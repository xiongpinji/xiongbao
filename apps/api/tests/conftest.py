"""pytest fixtures：默认强制 lite 模式 + 关闭外部依赖，保证测试离线可跑。"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

# --- 测试隔离：阻断仓库根 .env 泄漏真实密钥 ---------------------------------
# xagent.infra.settings 在模块加载时把 ``仓库根/.env`` 烤进
# ``Settings.model_config['env_file']``，仅清 XAGENT_* 环境变量无法阻止
# pydantic-settings 从该文件读取真实 key（lite 测试会误用真实 LLM）。
# 此处必须在**任何** get_settings()/Settings() 首次调用之前执行，
# 因此放在 conftest 模块顶层（pytest 最先加载 conftest，早于测试模块 import）。
_EMPTY_ENV_FILE = Path(tempfile.gettempdir()) / "xagent_pytest_empty.env"
_EMPTY_ENV_FILE.touch(exist_ok=True)

from xagent.infra import settings as _settings_mod  # noqa: E402

_settings_mod._ENV_FILE = _EMPTY_ENV_FILE  # 防止后续代码再引用
_settings_mod.Settings.model_config["env_file"] = str(_EMPTY_ENV_FILE)
_settings_mod.get_settings.cache_clear()
# ---------------------------------------------------------------------------

# --- 每进程独立测试库（工作流 D）---------------------------------------------
# 见 _lite_env 中的说明；在模块顶层计算一次，保证全进程所有测试同一库。
_PID_DB_PATH = Path(tempfile.gettempdir()) / f"xagent_pytest_{os.getpid()}.db"
_PID_DB_PATH.unlink(missing_ok=True)  # 可能残留上次同 pid 崩溃的库，确保全新起步
_PID_DB_URL = f"sqlite+aiosqlite:///{_PID_DB_PATH}"
# ---------------------------------------------------------------------------

# --- 每进程独立 qdrant 本地库（主控补）----------------------------------------
# qdrant 本地磁盘模式带独占文件锁，默认路径 apps/data/qdrant 会被开发服务器
# /其他 pytest 进程持有导致 RuntimeError；指到每进程独立目录彻底隔离。
_PID_QDRANT_PATH = Path(tempfile.gettempdir()) / f"xagent_pytest_qdrant_{os.getpid()}"
if _PID_QDRANT_PATH.exists():
    import shutil as _shutil

    _shutil.rmtree(_PID_QDRANT_PATH, ignore_errors=True)  # 清理同 pid 崩溃残留
_PID_QDRANT_PATH.mkdir(parents=True, exist_ok=True)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _lite_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个测试都跑在干净的 lite 配置下。"""
    # 清掉可能污染的环境变量
    for k in list(os.environ):
        if k.startswith("XAGENT_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("XAGENT_MODE", "lite")
    monkeypatch.setenv("XAGENT_MEMORY__QDRANT_LOCAL_PATH", str(_PID_QDRANT_PATH))
    # 测试 DB 隔离（工作流 D 补充）：默认库 ./xagent.db 是开发库且被并行
    # pytest 进程/开发服务器共享，并发运行会互相清表/写审计导致断言抖动。
    # 每个 pytest 进程使用独立的临时 SQLite 库；单个测试仍可用
    # monkeypatch.setenv("XAGENT_DB__URL", ...) 覆盖（如 test_persistence）。
    monkeypatch.setenv("XAGENT_DB__URL", _PID_DB_URL)

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
    from xagent.domains.code_review import reset_review_store
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
    reset_review_store()
    get_browser_agent.cache_clear()
    get_desktop_agent.cache_clear()
    get_coding_agent.cache_clear()
    get_stt.cache_clear()
    get_tts.cache_clear()
    # 清空进程内草稿存储（creative-studio 测试隔离）
    from xagent.api.v1 import creative_studio as _cs

    _cs._drafts.clear()
    _cs._productions.clear()
    _cs._media_task_tenants.clear()
    _cs._media_runtime_tasks.clear()
    _cs._production_runtime_runs.clear()
    # 清空画布
    from xagent.api.v1 import canvas as _cv

    _cv._canvases.clear()
    _cv._canvas_tenants.clear()
    # 把画布快照路径指向临时位置，避免测试残留
    snapshot_path = Path(tempfile.gettempdir()) / f"canvas_{uuid.uuid4().hex}.json"
    monkeypatch.setattr(_cv, "_CANVAS_SNAPSHOT_PATH", snapshot_path)
    # 清空编辑器时间线
    from xagent.api.v1 import editor as _ed

    _ed._timelines.clear()
    _ed._timeline_tenants.clear()
    from xagent.domains.creative_studio.editor import tools as _et

    _et._timelines.clear()
    # 清空 task 租户映射
    from xagent.api.v1 import tasks as _tasks

    _tasks._task_tenants.clear()
    _tasks._task_metadata.clear()
    yield
    get_settings.cache_clear()
