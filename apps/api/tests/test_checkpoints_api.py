"""Checkpoint list/detail/resume/rollback API 契约。"""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.core.orchestration.conversation import (
    ConversationSession,
    persist_conversation,
    persist_message,
)
from xagent.domains.checkpoints import create_checkpoint
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.jwt_auth import create_access_token
from xagent.infra.db import Base, get_engine, get_sessionmaker
from xagent.main import create_app


def _headers(tenant_id: str) -> dict[str, str]:
    token = create_access_token(
        user_id=f"admin-{tenant_id}", tenant_id=tenant_id, roles=["admin"]
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def checkpoint_client(tmp_path, monkeypatch):
    from xagent.api.v1 import checkpoints as checkpoint_api

    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    async with get_sessionmaker()() as session:
        checkpoint = await create_checkpoint(
            session,
            tenant_id="tenant-checkpoint-a",
            conversation_id="conversation-checkpoint-a",
            run_id="run-checkpoint-a",
            step=5,
            goal="resume release validation",
            messages=[{"role": "user", "content": "continue safely"}],
            changed_files=[],
            workspace=workspace,
        )
        await session.commit()

    resumed: list[tuple[str, str]] = []

    async def fake_resume(record, principal) -> None:
        resumed.append((record.checkpoint_id, principal.tenant_id))

    monkeypatch.setattr(checkpoint_api, "_run_resumed_checkpoint", fake_resume)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, checkpoint, resumed, checkpoint_api


async def test_list_detail_resume_are_tenant_scoped_and_preserve_parent(
    checkpoint_client,
) -> None:
    client, checkpoint, resumed, _ = checkpoint_client
    own = await client.get(
        "/api/v1/checkpoints?conversation_id=conversation-checkpoint-a",
        headers=_headers("tenant-checkpoint-a"),
    )
    assert own.status_code == 200
    assert own.json()["checkpoints"][0]["checkpoint_id"] == checkpoint.checkpoint_id
    assert "messages" not in own.json()["checkpoints"][0]

    other = await client.get(
        f"/api/v1/checkpoints/{checkpoint.checkpoint_id}",
        headers=_headers("tenant-checkpoint-b"),
    )
    assert other.status_code == 404

    wrong_confirm = await client.post(
        f"/api/v1/checkpoints/{checkpoint.checkpoint_id}/resume",
        json={"confirm_checkpoint_id": "wrong"},
        headers=_headers("tenant-checkpoint-a"),
    )
    assert wrong_confirm.status_code == 409
    resumed_response = await client.post(
        f"/api/v1/checkpoints/{checkpoint.checkpoint_id}/resume",
        json={"confirm_checkpoint_id": checkpoint.checkpoint_id},
        headers=_headers("tenant-checkpoint-a"),
    )
    assert resumed_response.status_code == 202
    child = resumed_response.json()["checkpoint"]
    assert child["parent_checkpoint_id"] == checkpoint.checkpoint_id
    assert child["run_id"] != checkpoint.run_id
    assert resumed == [(child["checkpoint_id"], "tenant-checkpoint-a")]
    duplicate = await client.post(
        f"/api/v1/checkpoints/{checkpoint.checkpoint_id}/resume",
        json={"confirm_checkpoint_id": checkpoint.checkpoint_id},
        headers=_headers("tenant-checkpoint-a"),
    )
    assert duplicate.status_code == 409
    assert resumed == [(child["checkpoint_id"], "tenant-checkpoint-a")]
    events = get_audit_log().list("tenant-checkpoint-a")
    assert events[-1].action == "checkpoint.resume"


async def test_rollback_requires_exact_confirmation_and_writes_audit(
    checkpoint_client, monkeypatch
) -> None:
    client, checkpoint, _, checkpoint_api = checkpoint_client
    calls: list[tuple[str, str]] = []

    async def fake_rollback(session, **kwargs):
        calls.append((kwargs["checkpoint_id"], kwargs["source"]))
        return replace(
            checkpoint,
            status="rolled_back",
            rollback_source=kwargs["source"],
            rollback_commit="rollback-commit",
        )

    monkeypatch.setattr(checkpoint_api, "rollback_checkpoint", fake_rollback)
    response = await client.post(
        f"/api/v1/checkpoints/{checkpoint.checkpoint_id}/rollback",
        json={
            "confirm_checkpoint_id": checkpoint.checkpoint_id,
            "task_id": "development-task-a",
            "source": "commit",
        },
        headers=_headers("tenant-checkpoint-a"),
    )
    assert response.status_code == 200
    assert response.json()["checkpoint"]["rollback_commit"] == "rollback-commit"
    assert calls == [(checkpoint.checkpoint_id, "commit")]
    assert get_audit_log().list("tenant-checkpoint-a")[-1].action == "checkpoint.rollback"


async def test_conversation_message_delete_and_run_reject_other_tenant(
    checkpoint_client,
) -> None:
    client, _, _, _ = checkpoint_client
    conversation_id = f"conversation-{uuid.uuid4().hex}"
    conversation = ConversationSession(conversation_id, "tenant-checkpoint-a")
    conversation.add_user("tenant A only")
    async with get_sessionmaker()() as session:
        await persist_conversation(session, conversation)
        await persist_message(session, conversation_id, "user", "tenant A only")
        await session.commit()

    own = await client.get(
        f"/api/v1/stream/conversations/{conversation_id}/messages",
        headers=_headers("tenant-checkpoint-a"),
    )
    assert own.status_code == 200
    assert own.json()["messages"] == [{"role": "user", "content": "tenant A only"}]

    other_headers = _headers("tenant-checkpoint-b")
    other_read = await client.get(
        f"/api/v1/stream/conversations/{conversation_id}/messages",
        headers=other_headers,
    )
    other_delete = await client.delete(
        f"/api/v1/stream/conversations/{conversation_id}", headers=other_headers
    )
    other_run = await client.post(
        "/api/v1/stream/agents/run",
        json={"goal": "steal context", "conversation_id": conversation_id},
        headers=other_headers,
    )
    assert other_read.status_code == 404
    assert other_delete.status_code == 404
    assert other_run.status_code == 404
