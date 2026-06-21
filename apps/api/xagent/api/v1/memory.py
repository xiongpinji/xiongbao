"""记忆路由：写入 / 检索。严格按 principal.tenant_id 隔离，调用方不能跨租户。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from xagent.adapters.memory import MemoryRecord, get_vector_store
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/memory", tags=["memory"])


class WriteItem(BaseModel):
    id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    metadata: dict = Field(default_factory=dict)


class WriteRequest(BaseModel):
    items: list[WriteItem]


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)


@router.post("", summary="写入记忆（自动绑定当前租户）")
async def write(
    body: WriteRequest,
    principal: Principal = Depends(require_permission("memory", "write")),
) -> dict:
    store = get_vector_store()
    records = [
        MemoryRecord(
            id=item.id,
            text=item.text,
            # 强制覆盖 tenant_id，禁止从 body 注入他人租户
            metadata={**item.metadata, "tenant_id": principal.tenant_id},
        )
        for item in body.items
    ]
    await store.upsert(records)
    return {"written": [r.id for r in records], "tenant_id": principal.tenant_id}


@router.post("/search", summary="语义检索（仅当前租户）")
async def search(
    body: SearchRequest,
    principal: Principal = Depends(require_permission("memory", "read")),
) -> dict:
    hits = await get_vector_store().search(
        body.query, top_k=body.top_k, tenant_id=principal.tenant_id
    )
    return {
        "hits": [
            {"id": h.id, "text": h.text, "score": h.score, "metadata": h.metadata}
            for h in hits
        ]
    }
