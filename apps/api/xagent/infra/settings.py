"""集中配置：所有运行参数走 pydantic-settings，环境变量前缀 ``XAGENT_``。

设计要点：
- 单一 ``Settings`` 对象，按域分组为嵌套 ``BaseModel``（llm / memory / observability ...）。
- ``XAGENT_MODE`` 控制运行模式（lite / full / enterprise），adapters 工厂据此选择实现或降级。
- 嵌套字段用双下划线分隔：``XAGENT_LLM__PROXY_URL``、``XAGENT_DB__URL`` 等。
- 提供 ``get_settings()`` 单例（lru_cache），便于依赖注入与测试覆盖。
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    qdrant_url: str = ""                 # 空 => 内存模式 ":memory:"
    qdrant_api_key: str = ""
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

    # 默认 provider 选择（image/video）
    default_image_provider: str = "null"   # null | openai
    default_video_provider: str = "null"   # null | kling | jimeng | generic

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


class SecuritySettings(BaseModel):
    """鉴权与安全。"""

    jwt_secret: str = "dev-insecure-lite-jwt-secret-for-local-only"  # noqa: S105
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60
    # Keycloak（full/enterprise），lite 用内置 JWT
    keycloak_url: str = ""
    keycloak_realm: str = "xagent"
    # None = 按模式推断（lite 关、生产开）；显式 True/False 覆盖
    require_auth: bool | None = None
    # OIDC 验签（RS256）：配置 jwks_url 后，Bearer token 走 OIDC 验签而非 HS256
    oidc_jwks_url: str = ""
    oidc_issuer: str = ""


class Settings(BaseSettings):
    """根配置对象。"""

    model_config = SettingsConfigDict(
        env_prefix="XAGENT_",
        env_nested_delimiter="__",
        env_file=".env",
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
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    @property
    def is_lite(self) -> bool:
        return self.mode == RunMode.lite

    @property
    def is_production(self) -> bool:
        return self.mode in (RunMode.full, RunMode.enterprise)

    @property
    def auth_required(self) -> bool:
        """有效鉴权开关：显式设置优先，否则 lite 关、生产开。"""
        if self.security.require_auth is not None:
            return self.security.require_auth
        return self.is_production

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
        return problems


@lru_cache
def get_settings() -> Settings:
    """全局配置单例。测试可用 ``get_settings.cache_clear()`` 重置。"""
    return Settings()
