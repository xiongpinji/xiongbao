"""系统能力概览路由：让前端设置页能读取当前可用的工具、MCP、命令等只读信息，以及 LLM 模型配置。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from xagent.adapters.mcp import get_mcp_manager
from xagent.adapters.tools import get_tool_registry
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.logging import get_logger
from xagent.infra.paths import data_path
from xagent.infra.secrets import is_secret_ref, resolve_secret
from xagent.infra.secure_json import write_private_json
from xagent.infra.settings import RunMode, get_settings

router = APIRouter(prefix="/system", tags=["system"])
logger = get_logger("xagent.api.system")


class ClientErrorIn(BaseModel):
    """前端 ErrorBoundary 上报的客户端异常。"""

    message: str = Field(default="", max_length=2000)
    stack: str = Field(default="", max_length=2000)
    componentStack: str = Field(default="", max_length=2000)
    url: str = Field(default="", max_length=500)
    timestamp: int = 0


@router.post("/client-errors", summary="前端异常上报（免鉴权，供 ErrorBoundary 使用）")
async def report_client_error(body: ClientErrorIn) -> dict:
    # 免鉴权：前端崩溃时可能无法携带有效 token，上报不能被 401 阻断
    logger.warning(
        "client_error_reported",
        message=body.message[:500],
        url=body.url,
        component_stack=body.componentStack[:300],
    )
    return {"received": True}


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

# 运行时 LLM 配置覆盖持久化文件（非密字段和 secretRef 才会写入）。
# 明文密钥仅在当前进程生效，响应会明确标注 session_only。
_LLM_OVERRIDES_PATH = data_path("llm_config_overrides.json")
# 允许通过 API 覆盖的 LLM 字段白名单
_LLM_OVERRIDABLE_FIELDS = (
    "default_model",
    "fallback_models",
    "proxy_url",
    "proxy_api_key",
    "ollama_base_url",
    "ollama_model",
    "request_timeout_seconds",
    "openai_api_key",
    "anthropic_api_key",
    "deepseek_api_key",
)
_LLM_SENSITIVE_FIELDS = frozenset({
    "proxy_api_key",
    "openai_api_key",
    "anthropic_api_key",
    "deepseek_api_key",
})


def _load_llm_overrides(*, mode: RunMode | None = None) -> dict:
    current_mode = mode or get_settings().mode
    if not _LLM_OVERRIDES_PATH.is_file():
        return {}
    try:
        import json

        data = json.loads(_LLM_OVERRIDES_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("LLM override root must be an object")
    except Exception as exc:  # noqa: BLE001
        if current_mode != RunMode.lite:
            raise RuntimeError("LLM override file is invalid") from exc
        logger.warning("llm_overrides_load_failed", error_type=type(exc).__name__)
        return {}

    overrides = {k: v for k, v in data.items() if k in _LLM_OVERRIDABLE_FIELDS}
    plaintext_fields = sorted(
        key
        for key, value in overrides.items()
        if key in _LLM_SENSITIVE_FIELDS and not is_secret_ref(value)
    )
    if plaintext_fields:
        fields = ", ".join(plaintext_fields)
        if current_mode != RunMode.lite:
            raise RuntimeError(f"plaintext LLM overrides are forbidden: {fields}")
        logger.warning("llm_plaintext_overrides_ignored", fields=plaintext_fields)
        for key in plaintext_fields:
            overrides.pop(key)
    return overrides


def _apply_llm_overrides() -> dict:
    """把持久化的覆盖值应用到当前 settings（幂等），返回应用的覆盖。"""
    settings = get_settings()
    overrides = _load_llm_overrides(mode=settings.mode)
    if overrides:
        cfg = settings.llm
        for key, value in overrides.items():
            if key in _LLM_SENSITIVE_FIELDS:
                value = resolve_secret(
                    value,
                    field=f"llm.{key}",
                    lite=settings.mode == RunMode.lite,
                )
            setattr(cfg, key, value)
    return overrides


def _save_llm_overrides(overrides: dict) -> None:
    write_private_json(_LLM_OVERRIDES_PATH, overrides)


# 模块导入时（即 app 创建时）恢复上次持久化的覆盖，保证重启后配置仍生效
_apply_llm_overrides()


class LLMModelOption(BaseModel):
    """可选模型及其可用性（供前端动态渲染选择器）。"""
    id: str
    label: str
    available: bool
    current: bool = False
    reason: str = ""


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
    # 配置来源可见性：磁盘覆盖生效时 env/.env 的同名配置不生效（P1 修复）
    override_active: bool = False
    override_fields: list[str] = []
    models: list[LLMModelOption] = []


# 模型目录：与前端历史预设保持一致，可用性由后端按 key/代理/本地运行时判定
_LLM_MODEL_CATALOG: tuple[tuple[str, str, str], ...] = (
    ("deepseek-v4-flash", "DeepSeek V4 Flash", "deepseek"),
    ("deepseek-chat", "DeepSeek Chat", "deepseek"),
    ("deepseek-reasoner", "DeepSeek Reasoner", "deepseek"),
    ("gpt-4o-mini", "GPT-4o Mini", "openai"),
    ("gpt-4o", "GPT-4o", "openai"),
    ("claude-sonnet-4-20250514", "Claude Sonnet 4", "anthropic"),
    ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku", "anthropic"),
)

_PROVIDER_REASON = {
    "deepseek": "缺 DeepSeek key 且未配置代理",
    "openai": "缺 OpenAI key 且未配置代理",
    "anthropic": "缺 Anthropic key 且未配置代理",
    "ollama": "未配置本地 Ollama 地址",
}


def _model_provider(model: str) -> str:
    if model.startswith(("ollama/", "ollama_chat/")):
        return "ollama"
    if model.startswith("deepseek"):
        return "deepseek"
    if model.startswith(("claude", "anthropic/")):
        return "anthropic"
    return "openai"


def _build_model_options(cfg) -> list[LLMModelOption]:
    def provider_ready(provider: str) -> bool:
        if cfg.proxy_url:  # 代理模式下由 proxy 侧路由，全部视为可用
            return True
        if provider == "deepseek":
            return bool(cfg.deepseek_api_key)
        if provider == "openai":
            return bool(cfg.openai_api_key)
        if provider == "anthropic":
            return bool(cfg.anthropic_api_key)
        return bool(cfg.ollama_base_url)

    seen: set[str] = set()
    options: list[LLMModelOption] = []
    current = cfg.default_model
    if current:
        provider = _model_provider(current)
        ready = provider_ready(provider)
        options.append(LLMModelOption(
            id=current, label=current, available=ready, current=True,
            reason="" if ready else _PROVIDER_REASON[provider],
        ))
        seen.add(current)
    for mid, label, provider in _LLM_MODEL_CATALOG:
        if mid in seen:
            continue
        ready = provider_ready(provider)
        options.append(LLMModelOption(
            id=mid, label=label, available=ready,
            reason="" if ready else _PROVIDER_REASON[provider],
        ))
    return options


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
    # 先应用持久化覆盖（幂等），保证重启后 / 多实例下读到的是生效值
    overrides = _apply_llm_overrides()
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
        override_active=bool(overrides),
        override_fields=sorted(overrides),
        models=_build_model_options(cfg),
    ).model_dump()


@router.put("/llm-config", summary="更新 LLM 模型配置（运行时生效）")
async def update_llm_config(
    body: LLMConfigIn,
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    settings = get_settings()
    cfg = settings.llm
    submitted = dict(body.model_dump(exclude_none=True))
    runtime_fields = dict(submitted)
    for key, value in runtime_fields.items():
        if key in _LLM_SENSITIVE_FIELDS and is_secret_ref(value):
            runtime_fields[key] = resolve_secret(
                value,
                field=f"llm.{key}",
                lite=settings.mode == RunMode.lite,
            )

    # 先把非模型字段应用到临时视图，再校验目标模型可用性（无 key 拦截）
    prospective = cfg.model_copy(update=runtime_fields)
    if body.default_model is not None:
        provider = _model_provider(body.default_model)
        ready = (
            bool(prospective.proxy_url)
            or (provider == "deepseek" and bool(prospective.deepseek_api_key))
            or (provider == "openai" and bool(prospective.openai_api_key))
            or (provider == "anthropic" and bool(prospective.anthropic_api_key))
            or (provider == "ollama" and bool(prospective.ollama_base_url))
        )
        if not ready:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=422,
                detail=(
                    f"模型 {body.default_model} 不可用：{_PROVIDER_REASON[provider]}。"
                    "请先配置对应 key 或代理，避免运行时出现『连接已中断』类失败。"
                ),
            )
    for key, value in runtime_fields.items():
        setattr(cfg, key, value)

    session_only_fields = sorted(
        key
        for key, value in submitted.items()
        if key in _LLM_SENSITIVE_FIELDS and not is_secret_ref(value)
    )
    reference_fields = sorted(
        key
        for key, value in submitted.items()
        if key in _LLM_SENSITIVE_FIELDS and is_secret_ref(value)
    )
    persistable_changes = {
        key: value
        for key, value in submitted.items()
        if key not in _LLM_SENSITIVE_FIELDS or is_secret_ref(value)
    }

    # 持久化覆盖到磁盘（与已有覆盖合并），重启后仍生效
    overrides = _load_llm_overrides(mode=settings.mode)
    for key in session_only_fields:
        overrides.pop(key, None)
    overrides.update(persistable_changes)
    try:
        _save_llm_overrides(overrides)
        persisted = True
    except Exception as exc:  # noqa: BLE001
        logger.error("llm_overrides_save_failed", error=str(exc))
        persisted = False

    # 重置 LLM 客户端缓存，使新配置生效
    from xagent.adapters.llm.factory import reset_llm_client
    reset_llm_client()

    return {
        "status": "ok",
        "persisted": persisted,
        "persisted_fields": sorted(persistable_changes) if persisted else [],
        "session_only_fields": session_only_fields,
        "secret_persistence": (
            "session_only"
            if session_only_fields
            else "reference_only"
            if reference_fields
            else "not_applicable"
        ),
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
    hook = await mgr.register(
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
    if not await mgr.delete(webhook_id, principal.tenant_id):
        raise HTTPException(404, "Webhook 不存在")
    return {"deleted": webhook_id}
