"""统一 task view 合同测试。"""

from __future__ import annotations

from xagent.core.orchestration.task_view import build_task_view


def test_build_task_view_defaults_to_unified_runtime_fields() -> None:
    payload = {"goal": "修复问题", "steps": [{"id": "s1", "meta": {"priority": "high"}}]}
    result = {"summary": "done", "items": [{"status": "ok"}]}
    view = build_task_view(
        task_id="repo-task-1",
        run_id=None,
        tenant_id="tenant-1",
        owner_id="user-1",
        kind="repo.task",
        backend="inproc",
        status="PENDING",
        input_payload=payload,
        result=result,
        created_at="2026-06-29T10:00:00+00:00",
    )

    payload["steps"][0]["meta"]["priority"] = "low"
    result["items"][0]["status"] = "mutated"

    assert view["task_id"] == "repo-task-1"
    assert view["run_id"] == "repo-task-1"
    assert view["status"] == "pending"
    assert view["source"] == "task"
    assert view["intent_type"] == "repo"
    assert view["route_source"] == "fallback"
    assert view["input"]["steps"][0]["meta"]["priority"] == "high"
    assert view["result"]["items"][0]["status"] == "ok"
    assert view["updated_at"] == "2026-06-29T10:00:00+00:00"


def test_build_task_view_keeps_explicit_route_metadata() -> None:
    view = build_task_view(
        task_id="workflow-task-1",
        run_id="runtime-run-1",
        tenant_id="tenant-1",
        owner_id="user-1",
        kind="agent.run",
        backend="celery",
        status="SUCCESS",
        source="workflow",
        intent_type="agent",
        route_source="planner",
        started_at="2026-06-29T10:01:00+00:00",
        finished_at="2026-06-29T10:02:00+00:00",
    )

    assert view["run_id"] == "runtime-run-1"
    assert view["status"] == "succeeded"
    assert view["source"] == "workflow"
    assert view["intent_type"] == "agent"
    assert view["route_source"] == "planner"
    assert view["updated_at"] == "2026-06-29T10:02:00+00:00"
