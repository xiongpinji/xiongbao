"""数据库 checkpoint 的租户、父子关系与脱敏门禁。"""

from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from xagent.domains.checkpoints import (
    create_checkpoint,
    create_resume_checkpoint,
    get_checkpoint,
    list_checkpoints,
    upsert_checkpoint_snapshot,
)
from xagent.infra.db import Base


@pytest.fixture
async def checkpoint_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'checkpoints.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def test_checkpoint_is_tenant_scoped_redacted_and_preserves_parent_history(
    checkpoint_session, tmp_path
) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('safe')", encoding="utf-8")

    parent = await create_checkpoint(
        checkpoint_session,
        tenant_id="tenant-a",
        conversation_id="conversation-a",
        run_id="run-a",
        step=5,
        goal='fix release OPENAI_API_KEY=release-secret and {"token":"json-secret"}',
        messages=[
            {
                "role": "user",
                "content": "Authorization: Bearer bearer-secret TOKEN=token-secret",
                "tool_calls": [
                    {"arguments": {"provider_secret": "nested-secret"}}
                ],
            }
        ],
        changed_files=[str(source)],
        workspace=workspace,
    )
    child = await create_resume_checkpoint(
        checkpoint_session,
        tenant_id="tenant-a",
        checkpoint_id=parent.checkpoint_id,
        new_run_id="run-resumed",
    )
    await checkpoint_session.commit()

    assert "release-secret" not in parent.goal
    assert "json-secret" not in parent.goal
    assert "bearer-secret" not in parent.messages[0]["content"]
    assert "token-secret" not in parent.messages[0]["content"]
    assert "nested-secret" not in str(parent.messages)
    assert parent.changed_files == ["src/app.py"]
    assert child.parent_checkpoint_id == parent.checkpoint_id
    assert child.run_id == "run-resumed"
    assert child.status == "pending"

    history = await list_checkpoints(
        checkpoint_session, "tenant-a", conversation_id="conversation-a"
    )
    assert {item.checkpoint_id for item in history} == {
        parent.checkpoint_id,
        child.checkpoint_id,
    }
    assert await get_checkpoint(
        checkpoint_session, "tenant-b", parent.checkpoint_id
    ) is None
    assert await list_checkpoints(
        checkpoint_session, "tenant-b", conversation_id="conversation-a"
    ) == []


