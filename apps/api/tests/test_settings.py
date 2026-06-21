"""配置与生产校验测试。"""

from __future__ import annotations

import pytest
from xagent.infra.settings import RunMode, Settings


def test_lite_defaults() -> None:
    s = Settings(mode=RunMode.lite)
    assert s.is_lite
    assert not s.is_production
    assert s.db.url.startswith("sqlite")
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


def test_nested_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAGENT_LLM__DEFAULT_MODEL", "claude-3-5-sonnet")
    monkeypatch.setenv("XAGENT_DB__ECHO", "true")
    s = Settings()
    assert s.llm.default_model == "claude-3-5-sonnet"
    assert s.db.echo is True
