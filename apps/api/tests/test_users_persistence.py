"""UserStore DB 持久化测试（lite 内存用户存储缺口修复）。

模拟"进程重启"：``reset_user_store()`` 清空 lru_cache 单例（内存态全丢），
此后首个异步方法应从 users 表读透恢复。覆盖注册/改密/角色/删除/查重五个面。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.enterprise.auth.users import get_user_store, reset_user_store
from xagent.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _login(client: AsyncClient, username: str, password: str) -> int:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    return resp.status_code


async def _admin_headers(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_registered_user_survives_store_reset(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register", json={"username": "persist_u1", "password": "secret123"}
    )
    assert resp.status_code == 200

    reset_user_store()  # 模拟进程重启：内存态清空
    assert await _login(client, "persist_u1", "secret123") == 200  # DB 读透恢复


async def test_password_change_persists_across_reset(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register", json={"username": "persist_u2", "password": "oldpass123"}
    )
    token = r.json()["access_token"]
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "oldpass123", "new_password": "newpass123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    reset_user_store()
    assert await _login(client, "persist_u2", "oldpass123") == 401
    assert await _login(client, "persist_u2", "newpass123") == 200


async def test_admin_seed_survives_reset_untouched(client: AsyncClient) -> None:
    # 种子 admin 未改密时不受 DB 读透影响（DB 无 admin 行，内存种子保留）
    reset_user_store()
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True


async def test_duplicate_registration_blocked_after_reset(client: AsyncClient) -> None:
    r1 = await client.post(
        "/api/v1/auth/register", json={"username": "persist_u5", "password": "secret123"}
    )
    assert r1.status_code == 200

    reset_user_store()
    r2 = await client.post(
        "/api/v1/auth/register", json={"username": "persist_u5", "password": "secret123"}
    )
    assert r2.status_code == 409  # DB 读透后查重生效，不能重复注册


async def test_role_update_and_delete_persist(client: AsyncClient) -> None:
    headers = await _admin_headers(client)

    # admin 创建用户（tenants API → aadd 写透）
    r = await client.post(
        "/api/v1/tenants/users",
        json={"username": "persist_u3", "password": "secret123", "roles": ["member"]},
        headers=headers,
    )
    assert r.status_code == 200

    # 改角色
    r = await client.put(
        "/api/v1/tenants/users/persist_u3/roles",
        json={"roles": ["member", "editor"]},
        headers=headers,
    )
    assert r.status_code == 200

    reset_user_store()
    headers = await _admin_headers(client)
    users = (await client.get("/api/v1/tenants/users", headers=headers)).json()["users"]
    u3 = next(u for u in users if u["user_id"] == "persist_u3")
    assert set(u3["roles"]) == {"member", "editor"}  # 重启后角色仍是 DB 中的值

    # 删除
    r = await client.delete("/api/v1/tenants/users/persist_u3", headers=headers)
    assert r.status_code == 200

    reset_user_store()
    assert await _login(client, "persist_u3", "secret123") == 401  # 重启后不可登录


async def test_two_store_instances_share_users_direct() -> None:
    """直接构造两个 store 实例（模拟两进程/两实例），共享同一 DB。"""
    reset_user_store()
    s1 = get_user_store()
    await s1.aadd("persist_u4", "t1", ["member"], "password123456")

    reset_user_store()
    s2 = get_user_store()
    assert "persist_u4" not in s2._users  # 内存态确实是全新实例
    assert (await s2.aauthenticate("persist_u4", "password123456")) is not None
    assert (await s2.aauthenticate("persist_u4", "wrong-password")) is None
