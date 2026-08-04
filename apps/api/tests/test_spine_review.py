"""P4 review 闭环测试：复检 verdict 驱动任务状态迁移 + review.verdict 证据。"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.domains.code_review.models import Finding, ReviewResult
from xagent.main import create_app

_DIFF = """diff --git a/a.py b/a.py
index 0000000..1111111 100644
--- a/a.py
+++ b/a.py
@@ -0,0 +1,2 @@
+def f():
+    return 1
"""


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


async def _seed_review_task(client: AsyncClient, auth: dict) -> tuple[str, str]:
    """创建 goal 并把首个任务推进到 review 列，返回 (goal_id, task_id)。"""
    resp = await client.post(
        "/api/v1/spine/goals", json={"title": "review 闭环验证"}, headers=auth
    )
    assert resp.status_code == 200, resp.text
    goal_id = resp.json()["goal"]["goal_id"]
    task_id = resp.json()["tasks"][0]["task_id"]

    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.spine import DeliveryTaskORM

    async with get_sessionmaker()() as session:
        row = await session.get(DeliveryTaskORM, task_id)
        row.status = "review"
        await session.commit()
    return goal_id, task_id


def _stub_review(monkeypatch, *, status="succeeded", verdict="approve", findings=None):
    result = ReviewResult(
        status=status,
        verdict=verdict,
        summary="stub review",
        findings=findings or [],
        duration_ms=5.0,
    )

    async def _fake_review_diff(**kwargs):
        return result

    monkeypatch.setattr(
        "xagent.domains.code_review.review_diff", _fake_review_diff
    )
    return result


async def test_review_approve_transitions_to_release_ready(client, monkeypatch) -> None:
    _stub_review(monkeypatch, verdict="approve")
    auth = await _login(client)
    goal_id, task_id = await _seed_review_task(client, auth)

    resp = await client.post(
        f"/api/v1/spine/goals/{goal_id}/tasks/{task_id}/review",
        json={"diff": _DIFF},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] == "approve"
    assert body["task_status"] == "release_ready"
    assert body["transition"] == "review->release_ready"

    # review.verdict 证据已落库
    from sqlalchemy import select
    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.evidence import EvidenceORM

    async with get_sessionmaker()() as session:
        rows = (await session.execute(
            select(EvidenceORM).where(EvidenceORM.kind == "review.verdict")
        )).scalars().all()
    assert rows, "review.verdict 证据未落库"
    payload = json.loads(rows[-1].payload)
    assert payload["verdict"] == "approve"
    assert payload["transition"] == "review->release_ready"


async def test_review_request_changes_back_to_ready(client, monkeypatch) -> None:
    _stub_review(
        monkeypatch,
        verdict="request_changes",
        findings=[
            Finding(file="a.py", line=1, severity="high",
                    issue="空指针风险", suggestion="加判空"),
        ],
    )
    auth = await _login(client)
    goal_id, task_id = await _seed_review_task(client, auth)

    resp = await client.post(
        f"/api/v1/spine/goals/{goal_id}/tasks/{task_id}/review",
        json={"diff": _DIFF},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task_status"] == "ready"
    assert body["transition"] == "review->ready"

    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.spine import DeliveryTaskORM

    async with get_sessionmaker()() as session:
        row = await session.get(DeliveryTaskORM, task_id)
    assert "复检退回" in row.blocker_reason


async def test_review_failed_no_transition(client, monkeypatch) -> None:
    _stub_review(monkeypatch, status="failed", verdict="approve")
    auth = await _login(client)
    goal_id, task_id = await _seed_review_task(client, auth)

    resp = await client.post(
        f"/api/v1/spine/goals/{goal_id}/tasks/{task_id}/review",
        json={"diff": _DIFF},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_status"] == "review"  # 评审失败不迁移
    assert resp.json()["transition"] == "none"


async def test_review_rejects_non_review_task(client, monkeypatch) -> None:
    _stub_review(monkeypatch)
    auth = await _login(client)
    resp = await client.post(
        "/api/v1/spine/goals", json={"title": "非 review 列"}, headers=auth
    )
    goal_id = resp.json()["goal"]["goal_id"]
    task_id = resp.json()["tasks"][0]["task_id"]  # status=ready

    r = await client.post(
        f"/api/v1/spine/goals/{goal_id}/tasks/{task_id}/review",
        json={"diff": _DIFF},
        headers=auth,
    )
    assert r.status_code == 409
