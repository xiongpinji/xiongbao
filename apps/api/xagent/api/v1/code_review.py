"""Code Review 路由（对标 Codex Code Review）。强鉴权 + RBAC + 租户隔离 + 审计。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from xagent.domains.code_review import get_review, review_diff, save_review
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/code-review", tags=["code-review"])


class ReviewOptions(BaseModel):
    max_files: int = Field(10, ge=1, le=50)


class CodeReviewIn(BaseModel):
    diff: str | None = Field(None, description="直接粘贴的 unified diff 文本")
    repo: str | None = Field(None, description="本地仓库路径（跑 git diff + 加载 AGENTS.md）")
    base: str | None = Field(None, description="基准 ref（与 repo 搭配）")
    head: str = Field("HEAD", description="目标 ref")
    options: ReviewOptions = Field(default_factory=ReviewOptions)


@router.post("", summary="代码评审：diff 或 repo+base..head")
async def create_review(
    body: CodeReviewIn,
    principal: Principal = Depends(require_permission("code_review", "execute")),
) -> dict:
    if not (body.diff or "").strip() and not (body.repo and body.base):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "必须提供 diff 文本，或 repo + base",
        )
    try:
        result = await review_diff(
            diff=body.diff,
            repo=body.repo,
            base=body.base,
            head=body.head,
            max_files=body.options.max_files,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    save_review(result, principal.tenant_id)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="code_review.run",
        resource="code_review",
        detail={
            "review_id": result.review_id,
            "verdict": result.verdict,
            "status": result.status,
            "findings": len(result.findings),
            "source": "diff" if (body.diff or "").strip() else "git",
        },
    )
    return {"review_id": result.review_id, "status": result.status, "result": result.to_dict()}


@router.get("/{review_id}", summary="查询评审结果")
async def read_review(
    review_id: str,
    principal: Principal = Depends(require_permission("code_review", "read")),
) -> dict:
    result = get_review(review_id, principal.tenant_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "评审不存在")
    return {"review_id": result.review_id, "status": result.status, "result": result.to_dict()}
