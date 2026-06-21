"""画布路由：无限节点画布 CRUD + 智能体生成全节点链 + 每节点审核编辑。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from xagent.domains.creative_studio.canvas import (
    NodeStatus,
    NodeType,
    ProductionCanvas,
    ProductionNode,
)
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/canvas", tags=["canvas"])

_canvases: dict[str, ProductionCanvas] = {}
_canvas_tenants: dict[str, str] = {}


class CanvasCreateIn(BaseModel):
    title: str = "未命名"
    brief: str = Field(default="", description="一句话需求，智能体据此生成全节点链")


class NodeUpdateIn(BaseModel):
    title: str | None = None
    content: Any = None
    status: str | None = None
    human_note: str = ""


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
    return canvas.to_dict()


def _get(canvas_id: str, principal: Principal) -> ProductionCanvas:
    c = _canvases.get(canvas_id)
    if c is None or _canvas_tenants.get(canvas_id) != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画布不存在或无权访问")
    return c


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
    return canvas.to_dict()


class NodeReviewIn(BaseModel):
    status: str = "approved"
    human_note: str = ""
    content: Any = None
    title: str | None = None


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
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="canvas.review",
        resource="canvas",
        detail={"canvas_id": canvas_id, "node_id": node_id, "status": body.status},
    )
    return canvas.to_dict()