"""pytest fixtures：默认强制 lite 模式 + 关闭外部依赖，保证测试离线可跑。"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _lite_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个测试都跑在干净的 lite 配置下。"""
    # 清掉可能污染的环境变量
    for k in list(os.environ):
        if k.startswith("XAGENT_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("XAGENT_MODE", "lite")

    # 重置所有 lru_cache 单例
    from xagent.adapters.audio import get_stt, get_tts
    from xagent.adapters.browser import get_browser_agent
    from xagent.adapters.coding import get_coding_agent
    from xagent.adapters.desktop_auto import get_desktop_agent
    from xagent.adapters.llm import reset_llm_client
    from xagent.adapters.mcp import reset_mcp_manager
    from xagent.adapters.memory import reset_memory
    from xagent.adapters.observability import reset_tracer
    from xagent.adapters.sandbox import reset_sandbox
    from xagent.adapters.storage import reset_object_store
    from xagent.adapters.tools import reset_tool_registry
    from xagent.core.agents import reset_role_registry
    from xagent.core.workflow import reset_engine
    from xagent.domains.billing import reset_billing_service
    from xagent.domains.creative_studio.media import reset_media_registry
    from xagent.domains.open_source_discovery import reset_discovery_engine
    from xagent.enterprise.audit import reset_audit_log
    from xagent.enterprise.auth.users import reset_user_store
    from xagent.enterprise.authz import reset_enforcer
    from xagent.infra.cache import reset_cache
    from xagent.infra.settings import get_settings
    from xagent.worker import reset_task_runner

    get_settings.cache_clear()
    reset_llm_client()
    reset_tracer()
    reset_memory()
    reset_cache()
    reset_tool_registry()
    reset_role_registry()
    reset_enforcer()
    reset_audit_log()
    reset_user_store()
    reset_billing_service()
    reset_task_runner()
    reset_mcp_manager()
    reset_sandbox()
    reset_object_store()
    reset_engine()
    reset_media_registry()
    reset_discovery_engine()
    get_browser_agent.cache_clear()
    get_desktop_agent.cache_clear()
    get_coding_agent.cache_clear()
    get_stt.cache_clear()
    get_tts.cache_clear()
    # 清空进程内草稿存储（creative-studio 测试隔离）
    from xagent.api.v1 import creative_studio as _cs

    _cs._drafts.clear()
    # 清空 task 租户映射
    from xagent.api.v1 import tasks as _tasks

    _tasks._task_tenants.clear()
    yield
    get_settings.cache_clear()