async def test_checkpoint_rejects_changed_file_outside_workspace(
    checkpoint_session, tmp_path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("unsafe", encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe_changed_file"):
        await create_checkpoint(
            checkpoint_session,
            tenant_id="tenant-a",
            conversation_id="conversation-a",
            run_id="run-a",
            step=1,
            goal="unsafe path",
            messages=[],
            changed_files=[str(outside)],
            workspace=workspace,
        )


async def test_upsert_checkpoint_snapshot_updates_same_scope_without_duplicate(
    checkpoint_session, tmp_path
) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('safe')", encoding="utf-8")

    created, replaced = await upsert_checkpoint_snapshot(
        checkpoint_session,
        tenant_id="tenant-a",
        conversation_id="conversation-a",
        run_id="run-a",
        step=5,
        goal="initial",
        messages=[{"role": "user", "content": "initial"}],
        changed_files=[],
        workspace=workspace,
    )
    updated, replaced_again = await upsert_checkpoint_snapshot(
        checkpoint_session,
        tenant_id="tenant-a",
        conversation_id="conversation-a",
        run_id="run-a",
        step=5,
        goal="finish OPENAI_API_KEY=release-secret",
        messages=[
            {"role": "user", "content": "finish"},
            {
                "role": "assistant",
                "content": "Authorization=auth-secret",
            },
        ],
        changed_files=[str(source)],
        workspace=workspace,
    )
    await checkpoint_session.commit()

    history = await list_checkpoints(checkpoint_session, "tenant-a", run_id="run-a")
    assert created.checkpoint_id == updated.checkpoint_id
    assert replaced is False
    assert replaced_again is True
    assert [checkpoint.step for checkpoint in history] == [5]
    assert history[0].messages[-2:][0] == {"role": "user", "content": "finish"}
    assert history[0].messages[-1]["role"] == "assistant"
    assert "auth-secret" not in history[0].messages[-1]["content"]
    assert "[REDACTED]" in history[0].messages[-1]["content"]
    assert "release-secret" not in history[0].goal
    assert history[0].changed_files == ["src/app.py"]


async def test_upsert_checkpoint_snapshot_scopes_by_conversation_id(
    checkpoint_session, tmp_path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    first, _ = await upsert_checkpoint_snapshot(
        checkpoint_session,
        tenant_id="tenant-a",
        conversation_id="conversation-a",
        run_id="run-a",
        step=5,
        goal="first",
        messages=[{"role": "assistant", "content": "first"}],
        changed_files=[],
        workspace=workspace,
    )
    second, _ = await upsert_checkpoint_snapshot(
        checkpoint_session,
        tenant_id="tenant-a",
        conversation_id="conversation-b",
        run_id="run-a",
        step=5,
        goal="second",
        messages=[{"role": "assistant", "content": "second"}],
        changed_files=[],
        workspace=workspace,
    )
    updated, replaced = await upsert_checkpoint_snapshot(
        checkpoint_session,
        tenant_id="tenant-a",
        conversation_id="conversation-a",
        run_id="run-a",
        step=5,
        goal="first updated",
        messages=[{"role": "assistant", "content": "first updated"}],
        changed_files=[],
        workspace=workspace,
    )
    await checkpoint_session.commit()

    assert replaced is True
    assert updated.checkpoint_id == first.checkpoint_id
    assert second.checkpoint_id != first.checkpoint_id
    first_history = await list_checkpoints(
        checkpoint_session, "tenant-a", conversation_id="conversation-a"
    )
    second_history = await list_checkpoints(
        checkpoint_session, "tenant-a", conversation_id="conversation-b"
    )
    assert first_history[0].messages == [
        {"role": "assistant", "content": "first updated"}
    ]
    assert second_history[0].messages == [{"role": "assistant", "content": "second"}]


async def test_upsert_checkpoint_snapshot_fails_on_duplicate_same_scope(
    tmp_path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'dirty.db'}")
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                CREATE TABLE checkpoints (
                    checkpoint_id VARCHAR(64) PRIMARY KEY,
                    tenant_id VARCHAR(64) NOT NULL,
                    conversation_id VARCHAR(64) NOT NULL,
                    run_id VARCHAR(96) NOT NULL,
                    parent_checkpoint_id VARCHAR(64) NOT NULL DEFAULT '',
                    step INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(32) NOT NULL,
                    goal TEXT NOT NULL DEFAULT '',
                    messages_json TEXT NOT NULL DEFAULT '[]',
                    changed_files_json TEXT NOT NULL DEFAULT '[]',
                    resumed_run_id VARCHAR(96) NOT NULL DEFAULT '',
                    rollback_source VARCHAR(32) NOT NULL DEFAULT '',
                    rollback_commit VARCHAR(128) NOT NULL DEFAULT '',
                    rollback_error TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        for index, content in enumerate(("first", "duplicate")):
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO checkpoints (
                        checkpoint_id, tenant_id, conversation_id, run_id, step,
                        status, goal, messages_json, changed_files_json,
                        created_at, updated_at
                    )
                    VALUES (
                        :checkpoint_id, 'tenant-a', 'conversation-a', 'run-a', 5,
                        'available', :goal, :messages_json, '[]',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "checkpoint_id": f"dirty-{index}",
                    "goal": content,
                    "messages_json": f'[{{"role":"assistant","content":"{content}"}}]',
                },
            )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        with pytest.raises(ValueError, match="checkpoint_scope_conflict"):
            await upsert_checkpoint_snapshot(
                session,
                tenant_id="tenant-a",
                conversation_id="conversation-a",
                run_id="run-a",
                step=5,
                goal="terminal",
                messages=[{"role": "assistant", "content": "terminal"}],
                changed_files=[],
                workspace=workspace,
            )
        await session.rollback()
        rows = (
            await session.execute(
                sa.text("SELECT messages_json FROM checkpoints ORDER BY checkpoint_id")
            )
        ).scalars().all()
    await engine.dispose()

    assert rows == [
        '[{"role":"assistant","content":"first"}]',
        '[{"role":"assistant","content":"duplicate"}]',
    ]


async def test_upsert_checkpoint_snapshot_concurrent_same_scope_keeps_one_row(
    tmp_path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'concurrent.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def write_snapshot(content: str) -> None:
        async with maker() as session:
            await upsert_checkpoint_snapshot(
                session,
                tenant_id="tenant-a",
                conversation_id="conversation-a",
                run_id="run-a",
                step=5,
                goal=content,
                messages=[{"role": "assistant", "content": content}],
                changed_files=[],
                workspace=workspace,
            )
            await session.commit()

    await asyncio.gather(write_snapshot("first"), write_snapshot("second"))
    async with maker() as session:
        await upsert_checkpoint_snapshot(
            session,
            tenant_id="tenant-a",
            conversation_id="conversation-a",
            run_id="run-a",
            step=5,
            goal="final",
            messages=[{"role": "assistant", "content": "final"}],
            changed_files=[],
            workspace=workspace,
        )
        await session.commit()

    async with maker() as session:
        history = await list_checkpoints(session, "tenant-a", run_id="run-a")
    await engine.dispose()

    assert len(history) == 1
    assert history[0].messages == [{"role": "assistant", "content": "final"}]


async def test_upsert_checkpoint_snapshot_integrity_retry_updates_existing_scope(
    checkpoint_session, tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    await upsert_checkpoint_snapshot(
        checkpoint_session,
        tenant_id="tenant-a",
        conversation_id="conversation-a",
        run_id="run-a",
        step=5,
        goal="existing",
        messages=[{"role": "assistant", "content": "existing"}],
        changed_files=[],
        workspace=workspace,
    )

    original_select = sa.select
    calls = 0

    def stale_first_select(*args, **kwargs):
        nonlocal calls
        stmt = original_select(*args, **kwargs)
        if calls == 0:
            calls += 1
            return stmt.where(sa.text("0 = 1"))
        calls += 1
        return stmt

    monkeypatch.setattr("xagent.domains.checkpoints.service.select", stale_first_select)

    record, replaced = await upsert_checkpoint_snapshot(
        checkpoint_session,
        tenant_id="tenant-a",
        conversation_id="conversation-a",
        run_id="run-a",
        step=5,
        goal="retried",
        messages=[{"role": "assistant", "content": "retried"}],
        changed_files=[],
        workspace=workspace,
    )
    await checkpoint_session.commit()
    history = await list_checkpoints(checkpoint_session, "tenant-a", run_id="run-a")

    assert replaced is True
    assert record.messages == [{"role": "assistant", "content": "retried"}]
    assert len(history) == 1
    assert history[0].messages == [{"role": "assistant", "content": "retried"}]


async def test_upsert_checkpoint_snapshot_rejects_oversized_payload(
    checkpoint_session, tmp_path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    large_payload = {"items": list(range(100_000))}

    with pytest.raises(ValueError, match="checkpoint_messages_too_large"):
        await upsert_checkpoint_snapshot(
            checkpoint_session,
            tenant_id="tenant-a",
            conversation_id="conversation-a",
            run_id="run-a",
            step=5,
            goal="too large",
            messages=[{"role": "assistant", "content": "large", "payload": large_payload}],
            changed_files=[],
            workspace=workspace,
        )
