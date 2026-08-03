"""P1 证据链自动生成测试：run.summary / workflow.summary / 归档 DB 导出。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from xagent.api.v1.agents import _build_run_summary_evidence
from xagent.api.v1.workflows import _build_workflow_evidence_records


def test_run_summary_evidence_shape() -> None:
    started = datetime.now(UTC) - timedelta(seconds=2)
    payload = {
        "run_id": "r1",
        "steps": 3,
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        "events": [
            {"kind": "tool_call", "tool": "web_search", "step": 1},
            {"kind": "tool_call", "tool": "web_search", "step": 2},
            {"kind": "tool_call", "tool": "read_file", "step": 3},
            {"kind": "message", "tool": None, "step": 4},
        ],
    }
    rec = _build_run_summary_evidence(payload, started_at=started, status="succeeded")
    assert rec["kind"] == "run.summary"
    p = rec["payload"]
    assert p["run_id"] == "r1"
    assert p["status"] == "succeeded"
    assert p["steps_count"] == 3
    assert p["tool_calls"] == 3
    assert p["tools_used"] == ["read_file", "web_search"]
    assert p["prompt_tokens"] == 100
    assert p["duration_ms"] >= 2000
    assert "error" not in p


def test_run_summary_evidence_failure_includes_error() -> None:
    rec = _build_run_summary_evidence(
        {"run_id": "r2"}, started_at=datetime.now(UTC),
        status="failed", error="boom" * 100,
    )
    assert rec["payload"]["status"] == "failed"
    assert rec["payload"]["error"].startswith("boom")
    assert len(rec["payload"]["error"]) <= 200


def test_workflow_summary_evidence_present() -> None:
    view = {
        "spec_name": "demo",
        "status": "running",
        "steps": [
            {"id": "s1", "name": "a", "status": "done"},
            {"id": "s2", "name": "b", "status": "failed"},
            {"id": "s3", "name": "c", "status": "pending"},
        ],
        "timeline": [{"kind": "approved", "step_id": "s1"}],
    }
    records = _build_workflow_evidence_records(view)
    kinds = [r["kind"] for r in records]
    assert "run.summary" in kinds
    summary = records[kinds.index("run.summary")]["payload"]
    assert summary["step_count"] == 3
    assert summary["steps_done"] == 1
    assert summary["steps_failed"] == 1
    assert summary["timeline_events"] == 1


async def test_archive_db_evidence_export(tmp_path, monkeypatch) -> None:
    """归档脚本导出最近 N 小时 evidence_records 为 JSONL。"""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from xagent.infra.db import Base
    from xagent.infra.models.evidence import EvidenceORM

    db_path = tmp_path / "x.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime.now(UTC)
    async with maker() as session:
        session.add(EvidenceORM(
            tenant_id="t1", evidence_id="e1", run_id="r1", task_id="t",
            kind="run.summary", payload=json.dumps({"status": "succeeded"}),
            created_at=now,
        ))
        session.add(EvidenceORM(
            tenant_id="t1", evidence_id="e2", run_id="r2", task_id="t",
            kind="alert:critical", payload="{}",
            created_at=now - timedelta(hours=48),  # 超出窗口
        ))
        await session.commit()

    # 注入脚本使用的 sessionmaker
    import xagent.infra.db as db_mod
    monkeypatch.setattr(db_mod, "_sessionmaker", maker)

    from scripts.auto_archive_evidence import collect_db_evidence_records

    out = tmp_path / "evidence.jsonl"
    # asyncio.run 不能在已运行的事件循环里调用，与脚本保持一致的同步包装
    count = await asyncio.to_thread(collect_db_evidence_records, 24, out)
    assert count == 1
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["kind"] == "run.summary"
    assert row["payload"]["status"] == "succeeded"
