"""会话管理：DB 持久化 + 进程内缓存。

所有会话和消息持久化到 SQLite（conversations / conversation_messages 表），
重启不丢失。进程内维护轻量缓存加速读取。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from xagent.adapters.llm import Message

# 每个会话最多保留的消息数
_MAX_MESSAGES = 80


@dataclass
class ConversationSession:
    conversation_id: str
    tenant_id: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    title: str = ""

    def add_user(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))
        if not self.title:
            self.title = content[:50] + ("..." if len(content) > 50 else "")
        self._trim()
        self.last_active = time.time()

    def add_assistant(self, content: str) -> None:
        self.messages.append(Message(role="assistant", content=content))
        self._trim()
        self.last_active = time.time()

    def get_history(self, max_turns: int = 10) -> list[Message]:
        relevant = [m for m in self.messages if m.role in ("user", "assistant")]
        return relevant[-(max_turns * 2):]

    def _trim(self) -> None:
        if len(self.messages) > _MAX_MESSAGES:
            self.messages = self.messages[-_MAX_MESSAGES:]


class ConversationManager:
    """DB 持久化会话管理器。"""

    def __init__(self) -> None:
        self._cache: dict[str, ConversationSession] = {}

    def get_or_create(self, conversation_id: str | None, tenant_id: str) -> ConversationSession:
        if conversation_id and conversation_id in self._cache:
            session = self._cache[conversation_id]
            if session.tenant_id != tenant_id:
                raise LookupError(conversation_id)
            return session

        cid = conversation_id or uuid.uuid4().hex
        session = ConversationSession(conversation_id=cid, tenant_id=tenant_id)
        self._cache[cid] = session
        return session

    def get(
        self, conversation_id: str, tenant_id: str | None = None
    ) -> ConversationSession | None:
        session = self._cache.get(conversation_id)
        if session is None or (tenant_id is not None and session.tenant_id != tenant_id):
            return None
        return session

    def list_sessions(self, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """同步列出缓存中的会话（API 层会调用异步 DB 版本）。"""
        results: list[dict[str, Any]] = []
        for _sid, sess in self._cache.items():
            if sess.tenant_id != tenant_id:
                continue
            msg_count = len([m for m in sess.messages if m.role in ("user", "assistant")])
            results.append({
                "conversation_id": sess.conversation_id,
                "title": sess.title or "新对话",
                "message_count": msg_count,
                "created_at": sess.created_at,
                "last_active": sess.last_active,
            })
        results.sort(key=lambda x: float(x["last_active"]), reverse=True)
        return results[:limit]

    def delete(self, conversation_id: str, tenant_id: str | None = None) -> bool:
        session = self._cache.get(conversation_id)
        if session is not None and (
            tenant_id is None or session.tenant_id == tenant_id
        ):
            del self._cache[conversation_id]
            return True
        return False

    def restore(self, session: ConversationSession) -> None:
        existing = self._cache.get(session.conversation_id)
        if existing is not None and existing.tenant_id != session.tenant_id:
            raise LookupError(session.conversation_id)
        self._cache[session.conversation_id] = session


# ─── 异步 DB 持久化操作 ───


async def persist_conversation(session_db, conv: ConversationSession) -> None:
    """将会话元数据写入 DB。"""
    from sqlalchemy import select

    from xagent.infra.models.conversation import ConversationORM

    stmt = select(ConversationORM).where(
        ConversationORM.conversation_id == conv.conversation_id
    )
    result = await session_db.execute(stmt)
    row = result.scalar_one_or_none()
    if row:
        if row.tenant_id != conv.tenant_id:
            raise ValueError("conversation_tenant_conflict")
        row.title = conv.title
        row.message_count = len(conv.messages)
    else:
        session_db.add(ConversationORM(
            conversation_id=conv.conversation_id,
            tenant_id=conv.tenant_id,
            title=conv.title,
            message_count=len(conv.messages),
        ))


async def persist_message(session_db, conversation_id: str, role: str, content: str) -> None:
    """将单条消息写入 DB。"""
    from xagent.infra.models.conversation import ConversationMessageORM

    session_db.add(ConversationMessageORM(
        conversation_id=conversation_id,
        role=role,
        content=content[:10000],  # 截断保护
    ))


async def load_conversations_from_db(
    session_db, tenant_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    """从 DB 加载会话列表。"""
    from sqlalchemy import select

    from xagent.infra.models.conversation import ConversationORM

    stmt = (
        select(ConversationORM)
        .where(ConversationORM.tenant_id == tenant_id)
        .order_by(ConversationORM.last_active.desc())
        .limit(limit)
    )
    result = await session_db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "conversation_id": r.conversation_id,
            "title": r.title or "新对话",
            "message_count": r.message_count,
            "created_at": r.created_at.timestamp() if r.created_at else 0,
            "last_active": r.last_active.timestamp() if r.last_active else 0,
        }
        for r in rows
    ]


async def load_messages_from_db(
    session_db, tenant_id: str, conversation_id: str, limit: int = 100
) -> list[dict[str, str]]:
    """从 DB 加载某会话的消息。"""
    from sqlalchemy import select

    from xagent.infra.models.conversation import ConversationMessageORM, ConversationORM

    stmt = (
        select(ConversationMessageORM)
        .join(
            ConversationORM,
            ConversationORM.conversation_id == ConversationMessageORM.conversation_id,
        )
        .where(
            ConversationORM.tenant_id == tenant_id,
            ConversationMessageORM.conversation_id == conversation_id,
        )
        .order_by(ConversationMessageORM.id.asc())
        .limit(limit)
    )
    result = await session_db.execute(stmt)
    rows = result.scalars().all()
    return [{"role": r.role, "content": r.content} for r in rows]


async def load_conversation_from_db(
    session_db, tenant_id: str, conversation_id: str
) -> ConversationSession | None:
    """恢复同租户会话；ID 已被其他租户占用时显式拒绝。"""
    from sqlalchemy import select

    from xagent.infra.models.conversation import ConversationORM

    row = await session_db.scalar(
        select(ConversationORM).where(
            ConversationORM.conversation_id == conversation_id
        )
    )
    if row is None:
        return None
    if row.tenant_id != tenant_id:
        raise LookupError(conversation_id)
    restored = ConversationSession(
        conversation_id=row.conversation_id,
        tenant_id=row.tenant_id,
        created_at=row.created_at.timestamp() if row.created_at else time.time(),
        last_active=row.last_active.timestamp() if row.last_active else time.time(),
        title=row.title,
    )
    messages = await load_messages_from_db(session_db, tenant_id, conversation_id)
    restored.messages = [
        Message(role=item["role"], content=item["content"]) for item in messages
    ]
    return restored


async def delete_conversation_from_db(
    session_db, tenant_id: str, conversation_id: str
) -> bool:
    """从 DB 删除会话及其消息。"""
    from sqlalchemy import delete

    from xagent.infra.models.conversation import ConversationMessageORM, ConversationORM

    result = await session_db.execute(
        delete(ConversationORM).where(
            ConversationORM.tenant_id == tenant_id,
            ConversationORM.conversation_id == conversation_id,
        )
    )
    if result.rowcount <= 0:
        return False
    await session_db.execute(
        delete(ConversationMessageORM).where(
            ConversationMessageORM.conversation_id == conversation_id
        )
    )
    return True


# 全局单例
_manager: ConversationManager | None = None


def get_conversation_manager() -> ConversationManager:
    global _manager
    if _manager is None:
        _manager = ConversationManager()
    return _manager
