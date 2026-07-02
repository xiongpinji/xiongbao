"""Evidence / delivery persistence tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from xagent.infra.db import dispose_engine, get_sessionmaker
from xagent.infra.models.agent_task import AgentTaskORM
from xagent.infra.models.artifact import ArtifactORM
from xagent.infra.repos.evidence import (
    build_evidence_record,
    load_evidence_records,
    persist_evidence_bundle,
    persist_evidence_record,
)
from xagent.infra.settings import get_settings


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


async def test_evidence_repo_uses_caller_transaction_and_filters_by_tenant(
    migrated_db,
) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await persist_evidence_record(
            session,
            evidence_id="ev-1",
            tenant_id="tenant-1",
            run_id="run-1",
            task_id="task-1",
            artifact_id="art-1",
            kind="delivery.receipt",
            payload={"channel": "email", "status": "delivered"},
        )
        await persist_evidence_record(
            session,
            evidence_id="ev-2",
            tenant_id="tenant-2",
            run_id="run-1",
            task_id="task-1",
            artifact_id=None,
            kind="validation.report",
            payload={"status": "passed"},
        )

    async with sessionmaker() as session:
        assert await load_evidence_records(session, "tenant-1", run_id="run-1") == []
        assert await load_evidence_records(session, "tenant-2", run_id="run-1") == []

    async with sessionmaker() as session:
        await persist_evidence_record(
            session,
            evidence_id="ev-1",
            tenant_id="tenant-1",
            run_id="run-1",
            task_id="task-1",
            artifact_id="art-1",
            kind="delivery.receipt",
            payload={"channel": "email", "status": "delivered"},
        )
        await persist_evidence_record(
            session,
            evidence_id="ev-2",
            tenant_id="tenant-2",
            run_id="run-1",
            task_id="task-1",
            artifact_id=None,
            kind="validation.report",
            payload={"status": "passed"},
        )
        await session.commit()

    async with sessionmaker() as session:
        records = await load_evidence_records(session, "tenant-1", run_id="run-1")
        other_tenant_records = await load_evidence_records(session, "tenant-2", run_id="run-1")

    assert records == [
        {
            "evidence_id": "ev-1",
            "tenant_id": "tenant-1",
            "run_id": "run-1",
            "task_id": "task-1",
            "artifact_id": "art-1",
            "kind": "delivery.receipt",
            "payload": {"channel": "email", "status": "delivered"},
        }
    ]
    assert other_tenant_records == [
        {
            "evidence_id": "ev-2",
            "tenant_id": "tenant-2",
            "run_id": "run-1",
            "task_id": "task-1",
            "artifact_id": None,
            "kind": "validation.report",
            "payload": {"status": "passed"},
        }
    ]


async def test_evidence_repo_allows_same_evidence_id_across_tenants(
    migrated_db,
) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await persist_evidence_record(
            session,
            evidence_id="ev-shared",
            tenant_id="tenant-1",
            run_id="run-1",
            task_id="task-1",
            artifact_id="art-1",
            kind="delivery.receipt",
            payload={"status": "delivered"},
        )
        await persist_evidence_record(
            session,
            evidence_id="ev-shared",
            tenant_id="tenant-2",
            run_id="run-2",
            task_id="task-2",
            artifact_id="art-2",
            kind="validation.report",
            payload={"status": "blocked"},
        )
        await session.commit()

    async with sessionmaker() as session:
        tenant_1_records = await load_evidence_records(session, "tenant-1", run_id="run-1")
        tenant_2_records = await load_evidence_records(session, "tenant-2", run_id="run-2")

    assert tenant_1_records == [
        {
            "evidence_id": "ev-shared",
            "tenant_id": "tenant-1",
            "run_id": "run-1",
            "task_id": "task-1",
            "artifact_id": "art-1",
            "kind": "delivery.receipt",
            "payload": {"status": "delivered"},
        }
    ]
    assert tenant_2_records == [
        {
            "evidence_id": "ev-shared",
            "tenant_id": "tenant-2",
            "run_id": "run-2",
            "task_id": "task-2",
            "artifact_id": "art-2",
            "kind": "validation.report",
            "payload": {"status": "blocked"},
        }
    ]


async def test_evidence_bundle_builds_stable_ids_and_persists_records(migrated_db) -> None:
    sessionmaker = get_sessionmaker()
    request_record = build_evidence_record(
        tenant_id="tenant-1",
        run_id="run-1",
        task_id="task-1",
        kind="request.input",
        payload={"goal": "collect evidence"},
    )
    duplicate_request_record = build_evidence_record(
        tenant_id="tenant-1",
        run_id="run-1",
        task_id="task-1",
        kind="request.input",
        payload={"goal": "collect evidence"},
    )

    assert request_record["evidence_id"] == duplicate_request_record["evidence_id"]

    async with sessionmaker() as session:
        persisted = await persist_evidence_bundle(
            session,
            tenant_id="tenant-1",
            run_id="run-1",
            task_id="task-1",
            records=[
                {"kind": "request.input", "payload": {"goal": "collect evidence"}},
                {"kind": "delivery.generated", "payload": {"status": "ready"}},
            ],
        )
        await session.commit()

    async with sessionmaker() as session:
        records = await load_evidence_records(session, "tenant-1", run_id="run-1")

    assert [item["kind"] for item in persisted] == ["request.input", "delivery.generated"]
    assert [item["kind"] for item in records] == ["request.input", "delivery.generated"]
    assert records[0]["evidence_id"] == request_record["evidence_id"]


async def test_agent_task_and_artifact_models_persist_summary_fields(migrated_db) -> None:
    sessionmaker = get_sessionmaker()
    validation_summary = {"status": "passed", "checks": 3}
    delivery_summary = {"status": "ready", "channel": "download"}
    lineage_summary = {"parent_task_id": "task-0", "artifact_ids": ["art-0"]}
    preview_summary = {"title": "Evidence package", "content_type": "application/pdf"}

    async with sessionmaker() as session:
        session.add(
            AgentTaskORM(
                task_id="task-1",
                run_id="run-1",
                tenant_id="tenant-1",
                owner_id="user-1",
                kind="agent.run",
                status="succeeded",
                backend="inproc",
                source="task",
                intent_type="agent",
                route_source="fallback",
                input_payload=json.dumps({"goal": "collect evidence"}, ensure_ascii=False),
                result_payload=json.dumps({"status": "done"}, ensure_ascii=False),
                validation_summary=json.dumps(validation_summary, ensure_ascii=False),
                delivery_summary=json.dumps(delivery_summary, ensure_ascii=False),
                lineage_summary=json.dumps(lineage_summary, ensure_ascii=False),
                preview_summary=json.dumps(preview_summary, ensure_ascii=False),
            )
        )
        session.add(
            ArtifactORM(
                artifact_id="art-1",
                run_id="run-1",
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
        await session.commit()

    async with sessionmaker() as session:
        task = await session.get(AgentTaskORM, "task-1")
        artifact = await session.get(ArtifactORM, "art-1")
        artifact_rows = (
            await session.execute(
                select(ArtifactORM).where(ArtifactORM.tenant_id == "tenant-1")
            )
        ).scalars().all()

    assert task is not None
    assert artifact is not None
    assert json.loads(task.validation_summary) == validation_summary
    assert json.loads(task.delivery_summary) == delivery_summary
    assert json.loads(task.lineage_summary) == lineage_summary
    assert json.loads(task.preview_summary) == preview_summary
    assert json.loads(artifact.validation_summary) == validation_summary
    assert json.loads(artifact.delivery_summary) == delivery_summary
    assert json.loads(artifact.lineage_summary) == lineage_summary
    assert json.loads(artifact.preview_summary) == preview_summary
    assert artifact.task_id == "task-1"
    assert [row.artifact_id for row in artifact_rows] == ["art-1"]
