"""内置用户存储 + 密码哈希。

Keycloak（OIDC）为 full/enterprise 目标；未配置时用内置用户表。
Phase 5：lite 启动默认 admin/admin（**仅本地演示**）：该账号标记
``must_change_password=True``，首次登录响应会携带该标记，前端应强制改密；
启动日志打显眼 warning。生产应接 Keycloak/DB 或显式初始化用户。
本模块同时支持注册/改密（内存 + 可选 DB 持久化）。
"""

from __future__ import annotations

import asyncio
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

    async def averify(self, plain: str) -> bool:
        """异步校验：bcrypt 校验为 CPU 密集（单次 ~300ms），移入线程池，
        避免阻塞事件循环。安全语义与 :meth:`verify` 完全一致。"""
        return await asyncio.to_thread(self.verify, plain)


class UserExistsError(Exception):
    """用户已存在。"""


class UserStore:
    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        # DB 读透只需一次（首个异步方法触发）；同步方法保持纯内存语义
        self._db_loaded = False

    # ── DB 持久化：读透 + 写透（users 表）────────────────────────────
    # 语义：DB 是注册用户的事实源——进程重启 / 多实例共享同一库时，
    # 首个异步方法把全表读入内存（同 id 覆盖内存条目，含种子 admin 的改密结果）；
    # 写操作先落内存再 best-effort 写透 DB。DB 不可用时降级纯内存，不阻断登录。

    async def _ensure_db_loaded(self) -> None:
        if self._db_loaded:
            return
        self._db_loaded = True
        try:
            from sqlalchemy import select

            from xagent.infra.db import get_sessionmaker
            from xagent.infra.models.user import User as UserRow

            async with get_sessionmaker()() as session:
                rows = (await session.execute(select(UserRow))).scalars().all()
            for row in rows:
                self._users[row.user_id] = User(
                    user_id=row.user_id,
                    tenant_id=row.tenant_id,
                    roles=[r for r in (row.roles or "").split(",") if r] or ["member"],
                    password_hash=row.password_hash or "",
                    email=row.email or "",
                    must_change_password=bool(row.must_change_password),
                )
            if rows:
                logger.info("user_store_db_loaded", count=len(rows))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "user_store_db_load_failed",
                message=f"users 表读取失败，本轮降级纯内存存储: {exc}",
            )

    async def _apersist(self, u: User) -> None:
        """写透单条用户记录（best-effort：失败仅告警，内存态仍生效）。"""
        try:
            from xagent.infra.db import get_sessionmaker
            from xagent.infra.models.user import User as UserRow

            async with get_sessionmaker()() as session:
                await session.merge(
                    UserRow(
                        user_id=u.user_id,
                        tenant_id=u.tenant_id,
                        roles=",".join(u.roles),
                        password_hash=u.password_hash,
                        email=u.email,
                        must_change_password=u.must_change_password,
                    )
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "user_store_persist_failed",
                message=f"用户 {u.user_id} 落库失败（内存态仍生效）: {exc}",
            )

    async def _adelete_row(self, user_id: str) -> None:
        try:
            from sqlalchemy import delete

            from xagent.infra.db import get_sessionmaker
            from xagent.infra.models.user import User as UserRow

            async with get_sessionmaker()() as session:
                await session.execute(delete(UserRow).where(UserRow.user_id == user_id))
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "user_store_delete_failed",
                message=f"用户 {user_id} 删库失败（内存态已删除）: {exc}",
            )

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

    async def aauthenticate(self, user_id: str, password: str) -> User | None:
        """异步认证：bcrypt 校验在线程池执行（不阻塞事件循环）。

        时序行为与同步版一致：用户不存在时不做 verify（短路返回）。
        先读透 DB，保证重启/其他实例写入的账号可认证。"""
        await self._ensure_db_loaded()
        u = self._users.get(user_id)
        if u and await u.averify(password):
            return u
        return None

    async def aadd(self, user_id: str, tenant_id: str, roles: list[str], password: str,
                   email: str = "") -> User:
        """异步新增用户：bcrypt 哈希（~300ms CPU）在线程池执行。

        先读透 DB 再查重（跨实例/重启后已存在的账号不能重复注册），成功后写透 DB。"""
        await self._ensure_db_loaded()
        if user_id in self._users:
            raise UserExistsError(user_id)
        password_hash = await asyncio.to_thread(_pwd.hash, password)
        u = User(user_id, tenant_id, roles, password_hash, email)
        self._users[user_id] = u
        await self._apersist(u)
        return u

    async def aget(self, user_id: str) -> User | None:
        """异步取用户（先读透 DB）。"""
        await self._ensure_db_loaded()
        return self._users.get(user_id)

    async def alist(self) -> list[User]:
        """异步列出全部用户（先读透 DB）。"""
        await self._ensure_db_loaded()
        return list(self._users.values())

    async def aupdate_roles(self, user_id: str, roles: list[str]) -> bool:
        """异步修改角色并写透 DB。"""
        await self._ensure_db_loaded()
        u = self._users.get(user_id)
        if not u:
            return False
        updated = User(
            user_id=u.user_id, tenant_id=u.tenant_id, roles=roles,
            password_hash=u.password_hash, email=u.email,
            must_change_password=u.must_change_password,
        )
        self._users[user_id] = updated
        await self._apersist(updated)
        return True

    async def adelete(self, user_id: str) -> bool:
        """异步删除用户（内存 + DB）。"""
        await self._ensure_db_loaded()
        if user_id not in self._users:
            return False
        del self._users[user_id]
        await self._adelete_row(user_id)
        return True

    async def achange_password(self, user_id: str, new_password: str) -> bool:
        """异步改密：bcrypt 哈希在线程池执行（改密后清除 must_change_password）。

        写透 DB——种子 admin 首次改密后，重启/其他实例以 DB 中哈希为准。"""
        await self._ensure_db_loaded()
        u = self._users.get(user_id)
        if not u:
            return False
        password_hash = await asyncio.to_thread(_pwd.hash, new_password)
        updated = User(
            user_id=u.user_id, tenant_id=u.tenant_id, roles=u.roles,
            password_hash=password_hash, email=u.email,
            must_change_password=False,
        )
        self._users[user_id] = updated
        await self._apersist(updated)
        return True

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
        # full/enterprise 模式：无默认账号。首次部署通过
        # XAGENT_ADMIN_BOOTSTRAP_PASSWORD 引导创建 admin（仅当库中无 admin 时生效），
        # 创建后必须首登改密；未设置时打引导提示 warning。
        import os

        bootstrap_pwd = os.environ.get("XAGENT_ADMIN_BOOTSTRAP_PASSWORD", "").strip()
        if bootstrap_pwd and "admin" not in store._users:
            if len(bootstrap_pwd) < 12:
                logger.warning(
                    "admin_bootstrap_weak_password",
                    message="XAGENT_ADMIN_BOOTSTRAP_PASSWORD 长度不足 12 位，已忽略",
                )
            else:
                store._users["admin"] = User(
                    "admin", ANONYMOUS_TENANT, ["admin"], _pwd.hash(bootstrap_pwd),
                    must_change_password=True,
                )
                logger.warning(
                    "admin_bootstrapped",
                    message="已通过 XAGENT_ADMIN_BOOTSTRAP_PASSWORD 引导创建 admin，"
                    "首次登录后必须修改密码；请尽快从环境中移除该变量",
                )
        elif not bootstrap_pwd:
            logger.warning(
                "admin_bootstrap_missing",
                message=(
                    "full/enterprise 模式无默认管理员：首次部署请设置 "
                    "XAGENT_ADMIN_BOOTSTRAP_PASSWORD（≥12 位）引导创建 admin，"
                    "或通过 SSO/OIDC 登录（realm_access.roles 映射）"
                ),
            )
    return store


def reset_user_store() -> None:
    get_user_store.cache_clear()
