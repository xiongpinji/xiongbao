"""secretRef 引用解析测试（infra/secrets.py + settings.py 挂点）。"""

from __future__ import annotations

import pytest
from xagent.infra import secrets as secrets_mod
from xagent.infra.secrets import (
    SECRETREF_PREFIX,
    SecretRefError,
    is_secret_ref,
    resolve_secret,
)
from xagent.infra.settings import RunMode, Settings


def _settings(mode: RunMode = RunMode.lite, **overrides) -> Settings:
    """构造 Settings，忽略真实环境变量与 .env 干扰。"""
    return Settings(_env_file=None, mode=mode, **overrides)  # type: ignore[call-arg]


# ── is_secret_ref ────────────────────────────────────────────────

def test_is_secret_ref():
    assert is_secret_ref(f"{SECRETREF_PREFIX}file:/tmp/x")
    assert is_secret_ref(f"{SECRETREF_PREFIX}env:FOO")
    assert not is_secret_ref("plain-value")
    assert not is_secret_ref("")
    assert not is_secret_ref(None)
    assert not is_secret_ref(123)


# ── file ref ─────────────────────────────────────────────────────

def test_resolve_file_ref(tmp_path):
    secret_file = tmp_path / "jwt.secret"
    secret_file.write_text("super-secret-value\n", encoding="utf-8")
    result = resolve_secret(f"{SECRETREF_PREFIX}file:{secret_file}")
    assert result == "super-secret-value"


def test_resolve_file_ref_strips_whitespace(tmp_path):
    secret_file = tmp_path / "key.secret"
    secret_file.write_text("  padded-secret  \n\n", encoding="utf-8")
    assert resolve_secret(f"{SECRETREF_PREFIX}file:{secret_file}") == "padded-secret"


def test_missing_file_fail_fast_production(tmp_path):
    with pytest.raises(SecretRefError, match="文件不存在"):
        resolve_secret(f"{SECRETREF_PREFIX}file:{tmp_path}/nope.secret", lite=False)


def test_missing_file_lite_degrades(tmp_path, caplog):
    with caplog.at_level("WARNING", logger=secrets_mod.logger.name):
        result = resolve_secret(f"{SECRETREF_PREFIX}file:{tmp_path}/nope.secret", lite=True)
    assert result == ""
    assert any("secretRef 解析失败" in rec.message for rec in caplog.records)


# ── env ref ──────────────────────────────────────────────────────

def test_resolve_env_ref(monkeypatch):
    monkeypatch.setenv("REAL_SECRET", "from-env-value")
    assert resolve_secret(f"{SECRETREF_PREFIX}env:REAL_SECRET") == "from-env-value"


def test_missing_env_fail_fast_production(monkeypatch):
    monkeypatch.delenv("MISSING_SECRET", raising=False)
    with pytest.raises(SecretRefError, match="环境变量未设置"):
        resolve_secret(f"{SECRETREF_PREFIX}env:MISSING_SECRET", lite=False)


def test_missing_env_lite_degrades(monkeypatch, caplog):
    monkeypatch.delenv("MISSING_SECRET", raising=False)
    with caplog.at_level("WARNING", logger=secrets_mod.logger.name):
        assert resolve_secret(f"{SECRETREF_PREFIX}env:MISSING_SECRET", lite=True) == ""
    assert any("secretRef 解析失败" in rec.message for rec in caplog.records)


# ── 非 ref 透传 ──────────────────────────────────────────────────

def test_plain_value_passthrough():
    assert resolve_secret("plain-secret") == "plain-secret"
    assert resolve_secret("") == ""


# ── vault 预留位 ─────────────────────────────────────────────────

def test_vault_ref_not_implemented():
    with pytest.raises(SecretRefError, match="预留扩展位"):
        resolve_secret(f"{SECRETREF_PREFIX}vault:secret/data/x#key", lite=False)


def test_unknown_scheme_fail_fast():
    with pytest.raises(SecretRefError, match="不支持的 secretRef scheme"):
        resolve_secret(f"{SECRETREF_PREFIX}aws:sm/x", lite=False)


def test_malformed_ref_fail_fast():
    with pytest.raises(SecretRefError, match="非法 secretRef 语法"):
        resolve_secret(f"{SECRETREF_PREFIX}file", lite=False)


# ── Settings 挂点 ────────────────────────────────────────────────

def test_settings_resolves_secret_fields(tmp_path):
    secret_file = tmp_path / "jwt.secret"
    secret_file.write_text("a" * 40, encoding="utf-8")
    s = _settings(
        security={"jwt_secret": f"{SECRETREF_PREFIX}file:{secret_file}"},
        llm={"openai_api_key": f"{SECRETREF_PREFIX}env:TEST_OPENAI_KEY"},
    )
    assert s.security.jwt_secret == "a" * 40


def test_settings_resolves_env_ref(monkeypatch):
    monkeypatch.setenv("TEST_RESOLVED_DB_URL", "postgresql+asyncpg://u:p@db:5432/x")
    s = _settings(db={"url": f"{SECRETREF_PREFIX}env:TEST_RESOLVED_DB_URL"})
    assert s.db.url == "postgresql+asyncpg://u:p@db:5432/x"


def test_settings_plain_values_unchanged():
    s = _settings(security={"jwt_secret": "plain-jwt-secret"})
    assert s.security.jwt_secret == "plain-jwt-secret"


def test_settings_production_fail_fast(tmp_path):
    with pytest.raises(SecretRefError, match="security.jwt_secret"):
        _settings(
            mode=RunMode.full,
            security={"jwt_secret": f"{SECRETREF_PREFIX}file:{tmp_path}/missing.secret"},
        )


def test_settings_lite_degrades_to_empty(tmp_path):
    s = _settings(
        mode=RunMode.lite,
        security={"jwt_secret": f"{SECRETREF_PREFIX}file:{tmp_path}/missing.secret"},
    )
    assert s.security.jwt_secret == ""


def test_settings_error_message_never_leaks_target_secret(monkeypatch):
    monkeypatch.setenv("LEAK_GUARD", "actual-secret-value")
    s = _settings(llm={"proxy_api_key": f"{SECRETREF_PREFIX}env:LEAK_GUARD"})
    assert s.llm.proxy_api_key == "actual-secret-value"
    # SecretRefError 消息只含 scheme/target，不含解析出的值
    try:
        resolve_secret(f"{SECRETREF_PREFIX}env:DEFINITELY_MISSING_VAR", lite=False)
    except SecretRefError as exc:
        assert "DEFINITELY_MISSING_VAR" in str(exc)
