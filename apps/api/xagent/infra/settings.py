"""集中配置：所有运行参数走 pydantic-settings，环境变量前缀 ``XAGENT_``。

设计要点：
- 单一 ``Settings`` 对象，按域分组为嵌套 ``BaseModel``（llm / memory / observability ...）。
- ``XAGENT_MODE`` 控制运行模式（lite / full / enterprise），adapters 工厂据此选择实现或降级。
- 嵌套字段用双下划线分隔：``XAGENT_LLM__PROXY_URL``、``XAGENT_DB__URL`` 等。
- 提供 ``get_settings()`` 单例（lru_cache），便于依赖注入与测试覆盖。
"""

from __future__ import annotations

# 项目根目录（xagent/），.env 在此；不依赖 CWD。
# 支持 XAGENT_ENV_FILE 显式覆盖（容器/自定义部署）；否则从包位置向上探测
# 含 .env 或 pyproject.toml 的目录；探测不到（如容器内浅布局）则退化为
# 不可达路径——此时配置完全来自环境变量，不致命。
import os as _os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from xagent.infra.paths import data_path
from xagent.infra.secrets import resolve_settings_secrets


def _detect_project_root(start: Path) -> Path:
    candidates = [start, *start.parents]
    # 优先：向上找到第一个真实存在的 .env（仓库根布局）
    for parent in candidates:
        if (parent / ".env").exists():
            return parent
    # 兜底：第一个含 pyproject.toml 的目录（包布局）
    for parent in candidates:
        if (parent / "pyproject.toml").exists():
            return parent
    return start  # 探测失败：返回包目录，.env 视为不存在


_PROJECT_ROOT = _detect_project_root(Path(__file__).resolve().parent)
_ENV_FILE = (
    Path(_os.environ["XAGENT_ENV_FILE"])
    if _os.environ.get("XAGENT_ENV_FILE")
    else _PROJECT_ROOT / ".env"
)

_INSECURE_JWT_SECRETS = {
    "",
    "dev-insecure-lite-jwt-secret-for-local-only",
    "dev-insecure-change-me",
    "change-me",
    "change-me-to-random",
    "change-me-to-a-long-random-secret",
}
_MIN_PRODUCTION_JWT_SECRET_LENGTH = 32


class RunMode(str, Enum):  # noqa: UP042  (兼容 py3.11，不用 StrEnum)
    """运行模式。"""

    lite = "lite"          # 单机/桌面/演示：SQLite + 内存缓存 + Qdrant 内存 + 内置 JWT
    full = "full"          # 单机生产/试点：Postgres + Redis + Qdrant + Langfuse + LiteLLM
    enterprise = "enterprise"  # 多区域 HA（后做）


class DatabaseSettings(BaseModel):
    """关系数据库。lite 默认 SQLite，full 用 Postgres。"""

    url: str = "sqlite+aiosqlite:///./xagent.db"
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20


class CacheSettings(BaseModel):
    """Redis 缓存。空 URL 时降级为进程内存缓存。"""

    redis_url: str = ""        # 例如 redis://localhost:6379/0
    default_ttl_seconds: int = 300


class LLMSettings(BaseModel):
    """LLM 网关（LiteLLM）。

    优先级：proxy_url > ollama_base_url > 直连 provider key。
    - proxy_url 非空：走 LiteLLM Proxy（full 模式）。
    - ollama_base_url 非空：走本地 Ollama（lite/本地部署，零 API 费用）。
    - 否则：直连 provider（需 openai/anthropic/deepseek key）。
    """

    proxy_url: str = ""                  # 例如 http://localhost:4000
    proxy_api_key: str = ""
    default_model: str = "gpt-4o-mini"
    fallback_models: list[str] = Field(default_factory=lambda: ["gpt-4o-mini"])
    # 本地 Ollama（零费用本地推理）
    ollama_base_url: str = ""            # 例如 http://localhost:11434
    ollama_model: str = ""               # 例如 qwen3:4b（为空则用 default_model）
    request_timeout_seconds: int = 60
    warmup_enabled: bool = False
    warmup_prompt: str = "回复一个字：好"
    warmup_max_tokens: int = 8
    warmup_wait_timeout_seconds: int = 30
    warmup_poll_interval_seconds: float = 1.0
    # 直连模式下的 provider key（full 模式建议在 LiteLLM Proxy 侧配置）
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""


class MemorySettings(BaseModel):
    """记忆 / 向量库。lite 用 Qdrant :memory: 内存模式。"""

    qdrant_url: str = ""                 # 空 => 本地磁盘模式（见 qdrant_local_path）
    qdrant_api_key: str = ""
    qdrant_local_path: str = ""          # 空 => 默认 apps/data/qdrant；测试可指向临时目录避免独占锁
    collection: str = "xagent_memory"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    backend: str = "qdrant"              # qdrant | mem0 (Phase1)


