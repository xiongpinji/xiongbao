"""Docker 容器沙箱（RFC-001 Level 1）。

安全措施（对照 RFC-001 L1 清单）：
- ``--network=none``      : ``network_disabled=True``（默认禁网，防数据外泄）
- 资源限额                : ``mem_limit`` + ``cpu_quota``（防 fork bomb / 内存打爆）
- 只读根 fs               : ``read_only=True``（容器内不可写系统目录）
- 一次性容器              : create → start → wait → logs → remove(force)，用后销毁
- 执行超时                : ``wait(timeout=...)``，超时 kill 容器
- 输出截断                : stdout/stderr 超长截断，防内存放大
- Windows 支持            : docker SDK 走 npipe；daemon 不可达时给出明确报错

SDK 兼容性：docker SDK 7.x 已移除 ``logs(demux=True)``。本模块改用
stdout/stderr 分流两次 ``logs()`` 调用（实测 daemon 返回无帧头原始字节，
见 tests/test_docker_sandbox_integration.py），兼容 SDK 6.x/7.x。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

from xagent.adapters.sandbox.base import SandboxResult

_MAX_OUTPUT_CHARS = 64_000  # 沙箱层输出截断上限（工具层另有 4000 字符上限）

_LANGUAGE_COMMANDS: dict[str, Callable[[str], list[str]]] = {
    "python": lambda code: ["python", "-c", code],
    "python3": lambda code: ["python", "-c", code],
    "shell": lambda code: ["sh", "-c", code],
    "bash": lambda code: ["sh", "-c", code],
    "sh": lambda code: ["sh", "-c", code],
}


class SandboxUnavailableError(RuntimeError):
    """docker SDK 缺失或 daemon 不可达。"""


def _default_client() -> Any:
    """构造 docker client 并 ping 验证 daemon 可达（Windows 下为 npipe 连接）。"""
    try:
        import docker  # 延迟导入：docker SDK 不是 lite 硬依赖
    except ImportError as exc:
        raise SandboxUnavailableError(
            "Docker 沙箱不可用：未安装 docker SDK（pip install docker）。"
            "请安装后重试，或将 XAGENT_SANDBOX__BACKEND 改回 disabled。"
        ) from exc
    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:
        raise SandboxUnavailableError(
            "Docker 沙箱不可用：无法连接 Docker daemon"
            f"（Windows 需 Docker Desktop 运行且 npipe //./pipe/docker_engine 可用）: {exc}"
        ) from exc
    return client


def _truncate(text: str) -> str:
    if len(text) > _MAX_OUTPUT_CHARS:
        return text[:_MAX_OUTPUT_CHARS] + f"\n... [截断，共 {len(text)} 字符]"
    return text


def _collect_output(container: Any) -> tuple[str, str]:
    """分别回收 stdout / stderr（docker SDK 7.x 兼容，无 demux 依赖）。

    SDK 7.x 移除了 ``logs(demux=True)``；改为 stdout/stderr 分流两次调用。
    实测（Docker Engine 29，tty=False）：分流调用返回无帧头原始字节。
    防御：若 daemon 仍返回 8 字节多路复用帧（旧 daemon/双流场景），先解帧。
    """
    out_raw = container.logs(stdout=True, stderr=False) or b""
    err_raw = container.logs(stdout=False, stderr=True) or b""
    out_bytes = _strip_mux_frames(out_raw, stream_id=1)
    err_bytes = _strip_mux_frames(err_raw, stream_id=2)
    return (
        out_bytes.decode("utf-8", errors="replace"),
        err_bytes.decode("utf-8", errors="replace"),
    )


def _strip_mux_frames(data: bytes, *, stream_id: int) -> bytes:
    """若 data 是 Docker 多路复用帧流则解帧，否则原样返回。

    帧格式：[stream(1B), 0, 0, 0, size(4B big-endian)] + payload。
    仅在全部字节都能被完整解析为帧时才视为帧流，避免误伤正常输出。
    """
    if not data or data[0] not in (0, 1, 2):
        return data
    payload = bytearray()
    pos = 0
    while pos < len(data):
        if pos + 8 > len(data):
            return data  # 截断帧头 → 非帧流，原样返回
        sid = data[pos]
        size = int.from_bytes(data[pos + 4 : pos + 8], "big")
        if pos + 8 + size > len(data):
            return data  # 截断帧体 → 非帧流，原样返回
        if sid == stream_id:
            payload += data[pos + 8 : pos + 8 + size]
        pos += 8 + size
    return bytes(payload)


class DockerSandbox:
    """一次性 Docker 容器执行不可信代码。"""

    backend = "docker"

    def __init__(
        self,
        *,
        image: str = "python:3.11-slim",
        mem_limit: str = "512m",
        cpu_quota: int = 100000,
        network_disabled: bool = True,
        readonly_rootfs: bool = True,
        timeout_seconds: int = 30,
        workspace: str | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._image = image
        self._mem_limit = mem_limit
        self._cpu_quota = cpu_quota
        self._network_disabled = network_disabled
        self._readonly_rootfs = readonly_rootfs
        self._timeout_seconds = timeout_seconds
        # 工作区只读挂载（RFC-001：_WORKSPACE 以只读挂入 /work）
        self._workspace = workspace if workspace is not None else os.environ.get(
            "XAGENT_WORKSPACE"
        )
        self._client_factory = client_factory or _default_client

    async def run_code(
        self, language: str, code: str, *, timeout: int = 30
    ) -> SandboxResult:
        build_cmd = _LANGUAGE_COMMANDS.get(language)
        if build_cmd is None:
            return SandboxResult(ok=False, error=f"暂不支持语言: {language}")
        if not code.strip():
            return SandboxResult(ok=False, error="code 不能为空")
        effective_timeout = timeout if timeout > 0 else self._timeout_seconds
        try:
            client = await asyncio.to_thread(self._client_factory)
        except SandboxUnavailableError as exc:
            return SandboxResult(ok=False, error=str(exc))
        except Exception as exc:  # client_factory 意外异常也兜底
            return SandboxResult(ok=False, error=f"Docker 沙箱不可用: {exc}")
        try:
            return await asyncio.to_thread(
                self._run_sync, client, build_cmd(code), effective_timeout
            )
        except Exception as exc:
            return SandboxResult(ok=False, error=f"沙箱执行失败: {exc}")

    def _run_sync(self, client: Any, cmd: list[str], timeout: int) -> SandboxResult:
        """同步执行（线程池调用）：create → start → wait → logs → remove。"""
        kwargs: dict[str, Any] = {
            "command": cmd,
            "network_disabled": self._network_disabled,
            "read_only": self._readonly_rootfs,
            "mem_limit": self._mem_limit,
            "cpu_quota": self._cpu_quota,
            "detach": True,
            "tty": False,
        }
        if self._workspace:
            kwargs["volumes"] = {
                self._workspace: {"bind": "/work", "mode": "ro"}
            }
            kwargs["working_dir"] = "/work"
        container = client.containers.create(self._image, **kwargs)
        try:
            container.start()
            try:
                wait_result = container.wait(timeout=timeout)
            except Exception:
                # 超时（requests ReadTimeout / ConnectionError 等）：杀掉容器
                try:
                    container.kill()
                except Exception:
                    pass
                return SandboxResult(
                    ok=False, error=f"沙箱执行超时（{timeout}s），容器已终止"
                )
            exit_code = (
                wait_result.get("StatusCode", -1)
                if isinstance(wait_result, dict)
                else -1
            )
            stdout, stderr = _collect_output(container)
            return SandboxResult(
                ok=exit_code == 0,
                stdout=_truncate(stdout),
                stderr=_truncate(stderr),
                exit_code=exit_code,
                error=stderr if exit_code != 0 and stderr else None,
            )
        finally:
            # 容器用后销毁（--rm 语义）
            try:
                container.remove(force=True)
            except Exception:
                pass

    async def health(self) -> bool:
        try:
            await asyncio.to_thread(self._client_factory)
            return True
        except Exception:
            return False
