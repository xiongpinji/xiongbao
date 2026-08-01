"""知识库 API：文档上传 / 检索 / 管理。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from xagent.core.knowledge import get_knowledge_base
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class IngestIn(BaseModel):
    text: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=256)
    source: str = "upload"
    content_type: str = "text/plain"
    tags: list[str] = Field(default_factory=list)


class SearchIn(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


@router.post("/ingest", summary="上传文档到知识库")
async def ingest_document(
    body: IngestIn,
    principal: Principal = Depends(require_permission("knowledge", "write")),
) -> dict:
    kb = get_knowledge_base()
    doc = await kb.ingest(
        text=body.text,
        title=body.title,
        tenant_id=principal.tenant_id,
        source=body.source,
        content_type=body.content_type,
        tags=body.tags,
    )
    return {"document": doc.to_dict()}


@router.post("/search", summary="语义检索知识库")
async def search_knowledge(
    body: SearchIn,
    principal: Principal = Depends(require_permission("knowledge", "read")),
) -> dict:
    kb = get_knowledge_base()
    results = await kb.search(body.query, principal.tenant_id, top_k=body.top_k)
    return {"results": results, "count": len(results)}


@router.get("/documents", summary="列出知识库文档")
async def list_documents(
    principal: Principal = Depends(require_permission("knowledge", "read")),
) -> dict:
    kb = get_knowledge_base()
    docs = [d.to_dict() for d in kb.list_docs(principal.tenant_id)]
    return {"documents": docs, "count": len(docs)}


@router.delete("/documents/{doc_id}", summary="删除知识库文档")
async def delete_document(
    doc_id: str,
    principal: Principal = Depends(require_permission("knowledge", "write")),
) -> dict:
    kb = get_knowledge_base()
    if not kb.delete_doc(doc_id, principal.tenant_id):
        raise HTTPException(404, "文档不存在")
    try:
        from xagent.core.persistence import delete_document as persist_delete
        await persist_delete(doc_id)
    except Exception:  # noqa: S110
        pass
    return {"deleted": doc_id}
