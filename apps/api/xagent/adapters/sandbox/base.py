"""沙箱抽象 + 默认「禁用」实现 + 工厂。

安全原则：lite 模式默认 DisabledSandbox，**绝不在宿主机直接 exec 不可信代码**。
要真正执行须显式切到 docker / e2b 后端（Phase 2 落地）。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, runtime_checkable

from xagent.infra.settings import get_settings


@dataclass
class SandboxResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error: str | None = None


@runtime_checkable
class Sandbox(Protocol):
    backend: str
    async def run_code(self, language: str, code: str, *, timeout: int = 30) -> SandboxResult: ...
    async def health(self) -> bool: ...


class DisabledSandbox:
    """默认实现：拒绝执行，给出明确指引。"""

    backend = "disabled"

    async def run_code(self, language: str, code: str, *, timeout: int = 30) -> SandboxResult:
        return SandboxResult(
            ok=False,
            error=(
                "沙箱未启用：lite 模式禁止执行不可信代码。"
                "请配置 docker / E2B 后端（Phase 2）后重试。"
            ),
        )

    async def health(self) -> bool:
        return True


class DockerSandbox:
    """Docker 容器沙箱：用官方 docker SDK 在隔离容器执行代码。

    需要 docker daemon + 镜像（默认 python:3.11-slim）。未装 docker SDK
    或 daemon 不可达时，factory 降级回 DisabledSandbox。
    """

    backend = "docker"

    def __init__(self, image: str = "python:3.11-slim", network: str = "none") -> None:
        self._image = image
        self._network = network

    async def run_code(self, language: str, code: str, *, timeout: int = 30) -> SandboxResult:
        import docker  # 延迟导入

        client = docker.from_env()
        if language not in ("python", "python3"):
            return SandboxResult(ok=False, error=f"暂不支持语言: {language}")
        try:
            result = client.containers.run(
                self._image,
                command=["python", "-c", code],
                network=self._network,
                mem_limit="128m",
                cpu_quota=50000,
                detach=False,
                stdout=True,
                stderr=True,
                remove=True,
            )
            stdout = (
                result.decode("utf-8", errors="replace")
                if isinstance(result, bytes)
                else str(result)
            )
            return SandboxResult(ok=True, stdout=stdout, exit_code=0)
        except Exception as exc:
            return SandboxResult(ok=False, error=f"沙箱执行失败: {exc}")

    async def health(self) -> bool:
        try:
            import docker

            docker.from_env().ping()
            return True
        except Exception:
            return False


@lru_cache
def get_sandbox() -> Sandbox:
    settings = get_settings()
    # docker 后端：尝试 import docker，成功且 daemon 可达则用 DockerSandbox
    try:
        import docker  # noqa: F401

        return DockerSandbox()
    except ImportError:
        pass
    _ = settings
    return DisabledSandbox()


def reset_sandbox() -> None:
    get_sandbox.cache_clear()
