"""后台任务 Worker 测试。"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app
from xagent.worker import get_task_runner


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_submit_and_poll_task(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.post(
        "/api/v1/tasks", json={"goal": "你好"}, headers=_h(token)
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # 轮询直到完成（mock LLM 很快）
    for _ in range(20):
        s = await client.get(f"/api/v1/tasks/{task_id}", headers=_h(token))
        assert s.status_code == 200
        if s.json()["status"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.1)
    assert s.json()["status"] == "succeeded"
    assert s.json()["result"]["final_answer"]


async def test_task_tenant_isolation(client: AsyncClient) -> None:
    token_a = create_access_token(user_id="a", tenant_id="tA", roles=["member"])
    token_b = create_access_token(user_id="b", tenant_id="tB", roles=["member"])
    resp = await client.post("/api/v1/tasks", json={"goal": "x"}, headers=_h(token_a))
    task_id = resp.json()["task_id"]
    # 租户 B 看不到 A 的任务
    r = await client.get(f"/api/v1/tasks/{task_id}", headers=_h(token_b))
    assert r.status_code == 404


async def test_task_list(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    await client.post("/api/v1/tasks", json={"goal": "a"}, headers=_h(token))
    await client.post("/api/v1/tasks", json={"goal": "b"}, headers=_h(token))
    r = await client.get("/api/v1/tasks", headers=_h(token))
    assert r.status_code == 200
    assert len(r.json()["tasks"]) >= 2


async def test_task_runner_direct() -> None:
    runner = get_task_runner()

    async def _ok():
        await asyncio.sleep(0.01)
        return {"done": True}

    tid = runner.submit(_ok, kind="test", tenant_id="t1")
    for _ in range(20):
        rec = runner.get(tid, "t1")
        if rec.status.value in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.02)
    assert rec.status.value == "succeeded"
    assert rec.result == {"done": True}
