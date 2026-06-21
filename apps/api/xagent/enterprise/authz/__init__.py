"""授权层：RBAC/ABAC 检查。

Casbin（进程内）为目标实现；未安装时降级为内置策略表，保证 lite 可跑。
统一接口：``authorize(principal, resource, action) -> bool``。
"""

from xagent.enterprise.authz.rbac import (
    AccessRequest,
    authorize,
    get_enforcer,
    reset_enforcer,
)

__all__ = ["AccessRequest", "authorize", "get_enforcer", "reset_enforcer"]
