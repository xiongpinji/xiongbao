"""Principal —— 贯穿全栈的认证主体。"""

from __future__ import annotations

from dataclasses import dataclass, field

ANONYMOUS_TENANT = "default"


@dataclass(frozen=True)
class Principal:
    """认证主体。``tenant_id`` 必有，是多租户隔离的根。"""

    user_id: str
    tenant_id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)
    is_anonymous: bool = False

    @classmethod
    def anonymous(cls, tenant_id: str = ANONYMOUS_TENANT) -> Principal:
        """lite 模式无 token 时的匿名主体（默认租户 + member 角色）。"""
        return cls(
            user_id="anonymous",
            tenant_id=tenant_id,
            roles=frozenset({"member"}),
            is_anonymous=True,
        )

    def has_role(self, role: str) -> bool:
        return role in self.roles or "admin" in self.roles
