"""RBAC 引擎。

内置策略（默认）：
  - admin   : 全部资源全部动作
  - member  : 对 agent/memory/workflow/creative/spine 可读写自身租户数据；不可管理用户/计费
  - viewer  : 只读

Casbin 可选：安装 casbin 后可加载外部模型/策略文件覆盖内置（Phase 5 接入策略管理）。
本模块对外只暴露 ``authorize(principal, resource, action)``，调用方不感知后端。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from xagent.enterprise.auth.principal import Principal


@dataclass(frozen=True)
class AccessRequest:
    resource: str  # 如 "agent" / "memory" / "billing"
    action: str    # 如 "read" / "write" / "execute" / "manage"


class Enforcer(Protocol):
    def enforce(self, role: str, resource: str, action: str) -> bool: ...


# 内置策略：role -> {resource -> {actions}}；"*" 通配
_BUILTIN_POLICY: dict[str, dict[str, set[str]]] = {
    "admin": {"*": {"*"}},
    "member": {
        "agent": {"read", "write", "execute"},
        "memory": {"read", "write"},
        "workflow": {"read", "write", "execute"},
        "creative": {"read", "write", "execute"},
        "spine": {"read", "write", "execute"},
        "tool": {"read", "execute"},
        "open_source": {"read"},
        "code_review": {"read", "execute"},
        "billing": {"read"},
        "audit": {"read"},
        "system": {"read", "manage"},
    },
    "viewer": {
        "agent": {"read"},
        "memory": {"read"},
        "workflow": {"read"},
        "creative": {"read"},
        "spine": {"read"},
        "tool": {"read"},
        "open_source": {"read"},
        "code_review": {"read"},
        "billing": {"read"},
        "audit": {"read"},
        "system": {"read"},
    },
}


class BuiltinEnforcer:
    """内置 RBAC（无外部依赖）。"""

    def __init__(self, policy: dict[str, dict[str, set[str]]] | None = None) -> None:
        self._policy = policy or _BUILTIN_POLICY

    def enforce(self, role: str, resource: str, action: str) -> bool:
        rules = self._policy.get(role)
        if not rules:
            return False
        for res in (resource, "*"):
            actions = rules.get(res)
            if actions and (action in actions or "*" in actions):
                return True
        return False


@lru_cache
def get_enforcer() -> Enforcer:
    """返回 RBAC enforcer。预留 Casbin 接入点，当前用内置实现。"""
    # Phase 5：若配置了 casbin 模型/策略文件，则 import casbin 构造 CasbinEnforcer。
    return BuiltinEnforcer()


def reset_enforcer() -> None:
    get_enforcer.cache_clear()


def authorize(principal: Principal, request: AccessRequest) -> bool:
    """对 principal 的任一角色满足即放行。"""
    enforcer = get_enforcer()
    return any(
        enforcer.enforce(role, request.resource, request.action)
        for role in principal.roles
    )
