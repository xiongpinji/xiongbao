"""内置用户存储 + 密码哈希（lite/full 内置模式）。

Keycloak（OIDC）为 full/enterprise 目标；未配置时用内置用户表。
Phase 5：进程内存储 + 启动默认 admin；生产应接 Keycloak/DB。
本模块同时支持注册/改密（内存 + 可选 DB 持久化）。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from passlib.context import CryptContext

from xagent.enterprise.auth.principal import ANONYMOUS_TENANT
from xagent.infra.logging import get_logger

logger = get_logger("xagent.users")
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass
class User:
    user_id: str
    tenant_id: str
    roles: list[str]
    password_hash: str
    email: str = ""

    def verify(self, plain: str) -> bool:
        return _pwd.verify(plain, self.password_hash)


class UserExistsError(Exception):
    """用户已存在。"""


class UserStore:
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def add(self, user_id: str, tenant_id: str, roles: list[str], password: str,
            email: str = "") -> User:
        if user_id in self._users:
            raise UserExistsError(user_id)
        u = User(user_id, tenant_id, roles, _pwd.hash(password), email)
        self._users[user_id] = u
        return u

    def get(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def authenticate(self, user_id: str, password: str) -> User | None:
        u = self._users.get(user_id)
        if u and u.verify(password):
            return u
        return None

    def change_password(self, user_id: str, new_password: str) -> bool:
        u = self._users.get(user_id)
        if not u:
            return False
        # dataclass 不可变字段 —— 重建
        self._users[user_id] = User(
            user_id=u.user_id, tenant_id=u.tenant_id, roles=u.roles,
            password_hash=_pwd.hash(new_password), email=u.email,
        )
        return True


@lru_cache
def get_user_store() -> UserStore:
    store = UserStore()
    # 默认 admin/admin（仅 lite/演示；生产强制改密 + 接 Keycloak）
    store._users["admin"] = User("admin", ANONYMOUS_TENANT, ["admin"], _pwd.hash("admin"))
    logger.info("user_store_init", default_admin=True)
    return store


def reset_user_store() -> None:
    get_user_store.cache_clear()
