"""视频剪辑路由：时间线 CRUD + 渲染 + 草稿导出 + 智能体自主剪辑。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from xagent.domains.creative_studio.editor.models import (
    Clip,
    Timeline,
    TrackType,
    Transition,
    TransitionType,
)
from xagent.domains.creative_studio.editor.tools import _timelines
from xagent.domains.creative_studio.editor.video_editor import get_video_editor
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/creative-studio/editor", tags=["editor"])

# 按租户隔离的时间线归属
_timeline_tenants: dict[str, str] = {}


class TimelineIn(BaseModel):
    name: str = "未命名"
    width: int = 1080
    height: int = 1920
    fps: int = 30


class ClipIn(BaseModel):
    track_type: str = "video"
    source_url: str = ""
    timeline_start: float = 0
    timeline_end: float = 4
    source_start: float | None = None
    source_end: float | None = None
    text: str = ""
    font_size: int = 48
    color: str = "#ffffff"
    position: str = "center"
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0


class TransitionIn(BaseModel):
    clip_id: str
    type: str = "dissolve"
    duration: float = 0.5


class RenderIn(BaseModel):
    output_name: str | None = None


def _check_tenant(timeline_id: str, principal: Principal) -> Timeline:
    tl = _timelines.get(timeline_id)
    if tl is None or _timeline_tenants.get(timeline_id) != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "时间线不存在或无权访问")
    return tl


@router.post("/timelines", summary="创建剪辑时间线")
async def create_timeline(
    body: TimelineIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    tl = Timeline(name=body.name, width=body.width, height=body.height, fps=body.fps)
    _timelines[tl.id] = tl
    _timeline_tenants[tl.id] = principal.tenant_id
    return tl.to_dict()


@router.get("/timelines", summary="列出时间线")
async def list_timelines(
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    items = [
        tl.to_dict()
        for tid, tl in _timelines.items()
        if _timeline_tenants.get(tid) == principal.tenant_id
    ]
    return {"timelines": items}


@router.get("/timelines/{timeline_id}", summary="查看时间线")
async def get_timeline_api(
    timeline_id: str,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    return _check_tenant(timeline_id, principal).to_dict()


@router.post("/timelines/{timeline_id}/clips", summary="添加片段")
async def add_clip(
    timeline_id: str,
    body: ClipIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    tl = _check_tenant(timeline_id, principal)
    clip = Clip(
        track_type=TrackType(body.track_type),
        source_url=body.source_url,
        timeline_start=body.timeline_start,
        timeline_end=body.timeline_end,
        source_start=body.source_start,
        source_end=body.source_end,
        text=body.text,
        font_size=body.font_size,
        color=body.color,
        position=body.position,
        volume=body.volume,
        fade_in=body.fade_in,
        fade_out=body.fade_out,
    )
    tl.add_clip(clip)
    return tl.to_dict()


@router.post("/timelines/{timeline_id}/transitions", summary="添加转场")
async def add_transition(
    timeline_id: str,
    body: TransitionIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    tl = _check_tenant(timeline_id, principal)
    tl.add_transition(Transition(
        clip_id=body.clip_id,
        type=TransitionType(body.type),
        duration=body.duration,
    ))
    return tl.to_dict()


@router.delete("/timelines/{timeline_id}/clips/{clip_id}", summary="删除片段")
async def remove_clip(
    timeline_id: str,
    clip_id: str,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    tl = _check_tenant(timeline_id, principal)
    tl.remove_clip(clip_id)
    return tl.to_dict()


@router.post("/timelines/{timeline_id}/render", summary="渲染导出视频(MoviePy)")
async def render_timeline(
    timeline_id: str,
    body: RenderIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    tl = _check_tenant(timeline_id, principal)
    result = await get_video_editor().render(tl, body.output_name)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.render",
        resource="creative",
        detail={"timeline_id": timeline_id, "ok": result["ok"]},
    )
    return result


@router.post("/timelines/{timeline_id}/export-draft", summary="导出剪映草稿")
async def export_draft(
    timeline_id: str,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    tl = _check_tenant(timeline_id, principal)
    result = get_video_editor().export_jianying_draft(tl)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.export_draft",
        resource="creative",
        detail={"timeline_id": timeline_id},
    )
    return result
