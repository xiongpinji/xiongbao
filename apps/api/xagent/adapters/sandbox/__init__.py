"""沙箱适配层：不可信代码的隔离执行。

接口稳定，多后端：
  - docker  : 容器隔离（full/单机生产，需 docker daemon）
  - e2b     : 云沙箱（Phase 2 接入，需 key）
  - disabled: lite 默认，拒绝执行并返回明确提示（安全第一，绝不在宿主机裸跑）
"""

from xagent.adapters.sandbox.base import (
    Sandbox,
    SandboxResult,
    get_sandbox,
    reset_sandbox,
)

__all__ = ["Sandbox", "SandboxResult", "get_sandbox", "reset_sandbox"]
