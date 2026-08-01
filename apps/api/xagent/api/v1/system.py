"""系统能力概览路由：让前端设置页能读取当前可用的工具、MCP、命令等只读信息，以及 LLM 模型配置。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from xagent.adapters.mcp import get_mcp_manager
from xagent.adapters.tools import get_tool_registry
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.settings import get_settings

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/capabilities", summary="工作台只读能力概览")
async def capabilities(
    principal: Principal = Depends(require_permission("audit", "read")),
) -> dict:
    tools = get_tool_registry()
    mcp = get_mcp_manager()

    tool_items = []
    for name in tools.names():
        tool = tools.get(name)
        tool_items.append({
            "name": name,
            "description": getattr(tool, "description", ""),
            "kind": getattr(tool, "kind", "function"),
        })

    mcp_servers = [
        {
            "name": srv.name,
            "kind": srv.transport,
            "endpoint": srv.url or srv.command,
            "enabled": srv.enabled,
        }
        for srv in mcp.servers.values()
    ]

    return {
        "tenant": principal.tenant_id,
        "tools": tool_items,
        "mcp_servers": mcp_servers,
        "commands": [
            {"name": "/new", "description": "新建任务"},
            {"name": "/search", "description": "搜索工作区"},
            {"name": "/run-canvas", "description": "执行当前短剧画布"},
            {"name": "/export", "description": "导出当前剪辑节点产物"},
        ],
        "code_preview": {
            "default_theme": "neutral-dark",
            "tab_size": 2,
            "diff_mode": "side-by-side",
        },
        "onboarding": [
            "在工作区新建任务或打开项目",
            "在短剧工厂自由画布右键添加流程节点",
            "运行画布触发真实 WorkflowEngine",
            "在剪辑节点 / 导出节点完成短剧产出",
        ],
    }


# ---- LLM 模型配置 ----


class LLMConfigOut(BaseModel):
    """LLM 配置输出（脱敏）。"""
    default_model: str
    fallback_models: list[str]
    proxy_url: str
    has_proxy_api_key: bool
    ollama_base_url: str
    ollama_model: str
    request_timeout_seconds: int
    has_openai_key: bool
    has_anthropic_key: bool
    has_deepseek_key: bool


class LLMConfigIn(BaseModel):
    """LLM 配置输入（部分更新）。"""
    default_model: str | None = None
    fallback_models: list[str] | None = None
    proxy_url: str | None = None
    proxy_api_key: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    request_timeout_seconds: int | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    deepseek_api_key: str | None = None


@router.get("/llm-config", summary="读取当前 LLM 模型配置（脱敏）")
async def get_llm_config(
    principal: Principal = Depends(require_permission("system", "read")),
) -> dict:
    cfg = get_settings().llm
    return LLMConfigOut(
        default_model=cfg.default_model,
        fallback_models=cfg.fallback_models,
        proxy_url=cfg.proxy_url,
        has_proxy_api_key=bool(cfg.proxy_api_key),
        ollama_base_url=cfg.ollama_base_url,
        ollama_model=cfg.ollama_model,
        request_timeout_seconds=cfg.request_timeout_seconds,
        has_openai_key=bool(cfg.openai_api_key),
        has_anthropic_key=bool(cfg.anthropic_api_key),
        has_deepseek_key=bool(cfg.deepseek_api_key),
    ).model_dump()


@router.put("/llm-config", summary="更新 LLM 模型配置（运行时生效）")
async def update_llm_config(
    body: LLMConfigIn,
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    cfg = get_settings().llm
    if body.default_model is not None:
        cfg.default_model = body.default_model
    if body.fallback_models is not None:
        cfg.fallback_models = body.fallback_models
    if body.proxy_url is not None:
        cfg.proxy_url = body.proxy_url
    if body.proxy_api_key is not None:
        cfg.proxy_api_key = body.proxy_api_key
    if body.ollama_base_url is not None:
        cfg.ollama_base_url = body.ollama_base_url
    if body.ollama_model is not None:
        cfg.ollama_model = body.ollama_model
    if body.request_timeout_seconds is not None:
        cfg.request_timeout_seconds = body.request_timeout_seconds
    if body.openai_api_key is not None:
        cfg.openai_api_key = body.openai_api_key
    if body.anthropic_api_key is not None:
        cfg.anthropic_api_key = body.anthropic_api_key
    if body.deepseek_api_key is not None:
        cfg.deepseek_api_key = body.deepseek_api_key

    # 重置 LLM 客户端缓存，使新配置生效
    from xagent.adapters.llm.factory import reset_llm_client
    reset_llm_client()

    return {
        "status": "ok",
        "default_model": cfg.default_model,
        "fallback_models": cfg.fallback_models,
        "proxy_url": cfg.proxy_url,
        "ollama_base_url": cfg.ollama_base_url,
        "ollama_model": cfg.ollama_model,
        "request_timeout_seconds": cfg.request_timeout_seconds,
    }


# ─── Webhook 管理 ───


class WebhookCreateIn(BaseModel):
    url: str = Field(..., min_length=1)
    events: list[str] = Field(default_factory=lambda: ["*"])
    secret: str = ""


@router.get("/webhooks", summary="列出 Webhook")
async def list_webhooks(
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    from xagent.core.webhooks import get_webhook_manager
    mgr = get_webhook_manager()
    hooks = [h.to_dict() for h in mgr.list(principal.tenant_id)]
    return {"webhooks": hooks, "count": len(hooks)}


@router.post("/webhooks", summary="注册 Webhook")
async def create_webhook(
    body: WebhookCreateIn,
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    from xagent.core.webhooks import get_webhook_manager
    mgr = get_webhook_manager()
    hook = mgr.register(
        tenant_id=principal.tenant_id,
        url=body.url,
        events=body.events,
        secret=body.secret,
    )
    return {"webhook": hook.to_dict()}


@router.delete("/webhooks/{webhook_id}", summary="删除 Webhook")
async def delete_webhook(
    webhook_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    from xagent.core.webhooks import get_webhook_manager
    mgr = get_webhook_manager()
    if not mgr.delete(webhook_id, principal.tenant_id):
        raise HTTPException(404, "Webhook 不存在")
    return {"deleted": webhook_id}
