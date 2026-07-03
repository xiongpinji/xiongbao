"""工作流引擎测试：执行、补偿、审批门、回放、租户隔离。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

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
from xagent.infra.db import dispose_engine
from xagent.infra.settings import get_settings
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
async def client(migrated_db):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def migrated_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_file = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("XAGENT_DB__URL", url)
    get_settings.cache_clear()
    await dispose_engine()

    api_dir = str(Path(__file__).resolve().parent.parent)
    env = {**os.environ, "XAGENT_DB__URL": url, "PYTHONPATH": api_dir}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=api_dir,
        env=env,
        check=True,
        capture_output=True,
    )

    yield url

    await dispose_engine()
    get_settings.cache_clear()


@pytest.fixture
async def db_client(migrated_db):
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


async def test_workflow_api_run_degrades_when_runtime_task_table_missing(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.workflows as workflow_api

    original_table_exists = workflow_api._table_exists

    async def _fake_table_exists(session, table_name: str):  # noqa: ARG001
        if table_name == "agent_tasks":
            return False
        return await original_table_exists(session, table_name)

    monkeypatch.setattr(workflow_api, "_table_exists", _fake_table_exists)
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])

    resp = await client.post(
        "/api/v1/workflows",
        json={"name": "api-wf-legacy", "steps": [{"id": "s1", "name": "打招呼", "goal": "你好"}]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


async def test_workflow_api_run_degrades_when_workflow_view_table_missing(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.workflows as workflow_api
    from sqlalchemy.exc import OperationalError

    async def _missing_workflow_runs(*args, **kwargs):
        raise OperationalError(
            "SELECT ... FROM workflow_runs", {}, Exception("no such table: workflow_runs")
        )

    monkeypatch.setattr(workflow_api, "persist_workflow_run", _missing_workflow_runs)
    token = create_access_token(user_id="u-view-missing", tenant_id="tenant-1", roles=["member"])

    resp = await db_client.post(
        "/api/v1/workflows",
        json={"name": "wf-view-missing", "steps": [{"id": "s1", "name": "执行", "goal": "执行"}]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    run_id = resp.json()["run_id"]

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["workflow"] is None
    assert body["task"] is not None
    assert body["task"]["kind"] == "workflow.run"
    assert body["delivery"]["kind"] == "workflow.summary"


async def test_workflow_non_schema_workflow_view_failure_is_not_silently_swallowed(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.workflows as workflow_api

    async def _boom(*args, **kwargs):
        raise RuntimeError("workflow view write exploded")

    monkeypatch.setattr(workflow_api, "_persist_workflow_view", _boom)
    token = create_access_token(user_id="u-view-boom", tenant_id="tenant-1", roles=["member"])

    with pytest.raises(RuntimeError, match="workflow view write exploded"):
        await db_client.post(
            "/api/v1/workflows",
            json={"name": "wf-view-boom", "steps": [{"id": "s1", "name": "执行", "goal": "执行"}]},
            headers={"Authorization": f"Bearer {token}"},
        )


async def test_workflow_runtime_schema_mismatch_still_returns_workflow_view(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.workflows as workflow_api

    original_table_exists = workflow_api._table_exists

    async def _fake_table_exists(session, table_name: str):  # noqa: ARG001
        if table_name == "agent_tasks":
            return False
        return await original_table_exists(session, table_name)

    monkeypatch.setattr(workflow_api, "_table_exists", _fake_table_exists)
    token = create_access_token(user_id="u-schema", tenant_id="tenant-1", roles=["member"])

    resp = await db_client.post(
        "/api/v1/workflows",
        json={"name": "wf-schema-degrade", "steps": [{"id": "s1", "name": "执行", "goal": "执行"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["workflow"]["run_id"] == run_id
    assert body["task"] is None
    assert body["delivery"]["kind"] == "workflow.summary"


async def test_workflow_non_schema_view_failure_is_not_silently_swallowed(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.workflows as workflow_api

    async def _boom(*args, **kwargs):
        raise RuntimeError("workflow view write exploded")

    monkeypatch.setattr(workflow_api, "persist_workflow_run", _boom)
    token = create_access_token(user_id="u-view-boom", tenant_id="tenant-1", roles=["member"])

    with pytest.raises(RuntimeError, match="workflow view write exploded"):
        await db_client.post(
            "/api/v1/workflows",
            json={"name": "wf-view-boom", "steps": [{"id": "s1", "name": "执行", "goal": "执行"}]},
            headers={"Authorization": f"Bearer {token}"},
        )


async def test_workflow_non_schema_runtime_failure_is_not_silently_swallowed(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.workflows as workflow_api

    async def _boom(*args, **kwargs):
        raise RuntimeError("db write exploded")

    monkeypatch.setattr(workflow_api, "_upsert_runtime_task_record", _boom)
    token = create_access_token(user_id="u-boom", tenant_id="tenant-1", roles=["member"])

    with pytest.raises(RuntimeError, match="db write exploded"):
        await db_client.post(
            "/api/v1/workflows",
            json={
                "name": "wf-runtime-boom",
                "steps": [{"id": "s1", "name": "执行", "goal": "执行"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )


async def test_workflow_delivery_summary_is_visible_when_runtime_schema_degrades(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.api.v1.workflows as workflow_api

    original_table_exists = workflow_api._table_exists

    async def _fake_table_exists(session, table_name: str):  # noqa: ARG001
        if table_name == "agent_tasks":
            return False
        return await original_table_exists(session, table_name)

    monkeypatch.setattr(workflow_api, "_table_exists", _fake_table_exists)
    token = create_access_token(user_id="u-schema-runs", tenant_id="tenant-1", roles=["member"])

    resp = await db_client.post(
        "/api/v1/workflows",
        json={
            "name": "workflow-view-only",
            "steps": [{"id": "s1", "name": "执行", "goal": "执行"}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["workflow"]["run_id"] == run_id
    assert body["task"] is None
    assert [item["kind"] for item in body["evidence"]] == [
        "request.input",
        "result.final",
        "delivery.generated",
    ]
    assert body["delivery"] == {
        "status": "ready",
        "channel": "workflow_view",
        "kind": "workflow.summary",
        "summary": "工作流 workflow-view-only 已完成，1/1 个步骤成功。",
        "workflow": {
            "spec_name": "workflow-view-only",
            "status": "completed",
            "step_count": 1,
            "completed_steps": 1,
            "timeline_events": len(body["workflow"]["timeline"]),
            "highlights": ["执行"],
        },
        "replay": {
            "mode": "workflow_replay",
            "label": "回放工作流",
            "run_id": run_id,
            "api_path": f"/api/v1/workflows/{run_id}",
            "console_path": f"/runs/{run_id}",
        },
        "resume": None,
        "failure": None,
        "artifacts": [],
        "validation": {"risks": []},
        "risks": [],
    }


async def test_workflow_delivery_summary_is_visible_when_runtime_persistence_succeeds(
    db_client: AsyncClient,
) -> None:
    token = create_access_token(user_id="u", tenant_id="tenant-1", roles=["member"])
    resp = await db_client.post(
        "/api/v1/workflows",
        json={
            "name": "交付工作流",
            "description": "生成统一 delivery 摘要",
            "steps": [
                {"id": "plan", "name": "策划", "goal": "整理 brief"},
                {"id": "deliver", "name": "交付", "goal": "输出交付物", "depends_on": ["plan"]},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["task"]["kind"] == "workflow.run"
    assert body["delivery"] == {
        "status": "ready",
        "channel": "workflow_view",
        "kind": "workflow.summary",
        "summary": "工作流 交付工作流 已完成，2/2 个步骤成功。",
        "workflow": {
            "spec_name": "交付工作流",
            "status": "completed",
            "step_count": 2,
            "completed_steps": 2,
            "timeline_events": len(body["workflow"]["timeline"]),
            "highlights": ["策划", "交付"],
        },
        "replay": {
            "mode": "workflow_replay",
            "label": "回放工作流",
            "run_id": run_id,
            "api_path": f"/api/v1/workflows/{run_id}",
            "console_path": f"/runs/{run_id}",
        },
        "resume": None,
        "failure": None,
        "artifacts": [],
        "validation": {"risks": []},
        "risks": [],
    }


async def test_workflow_api_persists_delivery_summary_for_runtime_run(
    db_client: AsyncClient,
) -> None:
    token = create_access_token(user_id="u", tenant_id="tenant-1", roles=["member"])
    resp = await db_client.post(
        "/api/v1/workflows",
        json={
            "name": "交付工作流",
            "description": "生成统一 delivery 摘要",
            "steps": [
                {"id": "plan", "name": "策划", "goal": "整理 brief"},
                {"id": "deliver", "name": "交付", "goal": "输出交付物", "depends_on": ["plan"]},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    runtime_resp = await db_client.get(
        f"/api/v1/runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert runtime_resp.status_code == 200, runtime_resp.text
    body = runtime_resp.json()
    assert body["task"]["kind"] == "workflow.run"
    assert body["delivery"] == {
        "status": "ready",
        "channel": "workflow_view",
        "kind": "workflow.summary",
        "summary": "工作流 交付工作流 已完成，2/2 个步骤成功。",
        "workflow": {
            "spec_name": "交付工作流",
            "status": "completed",
            "step_count": 2,
            "completed_steps": 2,
            "timeline_events": len(body["workflow"]["timeline"]),
            "highlights": ["策划", "交付"],
        },
        "replay": {
            "mode": "workflow_replay",
            "label": "回放工作流",
            "run_id": run_id,
            "api_path": f"/api/v1/workflows/{run_id}",
            "console_path": f"/runs/{run_id}",
        },
        "resume": None,
        "failure": None,
        "artifacts": [],
        "validation": {"risks": []},
        "risks": [],
    }


async def test_workflow_api_viewer_forbidden(client: AsyncClient) -> None:
    token = create_access_token(user_id="v", tenant_id="t1", roles=["viewer"])
    resp = await client.post(
        "/api/v1/workflows",
        json={"name": "x", "steps": [{"id": "s1", "name": "x", "goal": "x"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
