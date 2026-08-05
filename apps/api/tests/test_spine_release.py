"""P4 release 收口测试：release_ready → ReleaseRecordORM + delivered。"""

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


async def _login(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _seed_goal(client: AsyncClient, auth: dict) -> tuple[str, list[str]]:
    resp = await client.post(
        "/api/v1/spine/goals", json={"title": "release 收口验证"}, headers=auth
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["goal"]["goal_id"], [t["task_id"] for t in data["tasks"]]


async def _set_tasks(task_ids: list[str], status: str) -> None:
    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.spine import DeliveryTaskORM

    async with get_sessionmaker()() as session:
        for tid in task_ids:
            row = await session.get(DeliveryTaskORM, tid)
            row.status = status
        await session.commit()


async def test_release_closes_goal(client: AsyncClient) -> None:
    auth = await _login(client)
    goal_id, task_ids = await _seed_goal(client, auth)
    # 全部任务到 release_ready
    await _set_tasks(task_ids, "release_ready")

    resp = await client.post(
        f"/api/v1/spine/goals/{goal_id}/release",
        json={
            "branch_name": "candidate/x",
            "commit_sha": "abc1234def",
            "pr_number": "7",
            "ci_run": {"id": "30871422526", "status": "success"},
            "evidence_paths": ["audit-20260802/"],
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["tasks_delivered"] == len(task_ids)
    assert body["goal_status"] == "delivered"

    from sqlalchemy import select
    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.spine import ReleaseRecordORM

    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(ReleaseRecordORM))).scalars().all()
    assert len(rows) == 1
    assert rows[0].commit_sha == "abc1234def"
    assert rows[0].goal_id == goal_id


async def test_release_rejects_when_nothing_ready(client: AsyncClient) -> None:
    auth = await _login(client)
    goal_id, _ = await _seed_goal(client, auth)
    resp = await client.post(
        f"/api/v1/spine/goals/{goal_id}/release",
        json={"branch_name": "b", "commit_sha": "abc1234"},
        headers=auth,
    )
    assert resp.status_code == 409


async def test_release_rejects_with_open_blockers(client: AsyncClient) -> None:
    auth = await _login(client)
    goal_id, task_ids = await _seed_goal(client, auth)
    await _set_tasks(task_ids[:-1], "release_ready")
    await _set_tasks([task_ids[-1]], "recovery")
    resp = await client.post(
        f"/api/v1/spine/goals/{goal_id}/release",
        json={"branch_name": "b", "commit_sha": "abc1234"},
        headers=auth,
    )
    assert resp.status_code == 409
    assert "未决任务" in resp.json()["detail"]


async def test_release_partial_delivery_keeps_goal_active(client: AsyncClient) -> None:
    auth = await _login(client)
    goal_id, task_ids = await _seed_goal(client, auth)
    await _set_tasks(task_ids[:-1], "release_ready")
    await _set_tasks([task_ids[-1]], "delivered")  # 已终态，不算未决

    resp = await client.post(
        f"/api/v1/spine/goals/{goal_id}/release",
        json={"branch_name": "b", "commit_sha": "abc1234"},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tasks_delivered"] == len(task_ids) - 1
    # 无剩余非终态任务 → goal delivered
    assert body["goal_status"] == "delivered"
