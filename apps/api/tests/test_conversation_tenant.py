"""会话缓存和数据库消息必须显式按租户隔离。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from xagent.core.orchestration.conversation import (
    ConversationManager,
    ConversationSession,
    delete_conversation_from_db,
    load_messages_from_db,
    persist_conversation,
    persist_message,
)
from xagent.infra.db import Base


@pytest.fixture
async def conversation_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'conversations.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def test_database_messages_and_delete_are_tenant_scoped(
    conversation_session,
) -> None:
    conversation = ConversationSession("conversation-shared", "tenant-a")
    conversation.add_user("tenant A secret")
    await persist_conversation(conversation_session, conversation)
    await persist_message(
        conversation_session, conversation.conversation_id, "user", "tenant A secret"
    )
    await conversation_session.commit()

    assert await load_messages_from_db(
        conversation_session, "tenant-b", conversation.conversation_id
    ) == []
    assert not await delete_conversation_from_db(
        conversation_session, "tenant-b", conversation.conversation_id
    )
    assert await load_messages_from_db(
        conversation_session, "tenant-a", conversation.conversation_id
    ) == [{"role": "user", "content": "tenant A secret"}]


def test_cached_conversation_rejects_cross_tenant_reuse_and_delete() -> None:
    manager = ConversationManager()
    original = manager.get_or_create("conversation-shared", "tenant-a")

    with pytest.raises(LookupError, match="conversation-shared"):
        manager.get_or_create("conversation-shared", "tenant-b")
    assert manager.get("conversation-shared", "tenant-b") is None
    assert not manager.delete("conversation-shared", "tenant-b")
    assert manager.get("conversation-shared", "tenant-a") is original
