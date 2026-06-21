"""用户注册/改密 + 对象存储 + 工作流持久化测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.adapters.storage import get_object_store
from xagent.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_register_new_user(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "newuser", "password": "secret123", "email": "u@e.com"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "newuser"
    assert body["tenant_id"] == "newuser"  # 自服务租户
    assert "member" in body["roles"]
    token = body["access_token"]

    # 新用户能 me
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["user_id"] == "newuser"


async def test_register_duplicate_conflict(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register", json={"username": "dup", "password": "secret123"}
    )
    resp = await client.post(
        "/api/v1/auth/register", json={"username": "dup", "password": "secret123"}
    )
    assert resp.status_code == 409


async def test_change_password(client: AsyncClient) -> None:
    # 注册
    r = await client.post(
        "/api/v1/auth/register", json={"username": "pwuser", "password": "oldpass123"}
    )
    token = r.json()["access_token"]
    # 改密
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "oldpass123", "new_password": "newpass123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    # 旧密码登录失败
    login_old = await client.post(
        "/api/v1/auth/login", json={"username": "pwuser", "password": "oldpass123"}
    )
    assert login_old.status_code == 401
    # 新密码登录成功
    login_new = await client.post(
        "/api/v1/auth/login", json={"username": "pwuser", "password": "newpass123"}
    )
    assert login_new.status_code == 200


async def test_change_password_wrong_old(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register", json={"username": "pw2", "password": "pass123456"}
    )
    token = r.json()["access_token"]
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "wrong", "new_password": "newpass123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


async def test_object_store_local_roundtrip() -> None:
    store = get_object_store()
    obj = await store.put("test.png", b"\x89PNG data", tenant_id="t1")
    assert obj.url.startswith("local://")
    data = await store.get(obj.url)
    assert data == b"\x89PNG data"
    await store.delete(obj.url)
    # 删除后 get 抛错
    with pytest.raises(FileNotFoundError):
        await store.get(obj.url)


async def test_object_store_tenant_isolation() -> None:
    store = get_object_store()
    a = await store.put("a.txt", b"tenantA", tenant_id="tenantA")
    b = await store.put("b.txt", b"tenantB", tenant_id="tenantB")
    # URL 含各自租户前缀，互不干扰
    assert "tenantA" in a.url
    assert "tenantB" in b.url
    assert await store.get(a.url) == b"tenantA"
    assert await store.get(b.url) == b"tenantB"
