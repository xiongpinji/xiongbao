"""数据库持久化测试：迁移建表 + repository 读写。

用临时 SQLite 文件库，测试前跑 alembic upgrade head 建表。
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC
from pathlib import Path

import pytest
from xagent.infra.db import dispose_engine, get_sessionmaker
from xagent.infra.repos.audit import load_audit_events, persist_audit_event
from xagent.infra.repos.billing import persist_billing_record
from xagent.infra.repos.workflow import load_workflow_runs, persist_workflow_run
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


async def test_workflow_roundtrip(migrated_db) -> None:
    view = {
        "run_id": "r1",
        "spec_name": "wf",
        "tenant_id": "t1",
        "status": "completed",
        "steps": [],
        "timeline": [],
    }
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:  # type: AsyncSession
        await persist_workflow_run(session, view)
        await session.commit()
    async with sessionmaker() as session:
        runs = await load_workflow_runs(session, "t1")
    assert runs
    assert runs[0]["run_id"] == "r1"
    # 租户隔离
    async with sessionmaker() as session:
        assert await load_workflow_runs(session, "tOTHER") == []


async def test_billing_persist(migrated_db) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await persist_billing_record(
            session, tenant_id="t1", actor="u", action="agent.run", tokens=5
        )


async def test_audit_persist_and_load(migrated_db) -> None:
    from datetime import datetime

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await persist_audit_event(
            session,
            ts=datetime.now(UTC),
            tenant_id="t1",
            actor="u",
            action="test",
            resource="agent",
            detail={"k": "v"},
            prev_hash="0" * 64,
            hash_="abc",
        )
    async with sessionmaker() as session:
        events = await load_audit_events(session, "t1")
    assert events
    assert events[0]["action"] == "test"
