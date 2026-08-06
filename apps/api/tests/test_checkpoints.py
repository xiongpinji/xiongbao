"""数据库 checkpoint 的租户、父子关系与脱敏门禁。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from xagent.domains.checkpoints import (
    create_checkpoint,
    create_resume_checkpoint,
    get_checkpoint,
    list_checkpoints,
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
