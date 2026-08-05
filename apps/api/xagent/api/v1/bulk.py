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

诚实化原则：批量操作直接作用于真实存储（SkillStore），
不支持的资源名返回 404，绝不做"内存演示存储"式假成功。
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from xagent.core.skills import get_skill_store
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/bulk", tags=["system"])

# 单次批量上限
MAX_BATCH_SIZE = 100

# 支持的资源白名单（只接真实存储，未接入的一律 404）
SUPPORTED_RESOURCES = ("skills",)


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


def _check_resource(resource: str) -> None:
    if resource not in SUPPORTED_RESOURCES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"不支持的批量资源: '{resource}'。"
                f"当前仅支持: {', '.join(SUPPORTED_RESOURCES)}"
            ),
        )


def _build_response(items: list[BulkItem], results: list[BulkResultItem], start: float) -> BulkResponse:
    succeeded = sum(1 for r in results if r.ok)
    return BulkResponse(
        total=len(items),
        succeeded=succeeded,
        failed=len(items) - succeeded,
        results=results,
        elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
    )


# ─── skills 资源的真实操作 ───


def _create_skill_item(item: BulkItem) -> tuple[str | None, str | None]:
    """创建单条技能，返回 (id, error)。"""
    name = str(item.data.get("name") or "").strip()
    trigger = str(item.data.get("trigger_pattern") or "").strip()
    if not name:
        return None, "缺少必填字段: name"
    if not trigger:
        return None, "缺少必填字段: trigger_pattern"
    skill = get_skill_store().create_skill(
        name=name,
        description=str(item.data.get("description") or ""),
        trigger_pattern=trigger,
        system_prompt_hint=str(item.data.get("system_prompt_hint") or ""),
        steps=list(item.data.get("steps") or []),
        tags=list(item.data.get("tags") or []),
        source="bulk",
    )
    return skill.skill_id, None


def _update_skill_item(item: BulkItem) -> tuple[str | None, str | None]:
    """更新单条技能（版本化 evolve），返回 (id, error)。"""
    if not item.id:
        return None, "缺少 id"
    store = get_skill_store()
    if not store.get(item.id):
        return None, f"记录不存在: {item.id}"
    allowed = {"description", "system_prompt_hint", "trigger_pattern", "steps"}
    unknown = set(item.data) - allowed
    if unknown:
        return None, f"不支持的更新字段: {', '.join(sorted(unknown))}"
    skill = store.evolve_skill(
        skill_id=item.id,
        description=item.data.get("description"),
        system_prompt_hint=item.data.get("system_prompt_hint"),
        trigger_pattern=item.data.get("trigger_pattern"),
        steps=item.data.get("steps"),
        change_reason="bulk update",
    )
    if not skill:
        return None, f"记录不存在: {item.id}"
    return skill.skill_id, None


def _delete_skill_item(item: BulkItem) -> tuple[str | None, str | None]:
    """删除单条技能，返回 (id, error)。"""
    if not item.id:
        return None, "缺少 id"
    if not get_skill_store().delete(item.id):
        return None, f"记录不存在: {item.id}"
    return item.id, None


@router.post("/{resource}", summary="批量创建", response_model=BulkResponse)
async def bulk_create(
    resource: str,
    body: BulkRequest,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    _check_resource(resource)
    start = time.perf_counter()
    results: list[BulkResultItem] = []

    for i, item in enumerate(body.items):
        try:
            record_id, error = _create_skill_item(item)
            results.append(BulkResultItem(index=i, ok=error is None, id=record_id, error=error))
        except Exception as e:
            results.append(BulkResultItem(index=i, ok=False, error=str(e)[:200]))

    return _build_response(body.items, results, start)


@router.patch("/{resource}", summary="批量更新", response_model=BulkResponse)
async def bulk_update(
    resource: str,
    body: BulkRequest,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    _check_resource(resource)
    start = time.perf_counter()
    results: list[BulkResultItem] = []

    for i, item in enumerate(body.items):
        try:
            record_id, error = _update_skill_item(item)
            results.append(BulkResultItem(index=i, ok=error is None, id=record_id, error=error))
        except Exception as e:
            results.append(BulkResultItem(index=i, ok=False, id=item.id, error=str(e)[:200]))

    return _build_response(body.items, results, start)


@router.delete("/{resource}", summary="批量删除", response_model=BulkResponse)
async def bulk_delete(
    resource: str,
    body: BulkRequest,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    _check_resource(resource)
    start = time.perf_counter()
    results: list[BulkResultItem] = []

    for i, item in enumerate(body.items):
        try:
            record_id, error = _delete_skill_item(item)
            results.append(BulkResultItem(index=i, ok=error is None, id=record_id, error=error))
        except Exception as e:
            results.append(BulkResultItem(index=i, ok=False, id=item.id, error=str(e)[:200]))

    return _build_response(body.items, results, start)