class MediaSettings(BaseModel):
    """媒体生成（短剧工厂）多模型 provider 配置。

    图像：OpenAI 兼容（gpt-image-2 / DALL·E）。
    视频：可灵 Kling / 即梦 Jimeng / 通用任务式 HTTP。
    全部为空时用 NullProvider（占位产物，流程不中断）。
    """

    # 默认 provider 选择（image/video/audio）
    default_image_provider: str = "null"   # null | openai
    default_video_provider: str = "null"   # null | kling | jimeng | generic
    default_audio_provider: str = "null"   # null | edge_tts（免 key 但需外网，故默认 null）
    tts_output_dir: str = Field(default_factory=lambda: str(data_path("tts")))

    # 图像（OpenAI 兼容）
    openai_image_api_key: str = ""
    openai_image_base_url: str = "https://api.openai.com/v1"
    openai_image_model: str = "gpt-image-2"

    # 视频（火山方舟 Seedance）
    volcano_ark_api_key: str = ""
    volcano_ark_base_url: str = "https://ark.cn-beijing.volces.com"
    volcano_ark_model: str = "doubao-seedance-2-0-260128"

    # 视频（可灵）
    kling_api_key: str = ""
    kling_submit_url: str = ""
    kling_poll_url: str = ""               # 含 {task_id}

    # 视频（即梦）
    jimeng_api_key: str = ""
    jimeng_submit_url: str = ""
    jimeng_poll_url: str = ""

    # 视频（通用任务式）
    generic_video_api_key: str = ""
    generic_video_submit_url: str = ""
    generic_video_poll_url: str = ""
    generic_video_model: str = ""

    poll_interval_seconds: int = 3
    task_timeout_seconds: int = 600


class ObservabilitySettings(BaseModel):
    """Langfuse + OpenTelemetry。key 为空时 trace 转为本地 no-op。"""

    langfuse_host: str = ""              # 例如 http://localhost:3000
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    otel_endpoint: str = ""
    service_name: str = "xagent-api"
    enable_prometheus: bool = True


class RecoverySettings(BaseModel):
    """自动恢复引擎配置。"""

    enabled: bool = True
    max_consecutive_llm_timeouts: int = 3
    fallback_on_llm_failure: bool = True
    worker_restart_threshold: int = 5
    evidence_output_dir: str = Field(
        default_factory=lambda: str(data_path("recovery-evidence"))
    )


class SecuritySettings(BaseModel):
    """鉴权与安全。"""

    jwt_secret: str = "dev-insecure-lite-jwt-secret-for-local-only"  # noqa: S105
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60
    # Keycloak（full/enterprise），lite 用内置 JWT
    keycloak_url: str = ""
    keycloak_realm: str = "xagent"
    # None = 安全默认（所有模式含 lite 都开鉴权）；
    # 显式 False（XAGENT_SECURITY__REQUIRE_AUTH=false）是唯一逃生门，启动时打 warning
    require_auth: bool | None = None
    # OIDC 验签（RS256）：配置 jwks_url 后，Bearer token 走 OIDC 验签而非 HS256
    oidc_jwks_url: str = ""
    oidc_issuer: str = ""
    # OIDC 浏览器登录链路（RFC-002 Authorization Code Flow）：
    # 未配置 oidc_client_id 时 /auth/oidc/* 端点返回 501（安全默认不暴露）
    oidc_client_id: str = ""
    oidc_client_secret: str = ""  # 仅走环境变量/secret 管理
    oidc_redirect_uri: str = "http://localhost:8000/api/v1/auth/oidc/callback"
    oidc_scopes: str = "openid profile email"
    # ── 全局限流（RateLimitMiddleware，按客户端 IP 滑动窗口）──
    # 默认与历史硬编码行为一致：300 req / 60s / IP，/health /ready /metrics 豁免。
    # enabled=false 整体关闭（压测/受信内网）；exempt_paths 自定义豁免前缀清单。
    # env 示例：XAGENT_SECURITY__RATE_LIMIT_ENABLED=false
    #          XAGENT_SECURITY__RATE_LIMIT_REQUESTS=1000
    #          XAGENT_SECURITY__RATE_LIMIT_EXEMPT_PATHS='["/health","/metrics"]'
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 300
    rate_limit_window_seconds: int = 60
    rate_limit_exempt_paths: list[str] = Field(
        default_factory=lambda: ["/health", "/ready", "/metrics"]
    )
    # 告警 webhook 共享令牌（Alertmanager → /api/v1/ops/alerts/webhook）；
    # 空 = 端点 503 禁用。env：XAGENT_SECURITY__ALERT_WEBHOOK_TOKEN
    alert_webhook_token: str = ""


