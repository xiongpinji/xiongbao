"""沙箱适配层：不可信代码的隔离执行。

接口稳定，多后端（XAGENT_SANDBOX__BACKEND 配置）：
  - docker  : 容器隔离（RFC-001 L1，需 docker daemon）
  - e2b     : 云 microVM（RFC-001 L2，SDK 优先 + REST 回退）
  - disabled: lite 默认，拒绝执行并返回明确提示（安全第一，绝不在宿主机裸跑）
"""

from xagent.adapters.sandbox.base import (
    DisabledSandbox,
    Sandbox,
    SandboxResult,
    UnsupportedBackendSandbox,
    get_sandbox,
    reset_sandbox,
)
from xagent.adapters.sandbox.docker_sandbox import DockerSandbox, SandboxUnavailableError
from xagent.adapters.sandbox.e2b_sandbox import E2BSandbox, E2BUnavailableError

__all__ = [
    "DisabledSandbox",
    "DockerSandbox",
    "E2BSandbox",
    "E2BUnavailableError",
    "Sandbox",
    "SandboxResult",
    "SandboxUnavailableError",
    "UnsupportedBackendSandbox",
    "get_sandbox",
    "reset_sandbox",
]
