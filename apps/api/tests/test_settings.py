"""配置与生产校验测试。"""

from __future__ import annotations

import pytest
from xagent.infra.settings import RunMode, Settings


def test_lite_defaults() -> None:
    s = Settings(mode=RunMode.lite)
    assert s.is_lite
    assert not s.is_production
    assert s.db.url.startswith("sqlite")
    assert "http://tauri.localhost" in s.cors_origins
    assert "tauri://localhost" in s.cors_origins
    # lite 默认不应有生产校验问题
    assert s.validate_for_production() == []


def test_production_rejects_wildcard_cors() -> None:
    s = Settings(mode=RunMode.full, cors_origins=["*"])
    problems = s.validate_for_production()
    assert any("CORS" in p for p in problems)


def test_production_rejects_default_jwt() -> None:
    s = Settings(mode=RunMode.full)
    problems = s.validate_for_production()
    assert any("JWT" in p for p in problems)


@pytest.mark.parametrize(
    "jwt_secret",
    [
        "dev-insecure-lite-jwt-secret-for-local-only",
        "dev-insecure-change-me",
        "change-me",
        "change-me-to-random",
        "change-me-to-a-long-random-secret",
        "short-secret",
    ],
)
def test_production_rejects_placeholder_or_short_jwt(jwt_secret: str) -> None:
    s = Settings(mode=RunMode.full)
    s.security.jwt_secret = jwt_secret
    problems = s.validate_for_production()
    assert any("JWT" in p for p in problems)


def test_full_mode_does_not_seed_default_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    from xagent.enterprise.auth.users import get_user_store, reset_user_store
    from xagent.infra.settings import get_settings

    monkeypatch.setenv("XAGENT_MODE", "full")
    get_settings.cache_clear()
    reset_user_store()
    try:
        store = get_user_store()
        assert store.authenticate("admin", "admin") is None
    finally:
        reset_user_store()
        get_settings.cache_clear()


def test_nested_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAGENT_LLM__DEFAULT_MODEL", "claude-3-5-sonnet")
    monkeypatch.setenv("XAGENT_DB__ECHO", "true")
    s = Settings()
    assert s.llm.default_model == "claude-3-5-sonnet"
    assert s.db.echo is True


def test_llm_timeout_and_warmup_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAGENT_LLM__REQUEST_TIMEOUT_SECONDS", "150")
    monkeypatch.setenv("XAGENT_LLM__WARMUP_ENABLED", "true")
    monkeypatch.setenv("XAGENT_LLM__WARMUP_PROMPT", "回复一个字：好")
    monkeypatch.setenv("XAGENT_LLM__WARMUP_MAX_TOKENS", "8")
    s = Settings()
    assert s.llm.request_timeout_seconds == 150
    assert s.llm.warmup_enabled is True
    assert s.llm.warmup_prompt == "回复一个字：好"
    assert s.llm.warmup_max_tokens == 8


def test_llm_warmup_defaults() -> None:
    s = Settings()
    assert s.llm.warmup_enabled is False
    assert s.llm.warmup_prompt == "回复一个字：好"
    assert s.llm.warmup_max_tokens == 8
    assert s.llm.warmup_wait_timeout_seconds == 30
