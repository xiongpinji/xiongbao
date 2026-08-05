"""统一 Runtime 读模型与 /runs 聚合接口测试。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.core.orchestration.state import normalize_run_status
from xagent.core.runtime.models import RuntimeRun, RuntimeTaskRef
from xagent.core.runtime.policies import normalize_runtime_policy
from xagent.enterprise.auth import create_access_token
from xagent.infra.db import dispose_engine, get_sessionmaker
from xagent.infra.models.agent_task import AgentTaskORM
from xagent.infra.models.artifact import ArtifactORM
from xagent.infra.repos.evidence import persist_evidence_record
from xagent.infra.repos.workflow import persist_workflow_run
from xagent.infra.settings import get_settings
from xagent.main import create_app


@pytest.fixture
async def migrated_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """临时 SQLite 库 + 跑迁移建表。"""
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
async def client(migrated_db):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_runtime_run_to_view_exposes_unified_contract() -> None:
    payload = {"goal": "draft", "steps": [{"id": "s1", "tags": ["alpha"]}]}
    result = {"final_answer": "done", "artifacts": [{"name": "report"}]}
    run = RuntimeRun(
        run_id="run-1",
        task=RuntimeTaskRef(
            task_id="task-1",
            kind="repo.task",
            source="task",
            intent_type="repo",
            route_source="fallback",
        ),
        tenant_id="tenant-1",
        owner_id="user-1",
        status="SUCCESS",
        backend="inproc",
        input_payload=payload,
        result=result,
        created_at="2026-06-29T10:00:00+00:00",
    )

    view = run.to_view()
    payload["steps"][0]["tags"].append("beta")
    result["artifacts"][0]["name"] = "mutated"

    assert view["run_id"] == "run-1"
    assert view["task_id"] == "task-1"
    assert view["kind"] == "repo.task"
    assert view["status"] == "succeeded"
    assert view["source"] == "task"
    assert view["intent_type"] == "repo"
    assert view["route_source"] == "fallback"
    assert view["input"]["steps"][0]["tags"] == ["alpha"]
    assert view["result"]["artifacts"][0]["name"] == "report"
    assert view["updated_at"] == "2026-06-29T10:00:00+00:00"


def test_runtime_policy_normalization_applies_defaults() -> None:
    normalized = normalize_runtime_policy({"source": "workflow"})

    assert normalized["source"] == "workflow"
    assert normalized["intent_type"] == "general"
    assert normalized["route_source"] == "planner"


def test_runtime_policy_normalization_derives_repo_intent_from_kind() -> None:
    normalized = normalize_runtime_policy({"kind": "repo.task"})

    assert normalized["source"] == "task"
    assert normalized["intent_type"] == "repo"
    assert normalized["route_source"] == "fallback"


def test_runtime_policy_marks_unknown_kind_as_unknown() -> None:
    normalized = normalize_runtime_policy({"kind": "mystery.job"})

    assert normalized["source"] == "unknown"
    assert normalized["intent_type"] == "unknown"
    assert normalized["route_source"] == "fallback"


def test_normalize_run_status_normalizes_default_value() -> None:
    assert normalize_run_status("mystery", default="completed") == "succeeded"


async def test_runs_api_aggregates_live_task_contract(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="tenant-1", roles=["member"])
    submit = await client.post(
        "/api/v1/tasks",
        json={"goal": "生成统一 runtime 视图"},
        headers=_auth(token),
    )
    assert submit.status_code == 200, submit.text
    run_id = submit.json()["run_id"]

    resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run_id
    assert body["task"]["run_id"] == run_id
    assert body["task"]["task_id"] == run_id
    assert body["task"]["source"] == "task"
    assert body["task"]["route_source"] == "fallback"
    assert body["workflow"] is None
    assert body["evidence"] == []
    assert body["artifacts"] == []
    assert body["related_tasks"] == []
    assert body["validation"] == {"risks": []}
    assert body["delivery"]["channel"] == "task_runtime"
    assert body["delivery"]["kind"] == "agent.run"
    assert body["delivery"]["replay"] == {
        "mode": "task_detail",
        "label": "查看后台任务",
        "run_id": run_id,
        "task_id": run_id,
        "api_path": f"/api/v1/tasks/{run_id}",
        "console_path": f"/runs/{run_id}",
    }
    assert body["delivery"]["summary"]
    if body["task"]["status"] in {"pending", "running"}:
        assert body["delivery"]["resume"] == {
            "mode": "task_follow",
            "label": "继续查看后台任务",
            "run_id": run_id,
            "task_id": run_id,
            "status": body["task"]["status"],
            "api_path": f"/api/v1/tasks/{run_id}",
            "console_path": f"/runs/{run_id}",
        }
    else:
        assert body["delivery"]["resume"] is None
    assert body["delivery"]["risks"] == []


async def test_runs_api_reads_direct_agent_run_persisted_to_agent_tasks(
    client: AsyncClient,
) -> None:
    token = create_access_token(user_id="chat-user", tenant_id="tenant-1", roles=["member"])
    submit = await client.post(
        "/api/v1/agents/run",
        json={"goal": "把 chat run 持久化到统一 runtime"},
        headers=_auth(token),
    )
    assert submit.status_code == 200, submit.text
    created = submit.json()
    run_id = created["run_id"]

    resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run_id
    assert body["task"]["task_id"] == run_id
    assert body["task"]["kind"] == "agent.run"
    assert body["task"]["status"] == "succeeded"
    assert body["task"]["input"] == {
        "goal": "把 chat run 持久化到统一 runtime",
        "role": None,
        "capabilities": [],
        "model": None,
    }
    assert body["task"]["result"]["run_id"] == run_id
    assert body["task"]["result"]["final_answer"] == created["final_answer"]
    assert body["workflow"] is None
    assert [item["kind"] for item in body["evidence"]] == [
        "request.input",
        "result.final",
        "delivery.generated",
        "run.summary",
    ]
    assert body["delivery"]["channel"] == "task_runtime"
    assert body["delivery"]["artifacts"] == []
    assert body["delivery"]["validation"] == {"risks": []}
    assert body["delivery"]["risks"] == []
    assert body["delivery"]["replay"] == {
        "mode": "task_detail",
        "label": "查看后台任务",
        "run_id": run_id,
        "task_id": run_id,
        "api_path": f"/api/v1/tasks/{run_id}",
        "console_path": f"/runs/{run_id}",
    }
    assert body["delivery"]["resume"] is None


async def test_runs_api_reads_stream_agent_run_persisted_to_agent_tasks(
    client: AsyncClient,
) -> None:
    token = create_access_token(user_id="stream-user", tenant_id="tenant-1", roles=["member"])
    stream_resp = await client.post(
        "/api/v1/stream/agents/run",
        json={"goal": "把 stream run 持久化到统一 runtime"},
        headers={**_auth(token), "Accept": "text/event-stream"},
    )
    assert stream_resp.status_code == 200, stream_resp.text

    done_payload = None
    for chunk in stream_resp.text.split("\n\n"):
        if "event: done" not in chunk:
            continue
        data_line = next(
            (line for line in chunk.splitlines() if line.startswith("data: ")),
            None,
        )
        if data_line is None:
            continue
        done_payload = json.loads(data_line.removeprefix("data: "))
        break

    assert done_payload is not None, stream_resp.text
    run_id = done_payload["run_id"]

    resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run_id
    assert body["task"]["task_id"] == run_id
    assert body["task"]["kind"] == "agent.run"
    assert body["task"]["status"] == "succeeded"
    assert body["task"]["input"] == {
        "goal": "把 stream run 持久化到统一 runtime",
        "role": None,
        "capabilities": [],
    }
    assert body["task"]["result"]["run_id"] == run_id
    assert body["task"]["result"]["steps"] == done_payload["steps"]
    assert body["workflow"] is None
    assert [item["kind"] for item in body["evidence"]] == [
        "request.input",
        "result.final",
        "delivery.generated",
    ]
    assert body["delivery"]["channel"] == "task_runtime"
    assert body["delivery"]["artifacts"] == []
    assert body["delivery"]["validation"] == {"risks": []}
    assert body["delivery"]["risks"] == []
    assert body["delivery"]["replay"] == {
        "mode": "task_detail",
        "label": "查看后台任务",
        "run_id": run_id,
        "task_id": run_id,
        "api_path": f"/api/v1/tasks/{run_id}",
        "console_path": f"/runs/{run_id}",
    }
    assert body["delivery"]["resume"] is None


async def test_direct_agent_failure_persists_failed_task_and_failure_delivery(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(user_id="chat-user", tenant_id="tenant-1", roles=["member"])
    mocked_run_agent = AsyncMock(side_effect=RuntimeError("direct exploded"))
    monkeypatch.setattr("xagent.api.v1.agents.run_agent", mocked_run_agent)

    resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": "触发 direct 失败持久化"},
        headers=_auth(token),
    )

    assert resp.status_code == 500, resp.text
    assert mocked_run_agent.await_count == 1
    _, kwargs = mocked_run_agent.await_args
    run_id = kwargs["run_id"]
    assert resp.json() == {"detail": {"run_id": run_id, "error": "direct exploded"}}

    run_resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))

    assert run_resp.status_code == 200, run_resp.text
    body = run_resp.json()
    assert body["task"]["status"] == "failed"
    assert body["task"]["task_id"] == run_id
    assert body["task"]["result"]["status"] == "failed"
    assert body["task"]["result"]["error"] == "direct exploded"
    assert body["delivery"]["status"] == "blocked"
    assert body["delivery"]["resume"] == {
        "mode": "task_follow",
        "label": "继续查看后台任务",
        "run_id": run_id,
        "task_id": run_id,
        "status": "failed",
        "api_path": f"/api/v1/tasks/{run_id}",
        "console_path": f"/runs/{run_id}",
    }
    assert body["delivery"]["replay"] == {
        "mode": "task_detail",
        "label": "查看后台任务",
        "run_id": run_id,
        "task_id": run_id,
        "api_path": f"/api/v1/tasks/{run_id}",
        "console_path": f"/runs/{run_id}",
    }
    assert body["delivery"]["blocking_step"] == "agent.run"
    assert body["delivery"]["risks"] == ["direct exploded"]
    assert [item["kind"] for item in body["evidence"]] == [
        "request.input",
        "failure.evidence",
        "delivery.generated",
        "run.summary",
    ]
    assert body["evidence"][1]["payload"] == {"error": "direct exploded", "run_id": run_id}


async def test_stream_agent_failure_persists_failed_task_and_failure_delivery(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(user_id="stream-user", tenant_id="tenant-1", roles=["member"])
    mocked_run_agent = AsyncMock(side_effect=RuntimeError("stream exploded"))
    monkeypatch.setattr("xagent.api.v1.stream.run_agent", mocked_run_agent)

    stream_resp = await client.post(
        "/api/v1/stream/agents/run",
        json={"goal": "触发 stream 失败持久化"},
        headers={**_auth(token), "Accept": "text/event-stream"},
    )

    assert stream_resp.status_code == 200, stream_resp.text
    assert mocked_run_agent.await_count == 1
    _, kwargs = mocked_run_agent.await_args
    run_id = kwargs["run_id"]
    assert f'"run_id": "{run_id}"' in stream_resp.text
    assert "event: error" in stream_resp.text
    assert "stream exploded" in stream_resp.text

    run_resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))

    assert run_resp.status_code == 200, run_resp.text
    body = run_resp.json()
    assert body["task"]["status"] == "failed"
    assert body["task"]["task_id"] == run_id
    assert body["task"]["result"]["status"] == "failed"
    assert body["task"]["result"]["error"] == "stream exploded"
    assert body["delivery"]["status"] == "blocked"
    assert body["delivery"]["resume"] == {
        "mode": "task_follow",
        "label": "继续查看后台任务",
        "run_id": run_id,
        "task_id": run_id,
        "status": "failed",
        "api_path": f"/api/v1/tasks/{run_id}",
        "console_path": f"/runs/{run_id}",
    }
    assert body["delivery"]["blocking_step"] == "agent.run"
    assert body["delivery"]["risks"] == ["stream exploded"]
    assert [item["kind"] for item in body["evidence"]] == [
        "request.input",
        "failure.evidence",
        "delivery.generated",
    ]
    assert body["evidence"][1]["payload"] == {"error": "stream exploded", "run_id": run_id}


async def test_stream_agent_failure_before_result_does_not_take_schema_mismatch_done_path(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(user_id="stream-user-early", tenant_id="tenant-1", roles=["member"])
    mocked_run_agent = AsyncMock(side_effect=RuntimeError("no such table: evidence"))
    monkeypatch.setattr("xagent.api.v1.stream.run_agent", mocked_run_agent)

    stream_resp = await client.post(
        "/api/v1/stream/agents/run",
        json={"goal": "在 result 生成前触发 schema 类错误"},
        headers={**_auth(token), "Accept": "text/event-stream"},
    )

    assert stream_resp.status_code == 200, stream_resp.text
    assert mocked_run_agent.await_count == 1
    _, kwargs = mocked_run_agent.await_args
    run_id = kwargs["run_id"]
    assert "event: error" in stream_resp.text
    assert "event: done" not in stream_resp.text
    assert f'"run_id": "{run_id}"' in stream_resp.text

    run_resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))

    assert run_resp.status_code == 200, run_resp.text
    body = run_resp.json()
    assert body["task"]["status"] == "failed"
    assert body["task"]["result"]["error"] == "no such table: evidence"
    assert body["delivery"]["status"] == "blocked"
    assert [item["kind"] for item in body["evidence"]] == [
        "request.input",
        "failure.evidence",
        "delivery.generated",
    ]


async def test_direct_agent_success_survives_runtime_schema_mismatch(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(user_id="schema-user", tenant_id="tenant-1", roles=["member"])

    async def _boom(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("no such table: evidence")

    monkeypatch.setattr("xagent.api.v1.agents.persist_evidence_bundle", _boom)

    resp = await client.post(
        "/api/v1/agents/run",
        json={"goal": "成功但 evidence 表缺失"},
        headers=_auth(token),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"]
    assert body["final_answer"]


async def test_stream_agent_success_survives_runtime_schema_mismatch(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(
        user_id="schema-stream-user", tenant_id="tenant-1", roles=["member"]
    )

    async def _boom(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("no such table: evidence")

    monkeypatch.setattr("xagent.api.v1.stream.persist_evidence_bundle", _boom)

    stream_resp = await client.post(
        "/api/v1/stream/agents/run",
        json={"goal": "stream 成功但 evidence 表缺失"},
        headers={**_auth(token), "Accept": "text/event-stream"},
    )

    assert stream_resp.status_code == 200, stream_resp.text
    assert "event: done" in stream_resp.text


async def test_runs_api_aggregates_workflow_persistence_and_summaries(client: AsyncClient) -> None:
    sessionmaker = get_sessionmaker()
    workflow_view = {
        "run_id": "wf-run-1",
        "tenant_id": "tenant-1",
        "spec_name": "creative-flow",
        "status": "completed",
        "steps": [{"id": "plan", "status": "succeeded"}],
        "timeline": [{"kind": "succeeded", "step_id": "plan"}],
    }
    validation_summary = {
        "status": "passed",
        "checks": 3,
        "risks": ["validation: requires legal review"],
    }
    delivery_summary = {
        "status": "ready",
        "channel": "download",
        "risks": ["delivery: manual publish window"],
    }
    lineage_summary = {"parent_task_id": "task-0", "artifact_ids": ["art-parent"]}
    preview_summary = {"title": "delivery-report.pdf"}

    async with sessionmaker() as session:
        await persist_workflow_run(session, workflow_view)
        session.add(
            AgentTaskORM(
                task_id="task-0",
                run_id="wf-run-parent",
                tenant_id="tenant-1",
                owner_id="user-0",
                kind="agent.run",
                status="succeeded",
                backend="db",
                source="task",
                intent_type="agent",
                route_source="fallback",
                input_payload=json.dumps({"goal": "parent"}, ensure_ascii=False),
                result_payload=json.dumps({"final_answer": "parent done"}, ensure_ascii=False),
                preview_summary=json.dumps({"title": "parent"}, ensure_ascii=False),
            )
        )
        session.add(
            AgentTaskORM(
                task_id="task-1",
                run_id="wf-run-1",
                tenant_id="tenant-1",
                owner_id="user-1",
                kind="creative.produce",
                status="succeeded",
                backend="db",
                source="task",
                intent_type="creative",
                route_source="fallback",
                input_payload=json.dumps({"brief": "短剧"}, ensure_ascii=False),
                result_payload=json.dumps({"storyboard_id": "wf-run-1"}, ensure_ascii=False),
                validation_summary=json.dumps(validation_summary, ensure_ascii=False),
                delivery_summary=json.dumps(delivery_summary, ensure_ascii=False),
                lineage_summary=json.dumps(lineage_summary, ensure_ascii=False),
                preview_summary=json.dumps(preview_summary, ensure_ascii=False),
            )
        )
        session.add(
            AgentTaskORM(
                task_id="task-2",
                run_id="wf-run-1",
                tenant_id="tenant-1",
                owner_id="user-2",
                kind="repo.task",
                status="succeeded",
                backend="db",
                source="task",
                intent_type="repo",
                route_source="fallback",
                input_payload=json.dumps({"goal": "sibling"}, ensure_ascii=False),
                result_payload=json.dumps({"final_answer": "sibling done"}, ensure_ascii=False),
                preview_summary=json.dumps({"title": "sibling"}, ensure_ascii=False),
            )
        )
        session.add(
            ArtifactORM(
                artifact_id="art-parent",
                run_id="wf-run-parent",
                task_id="task-0",
                tenant_id="tenant-1",
                kind="context",
                name="parent-context.json",
                uri="s3://tenant-1/artifacts/parent-context.json",
                content_type="application/json",
                preview_summary=json.dumps({"title": "parent artifact"}, ensure_ascii=False),
            )
        )
        session.add(
            ArtifactORM(
                artifact_id="art-1",
                run_id="wf-run-1",
                task_id="task-1",
                tenant_id="tenant-1",
                kind="report",
                name="delivery-report.pdf",
                uri="s3://tenant-1/artifacts/delivery-report.pdf",
                content_type="application/pdf",
                validation_summary=json.dumps(validation_summary, ensure_ascii=False),
                delivery_summary=json.dumps(delivery_summary, ensure_ascii=False),
                lineage_summary=json.dumps(lineage_summary, ensure_ascii=False),
                preview_summary=json.dumps(preview_summary, ensure_ascii=False),
            )
        )
        await persist_evidence_record(
            session,
            evidence_id="ev-1",
            tenant_id="tenant-1",
            run_id="wf-run-1",
            task_id="task-1",
            artifact_id="art-1",
            kind="delivery.receipt",
            payload={"status": "delivered"},
        )
        await session.commit()

    token = create_access_token(user_id="u1", tenant_id="tenant-1", roles=["member"])
    resp = await client.get("/api/v1/runs/wf-run-1", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == "wf-run-1"
    assert body["task"]["task_id"] == "task-1"
    assert body["task"]["kind"] == "creative.produce"
    assert body["workflow"]["run_id"] == "wf-run-1"
    assert body["workflow"]["spec_name"] == "creative-flow"
    assert body["artifacts"] == [
        {
            "artifact_id": "art-1",
            "run_id": "wf-run-1",
            "task_id": "task-1",
            "tenant_id": "tenant-1",
            "kind": "report",
            "name": "delivery-report.pdf",
            "uri": "s3://tenant-1/artifacts/delivery-report.pdf",
            "content_type": "application/pdf",
            "size_bytes": 0,
            "checksum": "",
            "validation_summary": validation_summary,
            "delivery_summary": delivery_summary,
            "lineage_summary": lineage_summary,
            "preview_summary": preview_summary,
        }
    ]
    assert body["evidence"] == [
        {
            "evidence_id": "ev-1",
            "tenant_id": "tenant-1",
            "run_id": "wf-run-1",
            "task_id": "task-1",
            "artifact_id": "art-1",
            "kind": "delivery.receipt",
            "payload": {"status": "delivered"},
        }
    ]
    assert body["validation"] == validation_summary
    assert body["delivery"]["summary"]
    assert body["delivery"]["kind"]
    assert body["delivery"]["status"] == delivery_summary["status"]
    assert body["delivery"]["channel"] == delivery_summary["channel"]
    assert body["delivery"]["validation"] == validation_summary
    assert body["delivery"]["artifacts"] == [
        {
            "artifact_id": "art-1",
            "task_id": "task-1",
            "kind": "report",
            "name": "delivery-report.pdf",
            "uri": "s3://tenant-1/artifacts/delivery-report.pdf",
            "content_type": "application/pdf",
            "preview_summary": preview_summary,
        }
    ]
    assert body["delivery"]["risks"] == [
        "delivery: manual publish window",
        "validation: requires legal review",
    ]
    assert body["validation"]["risks"] == ["validation: requires legal review"]
    assert body["delivery"]["replay"] == {
        "mode": "workflow_replay",
        "label": "回放工作流",
        "run_id": "wf-run-1",
        "api_path": "/api/v1/workflows/wf-run-1",
        "console_path": "/runs/wf-run-1",
    }
    assert body["delivery"]["resume"] is None
    related_task_ids = {item["task_id"] for item in body["related_tasks"]}
    assert related_task_ids == {"task-0", "task-2"}
    parent_task = next(item for item in body["related_tasks"] if item["task_id"] == "task-0")
    sibling_task = next(item for item in body["related_tasks"] if item["task_id"] == "task-2")
    assert parent_task["run_id"] == "wf-run-parent"
    assert parent_task["result"]["final_answer"] == "parent done"
    assert sibling_task["run_id"] == "wf-run-1"
    assert sibling_task["result"]["final_answer"] == "sibling done"


async def test_runs_api_aggregates_workflow_route_run_without_agent_read(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.enterprise.authz.rbac as rbac

    admin_token = create_access_token(user_id="wf-owner", tenant_id="tenant-1", roles=["member"])
    create_resp = await client.post(
        "/api/v1/workflows",
        json={"name": "api-runtime-wf", "steps": [{"id": "s1", "name": "打招呼", "goal": "你好"}]},
        headers=_auth(admin_token),
    )
    assert create_resp.status_code == 200, create_resp.text
    run_id = create_resp.json()["run_id"]

    policy = {
        "workflow_reader": {"workflow": {"read"}},
    }
    monkeypatch.setattr(rbac, "get_enforcer", lambda: rbac.BuiltinEnforcer(policy))
    token = create_access_token(
        user_id="wf-reader", tenant_id="tenant-1", roles=["workflow_reader"]
    )

    resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workflow"] is not None
    assert body["workflow"]["run_id"] == run_id
    assert body["workflow"]["steps"]
    assert body["task"] is not None


async def test_runs_api_exposes_resume_pointer_for_awaiting_approval_workflow(
    client: AsyncClient,
) -> None:
    owner_token = create_access_token(user_id="owner-user", tenant_id="tenant-1", roles=["member"])

    create_resp = await client.post(
        "/api/v1/workflows",
        json={
            "name": "wf-awaiting-approval",
            "steps": [
                {
                    "id": "review/check",
                    "name": "人工复核",
                    "goal": "等待审核",
                    "approver_role": "admin",
                    "approval_message": "请审批后继续",
                }
            ],
        },
        headers=_auth(owner_token),
    )
    assert create_resp.status_code == 200, create_resp.text
    run_id = create_resp.json()["run_id"]

    run_resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(owner_token))

    assert run_resp.status_code == 200, run_resp.text
    body = run_resp.json()
    assert body["workflow"]["status"] == "awaiting_approval"
    assert body["evidence"]
    assert [item["kind"] for item in body["evidence"]] == [
        "request.input",
        "approval.requested",
        "delivery.generated",
        "run.summary",
    ]
    assert body["validation"] == {"risks": []}
    assert body["delivery"]["summary"]
    assert body["delivery"]["kind"] == "workflow.summary"
    assert body["delivery"]["artifacts"] == []
    assert body["delivery"]["validation"] == {"risks": []}
    assert body["delivery"]["status"] == "pending"
    assert body["delivery"]["risks"] == []
    assert body["delivery"]["replay"] == {
        "mode": "workflow_replay",
        "label": "回放工作流",
        "run_id": run_id,
        "api_path": f"/api/v1/workflows/{run_id}",
        "console_path": f"/runs/{run_id}",
    }
    assert body["delivery"]["resume"] == {
        "mode": "workflow_approval",
        "label": "继续审批 review/check",
        "run_id": run_id,
        "step_id": "review/check",
        "status": "awaiting_approval",
        "approve_path": f"/api/v1/workflows/{run_id}/approve/review%2Fcheck",
        "deny_path": f"/api/v1/workflows/{run_id}/deny/review%2Fcheck",
        "console_path": f"/runs/{run_id}",
    }

    owner_token = create_access_token(user_id="owner-user", tenant_id="tenant-1", roles=["member"])
    reviewer_token = create_access_token(
        user_id="reviewer-user", tenant_id="tenant-1", roles=["admin"]
    )

    create_resp = await client.post(
        "/api/v1/workflows",
        json={
            "name": "wf-approve-owner",
            "steps": [
                {
                    "id": "s1",
                    "name": "待审批",
                    "goal": "执行",
                    "approver_role": "admin",
                    "approval_message": "请审批",
                }
            ],
        },
        headers=_auth(owner_token),
    )
    assert create_resp.status_code == 200, create_resp.text
    run_id = create_resp.json()["run_id"]

    approve_resp = await client.post(
        f"/api/v1/workflows/{run_id}/approve/s1",
        headers=_auth(reviewer_token),
    )
    assert approve_resp.status_code == 200, approve_resp.text

    run_resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(owner_token))
    assert run_resp.status_code == 200, run_resp.text
    assert run_resp.json()["task"]["owner_id"] == "owner-user"

    create_resp_2 = await client.post(
        "/api/v1/workflows",
        json={
            "name": "wf-deny-owner",
            "steps": [
                {
                    "id": "s1",
                    "name": "待审批",
                    "goal": "执行",
                    "approver_role": "admin",
                    "approval_message": "请审批",
                }
            ],
        },
        headers=_auth(owner_token),
    )
    assert create_resp_2.status_code == 200, create_resp_2.text
    run_id_2 = create_resp_2.json()["run_id"]

    deny_resp = await client.post(
        f"/api/v1/workflows/{run_id_2}/deny/s1",
        headers=_auth(reviewer_token),
    )
    assert deny_resp.status_code == 200, deny_resp.text

    run_resp_2 = await client.get(f"/api/v1/runs/{run_id_2}", headers=_auth(owner_token))
    assert run_resp_2.status_code == 200, run_resp_2.text
    assert run_resp_2.json()["task"]["owner_id"] == "owner-user"


async def test_runs_api_reads_workflow_by_run_id_outside_recent_limit(client: AsyncClient) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        for index in range(205):
            await persist_workflow_run(
                session,
                {
                    "run_id": f"wf-run-{index}",
                    "tenant_id": "tenant-1",
                    "spec_name": f"flow-{index}",
                    "status": "completed",
                    "steps": [{"id": "s1", "status": "succeeded"}],
                    "timeline": [{"kind": "succeeded", "step_id": "s1"}],
                },
            )
        await session.commit()

    token = create_access_token(user_id="u1", tenant_id="tenant-1", roles=["member"])
    resp = await client.get("/api/v1/runs/wf-run-0", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workflow"] is not None
    assert body["workflow"]["run_id"] == "wf-run-0"
    assert body["workflow"]["spec_name"] == "flow-0"
    assert body["delivery"]["kind"] == "workflow.summary"


async def test_runs_api_returns_not_found_for_workflow_run_from_other_tenant_even_with_exact_lookup(
    client: AsyncClient,
) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await persist_workflow_run(
            session,
            {
                "run_id": "wf-run-foreign-tenant",
                "tenant_id": "tenant-2",
                "spec_name": "foreign-flow",
                "status": "completed",
                "steps": [{"id": "s1", "status": "succeeded"}],
                "timeline": [{"kind": "succeeded", "step_id": "s1"}],
            },
        )
        await session.commit()

    token = create_access_token(user_id="u1", tenant_id="tenant-1", roles=["member"])
    resp = await client.get("/api/v1/runs/wf-run-foreign-tenant", headers=_auth(token))

    assert resp.status_code == 404, resp.text


async def test_runs_api_returns_empty_related_tasks_without_lineage(client: AsyncClient) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await persist_workflow_run(
            session,
            {
                "run_id": "wf-run-empty-related",
                "tenant_id": "tenant-1",
                "spec_name": "solo-flow",
                "status": "completed",
                "steps": [],
                "timeline": [],
            },
        )
        session.add(
            AgentTaskORM(
                task_id="task-solo",
                run_id="wf-run-empty-related",
                tenant_id="tenant-1",
                owner_id="user-solo",
                kind="agent.run",
                status="succeeded",
                backend="db",
                source="task",
                intent_type="agent",
                route_source="fallback",
                input_payload=json.dumps({"goal": "solo"}, ensure_ascii=False),
                result_payload=json.dumps({"final_answer": "solo done"}, ensure_ascii=False),
            )
        )
        await session.commit()

    token = create_access_token(user_id="u1", tenant_id="tenant-1", roles=["member"])
    resp = await client.get("/api/v1/runs/wf-run-empty-related", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    assert resp.json()["related_tasks"] == []


async def test_runs_api_denies_workflow_content_without_workflow_read(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xagent.enterprise.authz.rbac as rbac

    owner_token = create_access_token(user_id="wf-owner-2", tenant_id="tenant-1", roles=["member"])
    create_resp = await client.post(
        "/api/v1/workflows",
        json={
            "name": "api-runtime-wf-deny",
            "steps": [{"id": "s1", "name": "执行", "goal": "执行"}],
        },
        headers=_auth(owner_token),
    )
    assert create_resp.status_code == 200, create_resp.text
    run_id = create_resp.json()["run_id"]

    policy = {
        "agent_reader": {"agent": {"read"}},
    }
    monkeypatch.setattr(rbac, "get_enforcer", lambda: rbac.BuiltinEnforcer(policy))
    token = create_access_token(user_id="agent-only", tenant_id="tenant-1", roles=["agent_reader"])

    resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))

    assert resp.status_code == 403


async def test_runs_api_returns_404_for_untracked_celery_ids(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import celery

    class _PendingResult:
        state = "PENDING"
        result = None

        def successful(self) -> bool:
            return False

        def failed(self) -> bool:
            return False

    class _CeleryStub:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ARG002
            pass

        def AsyncResult(self, task_id: str) -> _PendingResult:  # noqa: N802
            return _PendingResult()

    monkeypatch.setenv("XAGENT_CACHE__REDIS_URL", "redis://example")
    get_settings.cache_clear()
    monkeypatch.setattr(celery, "Celery", _CeleryStub)
    token = create_access_token(user_id="u9", tenant_id="tenant-1", roles=["member"])

    resp = await client.get("/api/v1/runs/ghost-celery-id", headers=_auth(token))

    assert resp.status_code == 404


async def test_runs_api_normalizes_creative_production_status(client: AsyncClient) -> None:
    token = create_access_token(user_id="u3", tenant_id="tenant-1", roles=["member"])
    submit = await client.post(
        "/api/v1/creative-studio/produce",
        json={"brief": "短剧运行聚合", "with_video": False},
        headers=_auth(token),
    )
    assert submit.status_code == 200, submit.text
    run_id = submit.json()["storyboard_id"]

    resp = await client.get(f"/api/v1/runs/{run_id}", headers=_auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task"]["kind"] == "creative.produce"
    assert body["task"]["status"] == "succeeded"
    assert body["related_tasks"] == []


async def test_runs_api_enforces_tenant_isolation(client: AsyncClient) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await persist_workflow_run(
            session,
            {
                "run_id": "wf-run-tenant-a",
                "tenant_id": "tenant-a",
                "spec_name": "isolated-flow",
                "status": "completed",
                "steps": [],
                "timeline": [],
            },
        )

    token = create_access_token(user_id="u2", tenant_id="tenant-b", roles=["member"])
    resp = await client.get("/api/v1/runs/wf-run-tenant-a", headers=_auth(token))

    assert resp.status_code == 404