class ToolsSettings(BaseModel):
    """执行类工具安全门禁。

    ``enable_shell`` / ``enable_python_exec`` 默认 False：shell_exec / python_exec
    工具不注册，即使被直接调用也返回「已被配置禁用」。仅在显式设置
    XAGENT_TOOLS__ENABLE_SHELL / XAGENT_TOOLS__ENABLE_PYTHON_EXEC=true 时放开。
    """

    enable_shell: bool = False
    enable_python_exec: bool = False


class SandboxSettings(BaseModel):
    """沙箱后端选择（RFC-001 分级：L0 disabled / L1 docker / L2 e2b）。

    默认 ``disabled``：lite 模式禁执行，绝不在宿主机直接 exec 不可信代码。
    显式设置 ``XAGENT_SANDBOX__BACKEND=docker`` 后，shell/python 执行路由进
    一次性隔离容器（默认 --network=none、资源限额、只读根 fs）。
    """

    backend: str = "disabled"          # disabled | docker | e2b
    docker_image: str = "python:3.11-slim"
    mem_limit: str = "512m"            # Docker --memory
    cpu_quota: int = 100000            # Docker --cpu-quota（100000 = 1 CPU）
    network_disabled: bool = True      # 默认 --network=none
    readonly_rootfs: bool = True       # 默认 --read-only
    timeout_seconds: int = 30          # 单次执行超时
    # ── L2：E2B 云沙箱（见 adapters/sandbox/e2b_sandbox.py、docs/deployment/sandbox.md）
    e2b_api_key: str = ""              # 也可读 E2B_API_KEY 环境变量
    e2b_template: str = "code-interpreter"
    e2b_base_url: str = "https://api.e2b.dev"  # 官方云，可指自托管网关


class Settings(BaseSettings):
    """根配置对象。"""

    model_config = SettingsConfigDict(
        env_prefix="XAGENT_",
        env_nested_delimiter="__",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "X-Agent"
    mode: RunMode = RunMode.lite
    debug: bool = False
    # 生产禁止用 "*"，启动时校验
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    media: MediaSettings = Field(default_factory=MediaSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    recovery: RecoverySettings = Field(default_factory=RecoverySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    tools: ToolsSettings = Field(default_factory=ToolsSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)

    @model_validator(mode="after")
    def _resolve_secret_refs(self) -> Settings:
        """加载后对 secret 字段统一解析 ``SECRETREF:`` 引用（见 infra/secrets.py）。

        无 ``SECRETREF:`` 前缀的值原样保留，现有行为不变。
        """
        return cast(Settings, resolve_settings_secrets(self))

    @property
    def is_lite(self) -> bool:
        return self.mode == RunMode.lite

    @property
    def is_production(self) -> bool:
        return self.mode in (RunMode.full, RunMode.enterprise)

    @property
    def auth_required(self) -> bool:
        """有效鉴权开关：安全默认全开（含 lite）。

        显式 ``XAGENT_SECURITY__REQUIRE_AUTH=false`` 是唯一逃生门（演示用途），
        关闭时启动日志打 warning，且匿名 Principal 为空角色（只读公开端点）。
        """
        if self.security.require_auth is not None:
            return self.security.require_auth
        return True

    def validate_for_production(self) -> list[str]:
        """返回生产模式下的配置问题清单（空列表表示通过）。"""
        problems: list[str] = []
        if self.is_production:
            if "*" in self.cors_origins:
                problems.append("生产模式禁止 CORS 通配符 '*'")
            jwt_secret = self.security.jwt_secret.strip()
            if (
                jwt_secret in _INSECURE_JWT_SECRETS
                or len(jwt_secret) < _MIN_PRODUCTION_JWT_SECRET_LENGTH
            ):
                problems.append(
                    "生产模式必须设置至少 32 字符的 XAGENT_SECURITY__JWT_SECRET"
                )
            if self.security.require_auth is False:
                problems.append("生产模式不允许关闭鉴权 (require_auth=False)")
            # RFC-001：生产模式开启 shell/python 执行时必须有真实隔离边界，
            # 禁止宿主机裸奔执行（backend 必须为 docker / e2b）。
            exec_enabled = (
                self.tools.enable_shell or self.tools.enable_python_exec
            )
            if exec_enabled and self.sandbox.backend not in ("docker", "e2b"):
                problems.append(
                    "生产模式开启 shell/python 执行时，必须配置沙箱后端："
                    "XAGENT_SANDBOX__BACKEND=docker（或 e2b），"
                    "禁止在宿主机直接执行不可信代码"
                )
        return problems


@lru_cache
def get_settings() -> Settings:
    """全局配置单例。测试可用 ``get_settings.cache_clear()`` 重置。"""
    return Settings()
