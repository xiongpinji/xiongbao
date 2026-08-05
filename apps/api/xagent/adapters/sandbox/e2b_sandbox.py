"""E2B 云沙箱（RFC-001 Level 2，对标 Codex 云容器隔离）。

面向云 / 企业部署：每次执行在独立的 firecracker microVM 中运行，
多租户串扰面收敛到 E2B 平台本身，不依赖宿主机 Docker daemon。

安全措施（与 L1 DockerSandbox 对齐）：
- 一次性 sandbox       : create → run → kill，用后销毁（``finally`` 兜底）
- 执行超时             : 超时参数透传 SDK / REST；超时即销毁 sandbox 并报错
- 输出截断             : stdout/stderr 超 64K 截断，防内存放大
- API key 兜底         : ``api_key`` 参数缺省时读 ``E2B_API_KEY`` 环境变量；
                         两者皆无 → 明确中文报错，绝不静默降级到宿主机

**网络隔离差异（重要）**：E2B 官方模板（含默认 ``code-interpreter``）
**默认有外网访问**，与 L1 docker 的 ``--network=none`` 语义不同。
需要禁网/白名单时须自建 E2B 模板（自定义 Dockerfile + 防火墙规则），
并通过 ``XAGENT_SANDBOX__E2B_TEMPLATE`` 指定。详见 docs/deployment/sandbox.md。

双通道实现：
- 优先官方 SDK（``e2b_code_interpreter``，延迟导入）；
- SDK 未安装时退化到 E2B REST API（httpx：POST /sandboxes 创建 →
  POST /sandboxes/{id}/code 执行 → DELETE 销毁）；
- 两者都不可用 → 明确中文错误（不静默降级）。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

from xagent.adapters.sandbox.base import SandboxResult

_MAX_OUTPUT_CHARS = 64_000  # 沙箱层输出截断上限（与 docker_sandbox 一致）

_SUPPORTED_LANGUAGES = {"python", "python3", "shell", "bash", "sh"}

# REST 通道执行 shell：经 python subprocess 包装（/code 端点本身只跑 python）
_SHELL_WRAPPER = (
    "import subprocess, sys\n"
    "r = subprocess.run({code!r}, shell=True, capture_output=True, text=True)\n"
    "sys.stdout.write(r.stdout)\n"
    "sys.stderr.write(r.stderr)\n"
    "sys.exit(r.returncode)\n"
)


class E2BUnavailableError(RuntimeError):
    """E2B 通道不可用：缺 API key / 缺 SDK 且 REST 通道缺失 / 创建失败。"""


def _truncate(text: str) -> str:
    if len(text) > _MAX_OUTPUT_CHARS:
        return text[:_MAX_OUTPUT_CHARS] + f"\n... [截断，共 {len(text)} 字符]"
    return text


def _is_timeout(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    return "timeout" in name or "timed out" in str(exc).lower()


class E2BSandbox:
    """E2B microVM 执行不可信代码（SDK 优先，REST 回退）。"""

    backend = "e2b"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        template: str = "code-interpreter",
        base_url: str = "https://api.e2b.dev",
        timeout_seconds: int = 30,
        sdk_factory: Callable[[], Any] | None = None,
        http_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        # API key：显式参数 > E2B_API_KEY 环境变量
        self._api_key = api_key or os.environ.get("E2B_API_KEY") or ""
        self._template = template
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        # 测试注入点：SDK sandbox 工厂 / httpx client 工厂
        self._sdk_factory = sdk_factory
        self._http_client_factory = http_client_factory

    # ── 通道解析 ────────────────────────────────────────────────

    def _resolve_sdk_factory(self) -> Callable[[], Any] | None:
        """返回 SDK sandbox 工厂；SDK 未安装返回 None（调用方回退 REST）。"""
        if self._sdk_factory is not None:
            return self._sdk_factory
        try:
            from e2b_code_interpreter import Sandbox as _E2BCodeSandbox
        except ImportError:
            return None

        def factory() -> Any:
            return _E2BCodeSandbox.create(
                template=self._template,
                api_key=self._api_key,
                timeout=self._timeout_seconds,
            )

        return factory

    def _make_http_client(self) -> Any:
        if self._http_client_factory is not None:
            return self._http_client_factory()
        try:
            import httpx
        except ImportError as exc:
            raise E2BUnavailableError(
                "E2B 沙箱不可用：未安装 e2b-code-interpreter SDK"
                "（pip install e2b-code-interpreter），且 REST 回退通道 "
                "httpx 也不可用。请安装其一，或将 "
                "XAGENT_SANDBOX__BACKEND 改为 docker/disabled。"
            ) from exc
        return httpx.Client(
            base_url=self._base_url,
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout_seconds + 10,  # 给创建/销毁留余量
        )

    # ── 主入口 ──────────────────────────────────────────────────

    async def run_code(
        self, language: str, code: str, *, timeout: int = 30
    ) -> SandboxResult:
        if language not in _SUPPORTED_LANGUAGES:
            return SandboxResult(ok=False, error=f"暂不支持语言: {language}")
        if not code.strip():
            return SandboxResult(ok=False, error="code 不能为空")
        if not self._api_key:
            return SandboxResult(
                ok=False,
                error=(
                    "E2B 沙箱不可用：未配置 API key。请设置 "
                    "XAGENT_SANDBOX__E2B_API_KEY（或 E2B_API_KEY 环境变量），"
                    "或将 XAGENT_SANDBOX__BACKEND 改为 docker/disabled。"
                ),
            )
        effective_timeout = timeout if timeout > 0 else self._timeout_seconds
        sdk_factory = self._resolve_sdk_factory()
        try:
            if sdk_factory is not None:
                return await asyncio.to_thread(
                    self._run_via_sdk, sdk_factory, language, code, effective_timeout
                )
            return await asyncio.to_thread(
                self._run_via_rest, language, code, effective_timeout
            )
        except E2BUnavailableError as exc:
            return SandboxResult(ok=False, error=str(exc))
        except Exception as exc:  # 网络/协议等意外异常兜底，绝不抛出
            return SandboxResult(ok=False, error=f"E2B 沙箱执行失败: {exc}")

    # ── SDK 通道 ────────────────────────────────────────────────

    def _run_via_sdk(
        self, sdk_factory: Callable[[], Any], language: str, code: str, timeout: int
    ) -> SandboxResult:
        sbx = sdk_factory()
        try:
            if language in ("python", "python3"):
                try:
                    execution = sbx.run_code(code, timeout=timeout)
                except Exception as exc:
                    if _is_timeout(exc):
                        return SandboxResult(
                            ok=False,
                            error=f"沙箱执行超时（{timeout}s），E2B sandbox 已销毁",
                        )
                    raise
                stdout = "\n".join(execution.logs.stdout or [])
                stderr = "\n".join(execution.logs.stderr or [])
                err = getattr(execution, "error", None)
                if err:
                    return SandboxResult(
                        ok=False,
                        stdout=_truncate(stdout),
                        stderr=_truncate(stderr),
                        exit_code=1,
                        error=str(err),
                    )
                return SandboxResult(
                    ok=True,
                    stdout=_truncate(stdout),
                    stderr=_truncate(stderr),
                    exit_code=0,
                )
            # shell 系语言：经 code interpreter 的 commands 通道
            try:
                result = sbx.commands.run(code, timeout=timeout)
            except Exception as exc:
                if _is_timeout(exc):
                    return SandboxResult(
                        ok=False,
                        error=f"沙箱执行超时（{timeout}s），E2B sandbox 已销毁",
                    )
                raise
            exit_code = getattr(result, "exit_code", -1)
            stdout = getattr(result, "stdout", "") or ""
            stderr = getattr(result, "stderr", "") or ""
            return SandboxResult(
                ok=exit_code == 0,
                stdout=_truncate(stdout),
                stderr=_truncate(stderr),
                exit_code=exit_code,
                error=stderr if exit_code != 0 and stderr else None,
            )
        finally:
            # sandbox 用后销毁
            try:
                sbx.kill()
            except Exception:
                pass

    # ── REST 通道（httpx 回退） ─────────────────────────────────

    def _run_via_rest(self, language: str, code: str, timeout: int) -> SandboxResult:
        client = self._make_http_client()
        sandbox_id: str | None = None
        try:
            # 1) 创建 sandbox
            try:
                resp = client.post(
                    "/sandboxes",
                    json={"templateID": self._template, "timeout": timeout},
                )
                resp.raise_for_status()
                sandbox_id = resp.json()["sandboxID"]
            except Exception as exc:
                raise E2BUnavailableError(
                    f"E2B 沙箱创建失败（{self._base_url}/sandboxes）: {exc}"
                ) from exc
            # 2) 执行代码（shell 经 subprocess 包装）
            payload_code = (
                code
                if language in ("python", "python3")
                else _SHELL_WRAPPER.format(code=code)
            )
            try:
                resp = client.post(
                    f"/sandboxes/{sandbox_id}/code",
                    json={"code": payload_code},
                    timeout=timeout,
                )
            except Exception as exc:
                if _is_timeout(exc):
                    return SandboxResult(
                        ok=False,
                        error=f"沙箱执行超时（{timeout}s），E2B sandbox 已销毁",
                    )
                raise E2BUnavailableError(f"E2B 代码执行请求失败: {exc}") from exc
            if resp.status_code >= 400:
                return SandboxResult(
                    ok=False,
                    error=f"E2B 代码执行失败: HTTP {resp.status_code} {resp.text[:500]}",
                )
            data = resp.json()
            logs = data.get("logs") or {}
            stdout = "\n".join(logs.get("stdout") or [])
            stderr = "\n".join(logs.get("stderr") or [])
            err = data.get("error")
            if err:
                message = err.get("message") if isinstance(err, dict) else str(err)
                return SandboxResult(
                    ok=False,
                    stdout=_truncate(stdout),
                    stderr=_truncate(stderr),
                    exit_code=1,
                    error=message,
                )
            return SandboxResult(
                ok=True,
                stdout=_truncate(stdout),
                stderr=_truncate(stderr),
                exit_code=0,
            )
        finally:
            # 3) 销毁 sandbox
            if sandbox_id:
                try:
                    client.delete(f"/sandboxes/{sandbox_id}")
                except Exception:
                    pass
            close = getattr(client, "close", None)
            if callable(close) and self._http_client_factory is None:
                try:
                    close()
                except Exception:
                    pass

    # ── 健康检查（配置级，不触网） ───────────────────────────────

    async def health(self) -> bool:
        if not self._api_key:
            return False
        if self._resolve_sdk_factory() is not None:
            return True
        if self._http_client_factory is not None:
            return True
        try:
            import httpx  # noqa: F401
        except ImportError:
            return False
        return True
