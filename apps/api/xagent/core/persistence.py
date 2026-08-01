"""SQLite 持久化层 — 知识库/Webhook/审计跨重启保留。

使用 aiosqlite 异步驱动，自动建表，零配置。
数据库文件: {DATA_DIR}/xagent.db
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DB_PATH = _DATA_DIR / "xagent.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_docs (
    doc_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT DEFAULT 'manual',
    chunk_count INTEGER DEFAULT 0,
    tags TEXT DEFAULT '[]',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    text TEXT NOT NULL,
    idx INTEGER DEFAULT 0,
    FOREIGN KEY (doc_id) REFERENCES knowledge_docs(doc_id)
);

CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    url TEXT NOT NULL,
    events TEXT DEFAULT '[]',
    secret TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT DEFAULT '',
    detail TEXT DEFAULT '{}',
    ts REAL NOT NULL
);
"""


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接（自动建表）。"""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.executescript(_SCHEMA)
    return db


# ─── 知识库 ────────────────────────────────────────────────


async def save_document(doc: dict[str, Any]) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO knowledge_docs "
            "(doc_id, tenant_id, title, source, chunk_count, tags, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                doc["doc_id"],
                doc["tenant_id"],
                doc["title"],
                doc.get("source", "manual"),
                doc.get("chunk_count", 0),
                json.dumps(doc.get("tags", []), ensure_ascii=False),
                doc.get("created_at", time.time()),
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def save_chunks(doc_id: str, tenant_id: str, chunks: list[str]) -> None:
    db = await get_db()
    try:
        for i, text in enumerate(chunks):
            chunk_id = f"{doc_id}_{i}"
            await db.execute(
                "INSERT OR REPLACE INTO knowledge_chunks "
                "(chunk_id, doc_id, tenant_id, text, idx) VALUES (?, ?, ?, ?, ?)",
                (chunk_id, doc_id, tenant_id, text, i),
            )
        await db.commit()
    finally:
        await db.close()


async def load_documents(tenant_id: str) -> list[dict[str, Any]]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM knowledge_docs WHERE tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "doc_id": r["doc_id"],
                "tenant_id": r["tenant_id"],
                "title": r["title"],
                "source": r["source"],
                "chunk_count": r["chunk_count"],
                "tags": json.loads(r["tags"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        await db.close()


async def delete_document(doc_id: str) -> None:
    db = await get_db()
    try:
        await db.execute("DELETE FROM knowledge_chunks WHERE doc_id = ?", (doc_id,))
        await db.execute("DELETE FROM knowledge_docs WHERE doc_id = ?", (doc_id,))
        await db.commit()
    finally:
        await db.close()


# ─── Webhook ───────────────────────────────────────────────


async def save_webhook(hook: dict[str, Any]) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO webhooks "
            "(webhook_id, tenant_id, url, events, secret, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                hook["webhook_id"],
                hook["tenant_id"],
                hook["url"],
                json.dumps(hook.get("events", [])),
                hook.get("secret", ""),
                1 if hook.get("enabled", True) else 0,
                hook.get("created_at", time.time()),
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def load_webhooks(tenant_id: str) -> list[dict[str, Any]]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM webhooks WHERE tenant_id = ? AND enabled = 1",
            (tenant_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "webhook_id": r["webhook_id"],
                "tenant_id": r["tenant_id"],
                "url": r["url"],
                "events": json.loads(r["events"]),
                "secret": r["secret"],
                "enabled": bool(r["enabled"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        await db.close()


async def delete_webhook(webhook_id: str) -> None:
    db = await get_db()
    try:
        await db.execute("DELETE FROM webhooks WHERE webhook_id = ?", (webhook_id,))
        await db.commit()
    finally:
        await db.close()


# ─── 审计 ──────────────────────────────────────────────────


async def save_audit_event(
    tenant_id: str, action: str, actor: str = "", detail: dict | None = None
) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO audit_events (tenant_id, action, actor, detail, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (tenant_id, action, actor, json.dumps(detail or {}, ensure_ascii=False), time.time()),
        )
        await db.commit()
    finally:
        await db.close()


async def load_audit_events(
    tenant_id: str, *, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM audit_events WHERE tenant_id = ? ORDER BY ts DESC LIMIT ? OFFSET ?",
            (tenant_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "action": r["action"],
                "actor": r["actor"],
                "detail": json.loads(r["detail"]),
                "ts": r["ts"],
            }
            for r in rows
        ]
    finally:
        await db.close()
