"""工作流引擎测试：执行、补偿、审批门、回放、租户隔离。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.core.workflow import (
    ApprovalGate,
    WorkflowSpec,
    WorkflowStep,
    get_engine,
)
from xagent.enterprise.auth import create_access_token
from xagent.enterprise.auth.principal import Principal
from xagent.main import create_app


def _spec(approval: bool = False, comp: bool = False) -> WorkflowSpec:
    steps = [
        WorkflowStep(id="s1", name="步骤1", role="general", goal="做A"),
    ]
    if comp:
        steps[0].compensation_role = "general"
        steps[0].compensation_goal = "回滚A"
    if approval:
        steps[0].approval = ApprovalGate(approver_role="admin", message="需审批")
    return WorkflowSpec(name="wf-test", steps=steps)


async def test_workflow_completes() -> None:
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    engine = get_engine()
    run = engine.create_run(_spec(), p)
    run = await engine.execute(run.run_id, p)
    assert run.status.value == "completed"
    assert run.steps[0].status.value == "succeeded"
    assert any(e.kind == "succeeded" for e in run.timeline)


async def test_workflow_view_structure() -> None:
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"}))
    engine = get_engine()
    run = engine.create_run(_spec(), p)
    run = await engine.execute(run.run_id, p)
    view = engine.replay(run.run_id, p)
    assert view["status"] == "completed"
    assert view["steps"][0]["status"] == "succeeded"
    assert view["timeline"]  # 护城河：结构化 timeline


async def test_approval_gate_pauses() -> None:
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"admin"}))
    engine = get_engine()
    run = engine.create_run(_spec(approval=True), p)
    run = await engine.execute(run.run_id, p)
    assert run.status.value == "awaiting_approval"
    assert run.steps[0].status.value == "awaiting_approval"
    # 审批通过后继续
    run = await engine.approve(run.run_id, "s1", p)
    assert run.status.value == "completed"


async def test_deny_cancels() -> None:
    p = Principal(user_id="u", tenant_id="t1", roles=frozenset({"admin"}))
    engine = get_engine()
    run = engine.create_run(_spec(approval=True), p)
    await engine.execute(run.run_id, p)
    run = await engine.deny(run.run_id, "s1", p)
    assert run.status.value == "cancelled"


async def test_tenant_isolation_in_workflow() -> None:
    a = Principal(user_id="a", tenant_id="tA", roles=frozenset({"member"}))
    b = Principal(user_id="b", tenant_id="tB", roles=frozenset({"member"}))
    engine = get_engine()
    run = engine.create_run(_spec(), a)
    # 租户 B 不能访问 A 的工作流
    with pytest.raises(KeyError):
        engine.replay(run.run_id, b)


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_workflow_api_run(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.post(
        "/api/v1/workflows",
        json={"name": "api-wf", "steps": [{"id": "s1", "name": "打招呼", "goal": "你好"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    view = resp.json()
    assert view["status"] == "completed"


async def test_workflow_api_viewer_forbidden(client: AsyncClient) -> None:
    token = create_access_token(user_id="v", tenant_id="t1", roles=["viewer"])
    resp = await client.post(
        "/api/v1/workflows",
        json={"name": "x", "steps": [{"id": "s1", "name": "x", "goal": "x"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
