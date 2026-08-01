"""API 批量操作：Bulk Create / Update / Delete。

减少网络往返，一次请求处理多条记录：
- POST /api/v1/bulk/{resource}  批量创建
- PATCH /api/v1/bulk/{resource} 批量更新
- DELETE /api/v1/bulk/{resource} 批量删除

响应格式：
{
  "total": 10,
  "succeeded": 9,
  "failed": 1,
  "results": [{"index": 0, "ok": true, "id": "..."}, ...]
}
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/bulk", tags=["system"])

# 单次批量上限
MAX_BATCH_SIZE = 100


class BulkItem(BaseModel):
    """单条操作数据。"""

    id: str | None = None  # 更新/删除时必填
    data: dict[str, Any] = Field(default_factory=dict)


class BulkRequest(BaseModel):
    """批量请求体。"""

    items: list[BulkItem] = Field(..., min_length=1, max_length=MAX_BATCH_SIZE)


class BulkResultItem(BaseModel):
    """单条结果。"""

    index: int
    ok: bool
    id: str | None = None
    error: str | None = None


class BulkResponse(BaseModel):
    """批量响应。"""

    total: int
    succeeded: int
    failed: int
    results: list[BulkResultItem]
    elapsed_ms: float


# 内存存储（演示用，生产接 DB）
_bulk_stores: dict[str, dict[str, dict]] = {}


def _get_store(resource: str) -> dict[str, dict]:
    if resource not in _bulk_stores:
        _bulk_stores[resource] = {}
    return _bulk_stores[resource]


@router.post("/{resource}", summary="批量创建", response_model=BulkResponse)
async def bulk_create(
    resource: str,
    body: BulkRequest,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    start = time.perf_counter()
    store = _get_store(resource)
    results: list[BulkResultItem] = []

    for i, item in enumerate(body.items):
        try:
            record_id = item.id or f"{resource}_{int(time.time()*1000)}_{i}"
            store[record_id] = {**item.data, "_id": record_id, "_created_at": time.time()}
            results.append(BulkResultItem(index=i, ok=True, id=record_id))
        except Exception as e:
            results.append(BulkResultItem(index=i, ok=False, error=str(e)[:200]))

    succeeded = sum(1 for r in results if r.ok)
    return BulkResponse(
        total=len(body.items),
        succeeded=succeeded,
        failed=len(body.items) - succeeded,
        results=results,
        elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
    )


@router.patch("/{resource}", summary="批量更新", response_model=BulkResponse)
async def bulk_update(
    resource: str,
    body: BulkRequest,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    start = time.perf_counter()
    store = _get_store(resource)
    results: list[BulkResultItem] = []

    for i, item in enumerate(body.items):
        if not item.id:
            results.append(BulkResultItem(index=i, ok=False, error="缺少 id"))
            continue
        if item.id not in store:
            results.append(BulkResultItem(index=i, ok=False, error=f"记录不存在: {item.id}"))
            continue
        try:
            store[item.id].update(item.data)
            store[item.id]["_updated_at"] = time.time()
            results.append(BulkResultItem(index=i, ok=True, id=item.id))
        except Exception as e:
            results.append(BulkResultItem(index=i, ok=False, error=str(e)[:200]))

    succeeded = sum(1 for r in results if r.ok)
    return BulkResponse(
        total=len(body.items),
        succeeded=succeeded,
        failed=len(body.items) - succeeded,
        results=results,
        elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
    )


@router.delete("/{resource}", summary="批量删除", response_model=BulkResponse)
async def bulk_delete(
    resource: str,
    body: BulkRequest,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    start = time.perf_counter()
    store = _get_store(resource)
    results: list[BulkResultItem] = []

    for i, item in enumerate(body.items):
        if not item.id:
            results.append(BulkResultItem(index=i, ok=False, error="缺少 id"))
            continue
        if item.id not in store:
            results.append(BulkResultItem(index=i, ok=False, error=f"记录不存在: {item.id}"))
            continue
        del store[item.id]
        results.append(BulkResultItem(index=i, ok=True, id=item.id))

    succeeded = sum(1 for r in results if r.ok)
    return BulkResponse(
        total=len(body.items),
        succeeded=succeeded,
        failed=len(body.items) - succeeded,
        results=results,
        elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
    )
