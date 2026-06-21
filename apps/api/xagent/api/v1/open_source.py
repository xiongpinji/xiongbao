"""开源候选发现路由。强鉴权 + RBAC + 租户隔离 + 审计。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from xagent.domains.open_source_discovery import discover_and_rank
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/open-source", tags=["open-source"])


class DiscoverIn(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(10, ge=1, le=50)


@router.post("/discover", summary="多源候选发现 + 统一评分")
async def discover(
    body: DiscoverIn,
    principal: Principal = Depends(require_permission("open_source", "read")),
) -> dict:
    results = await discover_and_rank(body.query, limit=body.limit)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="open_source.discover",
        resource="open_source",
        detail={"query": body.query, "count": len(results)},
    )
    return {
        "query": body.query,
        "results": [
            {
                "name": s.candidate.name,
                "source": s.candidate.source,
                "url": s.candidate.url,
                "stars": s.candidate.stars,
                "license": s.candidate.license,
                "score": s.score,
                "breakdown": s.breakdown,
                "license_ok": s.license_ok,
                "notes": s.notes,
            }
            for s in results
        ],
    }
