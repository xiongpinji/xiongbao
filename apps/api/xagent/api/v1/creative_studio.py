"""短剧工厂路由：一句话→草稿、草稿审阅、质量门。强鉴权 + RBAC + 租户隔离。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from xagent.domains.creative_studio import build_draft_from_brief
from xagent.domains.creative_studio.media import (
    GenerationMode,
    GenerationRequest,
    MediaKind,
    get_media_registry,
)
from xagent.domains.creative_studio.pipeline import produce_short_drama
from xagent.domains.creative_studio.producer import generate_storyboard
from xagent.domains.creative_studio.quality import run_gates
from xagent.domains.creative_studio.storyboard import Storyboard
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/creative-studio", tags=["creative-studio"])

# 进程内草稿存储（Phase 5 落库）；按租户隔离
_drafts: dict[str, dict] = {}
# 进程内成片产物存储；按租户隔离
_productions: dict[str, dict] = {}


class BriefIn(BaseModel):
    brief: str = Field(..., min_length=1)
    genre: str = "逆袭"
    platform: str = "抖音"
    target_duration_seconds: float = 60.0


class ReviewIn(BaseModel):
    approved: bool
    comment: str = ""


@router.post("/workflow-draft", summary="一句话生成待审核工作流草稿")
async def create_draft(
    body: BriefIn,
    principal: Principal = Depends(require_permission("creative", "write")),
) -> dict:
    draft = build_draft_from_brief(
        body.brief,
        genre=body.genre,
        platform=body.platform,
        target_duration_seconds=body.target_duration_seconds,
    )
    doc = draft.to_dict()
    doc["tenant_id"] = principal.tenant_id
    doc["owner"] = principal.user_id
    _drafts[draft.draft_id] = doc
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.draft",
        resource="creative",
        detail={"draft_id": draft.draft_id, "genre": body.genre},
    )
    return doc


@router.post("/workflow-draft/{draft_id}/review", summary="审核草稿（通过/驳回）")
async def review_draft(
    draft_id: str,
    body: ReviewIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    doc = _drafts.get(draft_id)
    if doc is None or doc.get("tenant_id") != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "草稿不存在或无权访问")
    doc["status"] = "approved" if body.approved else "rejected"
    doc["review_comment"] = body.comment
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.review",
        resource="creative",
        detail={"draft_id": draft_id, "approved": body.approved},
    )
    return doc


@router.get("/workflow-drafts", summary="列出当前租户草稿")
async def list_drafts(
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    items = [d for d in _drafts.values() if d.get("tenant_id") == principal.tenant_id]
    return {"drafts": items}


@router.post("/quality-gates", summary="对故事板运行质量门")
async def quality_gates(
    sb: Storyboard,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    gates = run_gates(sb)
    return {
        "all_passed": all(g.passed for g in gates),
        "gates": [g.model_dump() for g in gates],
    }


@router.post("/storyboard/generate", summary="LLM 生成结构化故事板")
async def gen_storyboard(
    body: BriefIn,
    principal: Principal = Depends(require_permission("creative", "write")),
) -> dict:
    sb = await generate_storyboard(
        body.brief,
        genre=body.genre,
        platform=body.platform,
        target_duration_seconds=body.target_duration_seconds,
    )
    gates = run_gates(sb)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.storyboard",
        resource="creative",
        detail={"shots": len(sb.shots), "all_passed": all(g.passed for g in gates)},
    )
    return {
        "storyboard": sb.model_dump(),
        "quality_gates": {
            "all_passed": all(g.passed for g in gates),
            "gates": [g.model_dump() for g in gates],
        },
    }


class MediaGenIn(BaseModel):
    kind: str = "image"  # image | video
    prompt: str = Field(..., min_length=1)
    mode: str = "text_to_image"  # text_to_image|image_to_image|text_to_video|image_to_video
    model_id: str | None = None
    reference_images: list[str] = Field(default_factory=list)
    duration_seconds: float | None = None
    resolution: str | None = None
    wait: bool = False  # True 则轮询直到完成


@router.get("/media/models", summary="列出可用媒体生成模型(图像/视频)")
async def media_models(
    kind: str | None = None,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    mk = MediaKind(kind) if kind else None
    cards = get_media_registry().list_models(mk)
    return {
        "models": [
            {
                "model_id": c.model_id,
                "name": c.name,
                "kind": c.kind.value,
                "provider": c.provider,
                "modes": [m.value for m in c.modes],
                "description": c.description,
                "max_duration_seconds": c.max_duration_seconds,
                "resolutions": c.resolutions,
            }
            for c in cards
        ]
    }


@router.post("/media/generate", summary="媒体生成(文生图/图生图/文生视频/图生视频)")
async def media_generate(
    body: MediaGenIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    req = GenerationRequest(
        kind=MediaKind(body.kind),
        prompt=body.prompt,
        mode=GenerationMode(body.mode),
        model_id=body.model_id,
        reference_images=body.reference_images,
        duration_seconds=body.duration_seconds,
        resolution=body.resolution,
    )
    task = await get_media_registry().generate(req, wait=body.wait)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.media_generate",
        resource="creative",
        detail={"kind": body.kind, "mode": body.mode, "provider": task.provider},
    )
    return {
        "task_id": task.task_id,
        "provider": task.provider,
        "status": task.status,
        "outputs": task.outputs,
        "error": task.error,
    }


class ProduceIn(BaseModel):
    brief: str = Field(..., min_length=1)
    genre: str = "逆袭"
    platform: str = "抖音"
    target_duration_seconds: float = 60.0
    with_video: bool = True


@router.post("/produce", summary="短剧全链路产出(故事板→关键帧→视频→质量门)")
async def produce(
    body: ProduceIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    result = await produce_short_drama(
        body.brief,
        genre=body.genre,
        platform=body.platform,
        target_duration_seconds=body.target_duration_seconds,
        with_video=body.with_video,
    )
    doc = result.to_dict()
    doc["tenant_id"] = principal.tenant_id
    doc["owner"] = principal.user_id
    _productions[result.storyboard_id] = doc
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.produce",
        resource="creative",
        detail={
            "storyboard_id": result.storyboard_id,
            "shots": len(result.shots),
            "status": result.status,
        },
    )
    return doc


@router.get("/productions", summary="列出当前租户成片产物")
async def list_productions(
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    items = [p for p in _productions.values() if p.get("tenant_id") == principal.tenant_id]
    return {"productions": items}


@router.get("/productions/{storyboard_id}", summary="查看成片产物详情")
async def get_production(
    storyboard_id: str,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    doc = _productions.get(storyboard_id)
    if doc is None or doc.get("tenant_id") != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "产物不存在或无权访问")
    return doc
