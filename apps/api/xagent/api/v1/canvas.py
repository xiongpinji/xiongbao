"""画布路由：无限节点画布 CRUD + 智能体生成全节点链 + 每节点审核编辑。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from xagent.core.workflow import (
    ApprovalGate,
    WorkflowSpec,
    WorkflowStep,
    get_engine,
)
from xagent.domains.creative_studio.canvas import (
    NodeStatus,
    NodeType,
    ProductionCanvas,
    ProductionNode,
)
from xagent.domains.creative_studio.canvas.quality import (
    auto_fix as canvas_auto_fix,
)
from xagent.domains.creative_studio.canvas.quality import (
    estimate_canvas,
    score_canvas,
    score_node,
)
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/canvas", tags=["canvas"])

_canvases: dict[str, ProductionCanvas] = {}
_canvas_tenants: dict[str, str] = {}

_CANVAS_SNAPSHOT_PATH = Path(os.environ.get("XAGENT_CANVAS_SNAPSHOT", "data/canvas_snapshot.json"))


def _persist_snapshot() -> None:
    """把画布数据写到本地快照文件（lite 模式简易持久化，不打开 stdout）。"""
    try:
        _CANVAS_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "canvases": {cid: c.to_dict() for cid, c in _canvases.items()},
            "tenants": _canvas_tenants,
        }
        _CANVAS_SNAPSHOT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        # 持久化是 best-effort，失败不影响主流程
        pass


def _load_snapshot_once() -> None:
    if _canvases or _canvas_tenants:
        return
    if not _CANVAS_SNAPSHOT_PATH.exists():
        return
    try:
        data = json.loads(_CANVAS_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for cid, raw in (data.get("canvases") or {}).items():
        canvas = ProductionCanvas(
            canvas_id=raw.get("canvas_id", cid),
            title=raw.get("title", ""),
            brief=raw.get("brief", ""),
            workflow_run_id=raw.get("workflow_run_id"),
        )
        for node_raw in raw.get("nodes", []):
            try:
                node = ProductionNode(
                    node_id=node_raw.get("node_id") or uuid4().hex,
                    node_type=NodeType(node_raw.get("node_type", NodeType.brief_analysis.value)),
                    title=node_raw.get("title", ""),
                    content=node_raw.get("content"),
                    status=NodeStatus(node_raw.get("status", NodeStatus.pending.value)),
                    agent_note=node_raw.get("agent_note", ""),
                    human_note=node_raw.get("human_note", ""),
                    position=node_raw.get("position") or {"x": 0, "y": 0},
                    dependencies=node_raw.get("dependencies") or [],
                    settings=node_raw.get("settings") or {},
                    locked=bool(node_raw.get("locked", False)),
                )
            except ValueError:
                continue
            canvas.nodes.append(node)
        _canvases[cid] = canvas
    for cid, tenant in (data.get("tenants") or {}).items():
        _canvas_tenants[cid] = tenant


_load_snapshot_once()

# 需要人工审核门的节点类型（对齐工作流 ApprovalGate）
_REVIEW_GATE_TYPES = {
    NodeType.brief_analysis,
    NodeType.plot_outline,
    NodeType.storyboard,
    NodeType.export,
}

# 节点类型到 agent 角色的映射
_NODE_ROLES: dict[NodeType, str] = {
    NodeType.brief_analysis: "planner",
    NodeType.plot_outline: "screenwriter",
    NodeType.character_setting: "screenwriter",
    NodeType.storyboard: "director",
    NodeType.keyframe: "general",
    NodeType.video: "general",
    NodeType.voiceover: "general",
    NodeType.subtitle: "general",
    NodeType.soundtrack: "general",
    NodeType.export: "editor_agent",
}


class CanvasCreateIn(BaseModel):
    title: str = "未命名"
    brief: str = Field(default="", description="一句话需求，智能体据此生成全节点链")


class NodeUpdateIn(BaseModel):
    title: str | None = None
    content: Any = None
    status: str | None = None
    human_note: str = ""
    settings: dict[str, Any] | None = None
    locked: bool | None = None


class LayoutIn(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, str]] = Field(default_factory=list)


class QualityIn(BaseModel):
    node_ids: list[str] | None = None


class ScriptParseIn(BaseModel):
    script: str | None = None
    auto_link: bool = True
    keep_existing: bool = True


class BatchGenerateIn(BaseModel):
    node_types: list[str] = Field(default_factory=list)


class CanvasImportIn(BaseModel):
    title: str = "未命名"
    brief: str = ""
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, str]] = Field(default_factory=list)


@router.get("/templates/list", summary="列出短剧模板")
async def list_templates(
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    from xagent.domains.creative_studio.templates import list_templates as _list

    return {"templates": _list()}


class TemplateCreateIn(BaseModel):
    template_id: str


@router.post("/from-template", summary="从模板创建画布")
async def create_from_template(
    body: TemplateCreateIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    from xagent.domains.creative_studio.templates import get_template

    tpl = get_template(body.template_id)
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "模板不存在")
    # 用模板 brief 创建画布
    canvas = ProductionCanvas(title=tpl.name, brief=tpl.brief)
    canvas.add_node(ProductionNode(
        node_type=NodeType.brief_analysis, title="需求分析",
        content=tpl.brief, agent_note=f"模板: {tpl.name} ({tpl.genre})",
        position={"x": 50, "y": 200},
    ))
    _canvases[canvas.canvas_id] = canvas
    _canvas_tenants[canvas.canvas_id] = principal.tenant_id
    _persist_snapshot()
    return canvas.to_dict()


def _get(canvas_id: str, principal: Principal) -> ProductionCanvas:
    c = _canvases.get(canvas_id)
    if c is None or _canvas_tenants.get(canvas_id) != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画布不存在或无权访问")
    return c


def _workflow_step_from_node(
    node: ProductionNode,
    depends_on: list[str],
    *,
    with_approval: bool = True,
) -> WorkflowStep:
    goal = (
        f"执行短剧生产节点：{node.node_type.value}。标题：{node.title}。"
        f"内容：{node.content or ''}。参数：{node.settings or {}}"
    )
    approval = None
    if with_approval and node.node_type in _REVIEW_GATE_TYPES:
        approval = ApprovalGate(message=f"请审核节点：{node.title or node.node_type.value}")
    return WorkflowStep(
        id=node.node_id,
        name=node.title or node.node_type.value,
        role=_NODE_ROLES.get(node.node_type, "general"),
        goal=goal,
        depends_on=depends_on,
        approval=approval,
    )


def _workflow_spec_from_canvas(canvas: ProductionCanvas) -> WorkflowSpec:
    valid_ids = {node.node_id for node in canvas.nodes}
    steps = [
        _workflow_step_from_node(node, [dep for dep in node.dependencies if dep in valid_ids])
        for node in canvas.nodes
        if not node.locked
    ]
    if not steps:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "画布没有可运行节点")
    return WorkflowSpec(name=f"canvas:{canvas.canvas_id}", steps=steps)


@router.post("", summary="创建画布")
async def create_canvas(
    body: CanvasCreateIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = ProductionCanvas(title=body.title, brief=body.brief)
    if body.brief:
        from xagent.adapters.llm import Message, get_llm_client

        llm = get_llm_client()
        prompt = (
            "根据以下短剧需求，生成完整制作节点链。"
            + "需求：" + body.brief + "\n"
            + "返回JSON数组，每个元素包含: node_type, title, content, agent_note"
        )
        resp = await llm.complete([Message(role="user", content=prompt)])
        import json

        try:
            text = resp.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            nodes_data = json.loads(text)
            for nd in nodes_data:
                canvas.add_node(ProductionNode(
                    node_type=NodeType(nd.get("node_type", "需求分析")),
                    title=nd.get("title", ""),
                    content=nd.get("content", ""),
                    agent_note=nd.get("agent_note", ""),
                ))
        except Exception:  # noqa: S110  LLM 生成失败不影响
            pass
    if not canvas.nodes:
        canvas.add_node(ProductionNode(
            node_type=NodeType.brief_analysis,
            title="需求分析",
            content=body.brief,
            position={"x": 50, "y": 200},
        ))
    _canvases[canvas.canvas_id] = canvas
    _canvas_tenants[canvas.canvas_id] = principal.tenant_id
    _persist_snapshot()
    return canvas.to_dict()


@router.post("/import", summary="导入画布")
async def import_canvas(
    body: CanvasImportIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = ProductionCanvas(title=body.title, brief=body.brief)
    for raw in body.nodes:
        try:
            node = ProductionNode(
                node_id=str(raw.get("node_id") or uuid4().hex[:8]),
                node_type=NodeType(raw.get("node_type", NodeType.brief_analysis.value)),
                title=str(raw.get("title") or ""),
                content=raw.get("content"),
                status=NodeStatus(raw.get("status", NodeStatus.pending.value)),
                agent_note=str(raw.get("agent_note") or ""),
                human_note=str(raw.get("human_note") or ""),
                position=raw.get("position") or {"x": 0, "y": 0},
                dependencies=list(raw.get("dependencies") or []),
                settings=dict(raw.get("settings") or {}),
                locked=bool(raw.get("locked", False)),
            )
        except ValueError:
            continue
        canvas.add_node(node)
    canvas.apply_layout([], body.edges)
    _canvases[canvas.canvas_id] = canvas
    _canvas_tenants[canvas.canvas_id] = principal.tenant_id
    _persist_snapshot()
    return canvas.to_dict()


@router.get("/{canvas_id}", summary="获取画布")
async def get_canvas(
    canvas_id: str,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    return _get(canvas_id, principal).to_dict()


@router.get("", summary="列出画布")
async def list_canvases(
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    return {
        "canvases": [
            c.to_dict()
            for cid, c in _canvases.items()
            if _canvas_tenants.get(cid) == principal.tenant_id
        ]
    }


class NodeCreateIn(BaseModel):
    node_type: str
    title: str = ""
    content: Any = None
    position: dict = Field(default_factory=lambda: {"x": 0, "y": 0})


@router.post("/{canvas_id}/nodes", summary="添加节点")
async def add_node(
    canvas_id: str,
    body: NodeCreateIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = _get(canvas_id, principal)
    node = ProductionNode(
        node_type=NodeType(body.node_type),
        title=body.title,
        content=body.content,
        position=body.position,
    )
    canvas.add_node(node)
    _persist_snapshot()
    return canvas.to_dict()


@router.delete("/{canvas_id}/nodes/{node_id}", summary="删除节点")
async def delete_node(
    canvas_id: str,
    node_id: str,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = _get(canvas_id, principal)
    original_len = len(canvas.nodes)
    canvas.nodes = [node for node in canvas.nodes if node.node_id != node_id]
    if len(canvas.nodes) == original_len:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "节点不存在")
    for node in canvas.nodes:
        node.dependencies = [dep for dep in node.dependencies if dep != node_id]
    _persist_snapshot()
    return canvas.to_dict()


class NodeReviewIn(BaseModel):
    status: str = "approved"
    human_note: str = ""
    content: Any = None
    title: str | None = None


@router.patch("/{canvas_id}/nodes/{node_id}", summary="更新节点")
async def patch_node(
    canvas_id: str,
    node_id: str,
    body: NodeUpdateIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = _get(canvas_id, principal)
    node = canvas.get_node(node_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "节点不存在")
    if node.locked and body.settings:
        raise HTTPException(status.HTTP_409_CONFLICT, "节点已锁定")
    if body.title is not None:
        node.title = body.title
    if body.content is not None:
        node.content = body.content
    if body.status is not None:
        node.status = NodeStatus(body.status)
    if body.human_note:
        node.human_note = body.human_note
    if body.settings is not None:
        node.merge_settings(body.settings)
    if body.locked is not None:
        node.locked = body.locked
    _persist_snapshot()
    return {"node": node.to_dict(), "canvas": canvas.to_dict()}


@router.put("/{canvas_id}/layout", summary="保存画布布局")
async def save_layout(
    canvas_id: str,
    body: LayoutIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = _get(canvas_id, principal)
    canvas.apply_layout(body.nodes, body.edges)
    _persist_snapshot()
    return canvas.to_dict()


@router.post("/{canvas_id}/run", summary="运行画布工作流")
async def run_canvas(
    canvas_id: str,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = _get(canvas_id, principal)
    if not canvas.nodes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "画布没有可运行节点")
    spec = _workflow_spec_from_canvas(canvas)
    engine = get_engine()
    run = engine.create_run(spec, principal)
    canvas.workflow_run_id = run.run_id
    run = await engine.execute(run.run_id, principal)
    _persist_snapshot()
    workflow = run.to_view()
    return {
        "canvas_id": canvas.canvas_id,
        "workflow_run_id": run.run_id,
        "workflow": workflow,
        "node_step_map": {step["id"]: step["id"] for step in workflow["steps"]},
        "canvas": canvas.to_dict(),
    }


@router.post("/{canvas_id}/run/{node_id}", summary="运行单个节点")
async def run_canvas_node(
    canvas_id: str,
    node_id: str,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = _get(canvas_id, principal)
    node = canvas.get_node(node_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "节点不存在")
    spec = WorkflowSpec(
        name=f"canvas:{canvas.canvas_id}:{node.node_id}",
        steps=[_workflow_step_from_node(node, [], with_approval=False)],
    )
    engine = get_engine()
    run = engine.create_run(spec, principal)
    run = await engine.execute(run.run_id, principal)
    step = run.steps[0]
    if step.result:
        node.agent_note = str(step.result.get("final_answer") or step.result)[:500]
    elif step.error:
        node.agent_note = f"执行失败：{step.error}"
    else:
        node.agent_note = "节点执行已提交"
    _persist_snapshot()
    return {
        "canvas_id": canvas.canvas_id,
        "node_id": node.node_id,
        "workflow_run_id": run.run_id,
        "canvas": canvas.to_dict(),
        "workflow": run.to_view(),
    }


@router.post("/{canvas_id}/estimate", summary="估算画布资源")
async def estimate_canvas_endpoint(
    canvas_id: str,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    return estimate_canvas(_get(canvas_id, principal))


@router.post("/{canvas_id}/quality", summary="评估画布质量")
async def quality_canvas_endpoint(
    canvas_id: str,
    body: QualityIn,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    canvas = _get(canvas_id, principal)
    if not body.node_ids:
        return score_canvas(canvas)
    nodes = []
    for node_id in body.node_ids:
        node = canvas.get_node(node_id)
        if node is not None:
            nodes.append(
                {"node_id": node.node_id, "node_type": node.node_type.value, **score_node(node)}
            )
    return {"nodes": nodes}


@router.post("/{canvas_id}/nodes/{node_id}/auto-fix", summary="自动修复节点参数")
async def auto_fix_node(
    canvas_id: str,
    node_id: str,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = _get(canvas_id, principal)
    node = canvas.get_node(node_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "节点不存在")
    if node.locked:
        raise HTTPException(status.HTTP_409_CONFLICT, "节点已锁定")
    patch = canvas_auto_fix(node)
    node.merge_settings(patch)
    _persist_snapshot()
    return {"patch": patch, "node": node.to_dict(), "canvas": canvas.to_dict()}


@router.post("/{canvas_id}/script/parse", summary="解析剧本为分镜节点")
async def parse_script(
    canvas_id: str,
    body: ScriptParseIn | None = None,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = _get(canvas_id, principal)
    source = str(body.script if body and body.script is not None else canvas.brief or "")
    if body is None or body.keep_existing:
        for node in canvas.nodes:
            if node.content:
                source = f"{source}。{node.content}"
    parts = [p.strip() for p in source.replace("\n", "。 ").split("。") if p.strip()]
    created = []
    for index, part in enumerate(parts[:12], start=1):
        node = ProductionNode(
            node_type=NodeType.storyboard,
            title=f"分镜 {index}",
            content=part,
            position={"x": 260 + index * 120, "y": 240},
        )
        canvas.add_node(node)
        created.append(node.to_dict())
    _persist_snapshot()
    return {"created": created, "canvas": canvas.to_dict()}


@router.get("/{canvas_id}/export", summary="导出画布")
async def export_canvas(
    canvas_id: str,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    canvas = _get(canvas_id, principal)
    edges = [
        {"source": dep, "target": node.node_id}
        for node in canvas.nodes
        for dep in node.dependencies
    ]
    return {"version": 1, "edges": edges, **canvas.to_dict()}


@router.post("/{canvas_id}/nodes/{node_id}/request-review", summary="请求节点审核")
async def request_node_review(
    canvas_id: str,
    node_id: str,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = _get(canvas_id, principal)
    node = canvas.get_node(node_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "节点不存在")
    node.status = NodeStatus.review_required
    _persist_snapshot()
    return canvas.to_dict()


@router.post("/{canvas_id}/batch-generate", summary="批量生成媒体节点")
async def batch_generate(
    canvas_id: str,
    body: BatchGenerateIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    from xagent.api.v1.creative_studio import _media_task_tenants
    from xagent.domains.creative_studio.media.base import (
        GenerationMode,
        GenerationRequest,
        MediaKind,
    )
    from xagent.domains.creative_studio.media.registry import get_media_registry

    canvas = _get(canvas_id, principal)
    wanted = set(body.node_types)
    registry = get_media_registry()
    results = []
    for node in canvas.nodes:
        if wanted and node.node_type.value not in wanted:
            continue
        if node.node_type is NodeType.keyframe:
            kind = MediaKind.image
            mode = GenerationMode.text_to_image
        elif node.node_type is NodeType.video:
            kind = MediaKind.video
            mode = GenerationMode.text_to_video
        else:
            continue
        settings = dict(node.settings or {})
        task = await registry.generate(
            GenerationRequest(
                kind=kind,
                mode=mode,
                prompt=str(settings.get("prompt") or node.content or node.title),
                model_id=settings.get("model"),
                resolution=settings.get("resolution"),
                duration_seconds=settings.get("duration"),
                seed=settings.get("seed"),
                params=settings,
            )
        )
        if task.task_id:
            _media_task_tenants[task.task_id] = principal.tenant_id
        results.append({"node_id": node.node_id, **task.__dict__})
    return {"results": results, "canvas": canvas.to_dict()}


@router.post("/{canvas_id}/nodes/{node_id}/review", summary="审核/修改节点")
async def review_node(
    canvas_id: str,
    node_id: str,
    body: NodeReviewIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    canvas = _get(canvas_id, principal)
    node = canvas.get_node(node_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "节点不存在")
    node.status = NodeStatus(body.status)
    if body.human_note:
        node.human_note = body.human_note
    if body.content is not None:
        node.content = body.content
    if body.title is not None:
        node.title = body.title
    _persist_snapshot()
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="canvas.review",
        resource="canvas",
        detail={"canvas_id": canvas.canvas_id, "node_id": node_id, "status": body.status},
    )
    return canvas.to_dict()
