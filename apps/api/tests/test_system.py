"""系统路由测试：health / ready / meta。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_ready(client: AsyncClient) -> None:
    resp = await client.get("/ready")
    # lite 模式 SQLite + 内存缓存均可用，应 ready
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    names = {c["name"] for c in body["components"]}
    assert {"database", "cache"} <= names


async def test_meta(client: AsyncClient) -> None:
    resp = await client.get("/meta")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "lite"


async def test_request_id_header(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.headers.get("x-request-id")
