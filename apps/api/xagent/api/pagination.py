"""游标分页：Cursor-based Pagination。

比 offset 分页更适合大数据量 / 实时数据：
- 基于游标（cursor）而非偏移量
- 支持正向/反向翻页
- 返回 has_next / has_prev 标识

用法：
    GET /api/v1/items?limit=20&cursor=eyJpZCI6MTAwfQ
    GET /api/v1/items?limit=20&cursor=xxx&direction=prev

响应：
{
  "data": [...],
  "pagination": {
    "limit": 20,
    "has_next": true,
    "has_prev": true,
    "next_cursor": "eyJpZCI6MTIwfQ",
    "prev_cursor": "eyJpZCI6MTAwfQ"
  }
}
"""

from __future__ import annotations

import base64
import json
from typing import Any, Sequence

from pydantic import BaseModel


class CursorPagination(BaseModel):
    """分页元数据。"""

    limit: int
    has_next: bool
    has_prev: bool
    next_cursor: str | None = None
    prev_cursor: str | None = None


class PaginatedResponse(BaseModel):
    """分页响应。"""

    data: list[Any]
    pagination: CursorPagination


def encode_cursor(data: dict) -> str:
    """编码游标（base64 JSON）。"""
    raw = json.dumps(data, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> dict | None:
    """解码游标。"""
    if not cursor:
        return None
    try:
        # 补齐 padding
        padding = 4 - len(cursor) % 4
        if padding != 4:
            cursor += "=" * padding
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(raw)
    except Exception:
        return None


def paginate(
    items: Sequence[Any],
    limit: int = 20,
    cursor: str | None = None,
    direction: str = "next",
    id_field: str = "id",
) -> PaginatedResponse:
    """对列表执行游标分页。

    Args:
        items: 完整数据列表（已排序）
        limit: 每页条数
        cursor: 游标字符串
        direction: "next" 或 "prev"
        id_field: 用作游标的字段名
    """
    limit = min(max(1, limit), 100)  # 限制 1-100

    # 解码游标获取起始位置
    cursor_data = decode_cursor(cursor)
    start_index = 0

    if cursor_data:
        cursor_id = cursor_data.get("id")
        # 查找游标位置
        for i, item in enumerate(items):
            item_id = item.get(id_field) if isinstance(item, dict) else getattr(item, id_field, None)
            if item_id == cursor_id:
                start_index = i + 1 if direction == "next" else max(0, i - limit)
                break

    # 切片
    if direction == "prev":
        end_index = start_index + limit
        page_items = list(items[start_index:end_index])
    else:
        page_items = list(items[start_index:start_index + limit])

    # 计算游标
    has_next = start_index + limit < len(items)
    has_prev = start_index > 0

    next_cursor = None
    prev_cursor = None

    if page_items:
        last_item = page_items[-1]
        first_item = page_items[0]
        last_id = last_item.get(id_field) if isinstance(last_item, dict) else getattr(last_item, id_field, None)
        first_id = first_item.get(id_field) if isinstance(first_item, dict) else getattr(first_item, id_field, None)

        if has_next and last_id is not None:
            next_cursor = encode_cursor({"id": last_id})
        if has_prev and first_id is not None:
            prev_cursor = encode_cursor({"id": first_id})

    return PaginatedResponse(
        data=page_items,
        pagination=CursorPagination(
            limit=limit,
            has_next=has_next,
            has_prev=has_prev,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        ),
    )
