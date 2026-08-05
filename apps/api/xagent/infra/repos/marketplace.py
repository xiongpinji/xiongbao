"""市场条目 repository：同步持久化（供 marketplace 路由使用）。

路由对调用方暴露同步语义（原内存实现即同步），底层走同步 SQLAlchemy
（infra.repos.sync_db）。DB 不可用时抛异常，由路由降级为内存实现。
"""

from __future__ import annotations

import json

from sqlalchemy import func, select

from xagent.infra.models.marketplace import MarketEntryORM
from xagent.infra.repos.sync_db import sync_session


def _row_to_dict(r: MarketEntryORM) -> dict:
    return {
        "entry_id": r.entry_id,
        "name": r.name,
        "description": r.description,
        "author": r.author,
        "tenant_id": r.tenant_id,
        "version": r.version,
        "tags": json.loads(r.tags) if r.tags else [],
        "downloads": r.downloads,
        "rating": r.rating,
        "rating_count": r.rating_count,
        "skill_id": r.skill_id,
        "published_at": r.published_at,
        "updated_at": r.updated_at,
        "status": r.status,
    }


def table_empty_sync() -> bool:
    with sync_session() as s:
        cnt = s.execute(select(func.count()).select_from(MarketEntryORM)).scalar_one()
        return cnt == 0


def seed_entries_sync(entries: list[dict]) -> None:
    """批量插入种子条目（仅在表为空时由路由层调用）。"""
    with sync_session() as s:
        for e in entries:
            s.add(
                MarketEntryORM(
                    entry_id=e["entry_id"],
                    name=e["name"],
                    description=e["description"],
                    author=e["author"],
                    tenant_id=e["tenant_id"],
                    version=e["version"],
                    tags=json.dumps(e["tags"], ensure_ascii=False),
                    downloads=e["downloads"],
                    rating=e["rating"],
                    rating_count=e["rating_count"],
                    skill_id=e["skill_id"],
                    published_at=e["published_at"],
                    updated_at=e["updated_at"],
                    status=e["status"],
                )
            )


def list_entries_sync(*, q: str = "", tag: str = "", sort: str = "downloads") -> list[dict]:
    """返回过滤+排序后的全部 published 条目（分页由路由层切片）。"""
    with sync_session() as s:
        rows = (
            s.execute(select(MarketEntryORM).where(MarketEntryORM.status == "published"))
            .scalars()
            .all()
        )
        entries = [_row_to_dict(r) for r in rows]
    if q:
        q_lower = q.lower()
        entries = [
            e
            for e in entries
            if q_lower in e["name"].lower() or q_lower in e["description"].lower()
        ]
    if tag:
        entries = [e for e in entries if tag in e["tags"]]
    if sort == "rating":
        entries.sort(key=lambda e: e["rating"], reverse=True)
    elif sort == "newest":
        entries.sort(key=lambda e: e["published_at"], reverse=True)
    else:
        entries.sort(key=lambda e: e["downloads"], reverse=True)
    return entries


def get_entry_sync(entry_id: str) -> dict | None:
    with sync_session() as s:
        row = s.get(MarketEntryORM, entry_id)
        return _row_to_dict(row) if row else None


def create_entry_sync(entry: dict) -> dict:
    seed_entries_sync([entry])
    return entry


def increment_downloads_sync(entry_id: str) -> dict | None:
    with sync_session() as s:
        row = s.get(MarketEntryORM, entry_id)
        if row is None:
            return None
        row.downloads += 1
        s.flush()
        return _row_to_dict(row)


def add_rating_sync(entry_id: str, score: float) -> dict | None:
    with sync_session() as s:
        row = s.get(MarketEntryORM, entry_id)
        if row is None:
            return None
        total = row.rating * row.rating_count + score
        row.rating_count += 1
        row.rating = total / row.rating_count
        s.flush()
        return _row_to_dict(row)


def update_version_sync(
    entry_id: str, *, version: str, description: str, updated_at: float
) -> dict | None:
    with sync_session() as s:
        row = s.get(MarketEntryORM, entry_id)
        if row is None:
            return None
        row.version = version
        row.updated_at = updated_at
        if description:
            row.description = description
        s.flush()
        return _row_to_dict(row)


def revoke_entry_sync(entry_id: str) -> bool:
    with sync_session() as s:
        row = s.get(MarketEntryORM, entry_id)
        if row is None:
            return False
        row.status = "revoked"
        return True
