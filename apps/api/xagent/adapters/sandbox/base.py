"""沙箱抽象 + 默认「禁用」实现 + 工厂。

安全原则：lite 模式默认 DisabledSandbox，**绝不在宿主机直接 exec 不可信代码**。
要真正执行须显式配置后端（RFC-001 分级）：
  - disabled : L0，拒绝执行（lite 默认）
  - docker   : L1，一次性隔离容器（见 docker_sandbox.py）
  - e2b      : L2，云 microVM（S3 落地，当前返回明确未实现错误）
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
                "请配置 XAGENT_SANDBOX__BACKEND=docker（或 e2b）后重试。"
            ),
        )

    async def health(self) -> bool:
        return True


class UnsupportedBackendSandbox:
    """已声明但未实现的后端（如 e2b）：明确报错，绝不静默降级到宿主机。"""

    def __init__(self, backend: str, reason: str) -> None:
        self.backend = backend
        self._reason = reason

    async def run_code(self, language: str, code: str, *, timeout: int = 30) -> SandboxResult:
        return SandboxResult(ok=False, error=self._reason)

    async def health(self) -> bool:
        return False


@lru_cache
def get_sandbox() -> Sandbox:
    """按 ``XAGENT_SANDBOX__BACKEND`` 选择沙箱后端（默认 disabled 保持现状）。"""
    backend = get_settings().sandbox.backend.strip().lower()
    if backend == "docker":
        from xagent.adapters.sandbox.docker_sandbox import DockerSandbox

        s = get_settings().sandbox
        return DockerSandbox(
            image=s.docker_image,
            mem_limit=s.mem_limit,
            cpu_quota=s.cpu_quota,
            network_disabled=s.network_disabled,
            readonly_rootfs=s.readonly_rootfs,
            timeout_seconds=s.timeout_seconds,
        )
    if backend == "e2b":
        return UnsupportedBackendSandbox(
            "e2b",
            "E2B 沙箱后端尚未实现（RFC-001 L2，计划 S3 落地）。"
            "请改用 XAGENT_SANDBOX__BACKEND=docker 或 disabled。",
        )
    return DisabledSandbox()


def reset_sandbox() -> None:
    get_sandbox.cache_clear()


# 兼容旧导入路径（DockerSandbox 已移至 docker_sandbox.py）
def __getattr__(name: str):
    if name == "DockerSandbox":
        from xagent.adapters.sandbox.docker_sandbox import DockerSandbox

        return DockerSandbox
    raise AttributeError(name)
