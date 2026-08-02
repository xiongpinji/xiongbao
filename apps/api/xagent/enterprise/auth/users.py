"""内置用户存储 + 密码哈希。

Keycloak（OIDC）为 full/enterprise 目标；未配置时用内置用户表。
Phase 5：lite 启动默认 admin/admin（**仅本地演示**）：该账号标记
``must_change_password=True``，首次登录响应会携带该标记，前端应强制改密；
启动日志打显眼 warning。生产应接 Keycloak/DB 或显式初始化用户。
本模块同时支持注册/改密（内存 + 可选 DB 持久化）。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from passlib.context import CryptContext

from xagent.enterprise.auth.principal import ANONYMOUS_TENANT
from xagent.infra.logging import get_logger
from xagent.infra.settings import get_settings

logger = get_logger("xagent.users")
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass
class User:
    user_id: str
    tenant_id: str
    roles: list[str]
    password_hash: str
    email: str = ""
    # 使用默认/初始口令登录时为 True，前端应强制跳转改密；改密后自动清除
    must_change_password: bool = False

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
        # dataclass 不可变字段 —— 重建（改密后清除 must_change_password 标记）
        self._users[user_id] = User(
            user_id=u.user_id, tenant_id=u.tenant_id, roles=u.roles,
            password_hash=_pwd.hash(new_password), email=u.email,
            must_change_password=False,
        )
        return True


@lru_cache
def get_user_store() -> UserStore:
    store = UserStore()
    if get_settings().is_lite:
        # 默认口令仅限本地演示：标记强制改密 + 显眼 warning
        store._users["admin"] = User(
            "admin", ANONYMOUS_TENANT, ["admin"], _pwd.hash("admin"),
            must_change_password=True,
        )
        logger.warning(
            "default_admin_credentials_active",
            message=(
                "⚠️  安全问题：lite 模式内置默认账号 admin/admin，"
                "首次登录后必须修改密码（must_change_password=true）；"
                "请勿在可暴露网络的环境中使用默认口令"
            ),
        )
    else:
        logger.info("user_store_init", default_admin=False)
    return store


def reset_user_store() -> None:
    get_user_store.cache_clear()
