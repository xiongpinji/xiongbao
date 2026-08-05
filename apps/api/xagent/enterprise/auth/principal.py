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
        """鉴权关闭（演示模式）时的匿名主体。

        安全默认：**空角色**——只能通过无角色依赖的公开端点；任何带
        ``require_role`` / ``require_permission`` 的写/执行操作一律 403。
        """
        return cls(
            user_id="anonymous",
            tenant_id=tenant_id,
            roles=frozenset(),
            is_anonymous=True,
        )

    def has_role(self, role: str) -> bool:
        return role in self.roles or "admin" in self.roles
