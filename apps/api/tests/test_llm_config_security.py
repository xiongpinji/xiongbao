"""LLM 配置持久化不得把明文密钥写入磁盘。"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.api.v1 import system as system_module
from xagent.enterprise.auth import create_access_token
from xagent.infra.settings import RunMode, get_settings
from xagent.main import create_app


@pytest.fixture
async def client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        system_module,
        "_LLM_OVERRIDES_PATH",
        tmp_path / "llm_config_overrides.json",
    )
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value
    get_settings.cache_clear()


def _headers() -> dict[str, str]:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    return {"Authorization": f"Bearer {token}"}


async def test_plaintext_key_is_session_only(client: AsyncClient) -> None:
    response = await client.put(
        "/api/v1/system/llm-config",
        json={"openai_api_key": "session-secret"},
        headers=_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["secret_persistence"] == "session_only"
    assert body["session_only_fields"] == ["openai_api_key"]
    assert body["persisted_fields"] == []
    assert get_settings().llm.openai_api_key == "session-secret"
    stored = json.loads(system_module._LLM_OVERRIDES_PATH.read_text(encoding="utf-8"))
    assert "openai_api_key" not in stored
    assert "session-secret" not in system_module._LLM_OVERRIDES_PATH.read_text(
        encoding="utf-8"
    )


async def test_secret_ref_is_persisted_but_runtime_receives_value(
    client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setenv("XAGENT_TEST_OPENAI_KEY", "resolved-secret")
    reference = "SECRETREF:env:XAGENT_TEST_OPENAI_KEY"

    response = await client.put(
        "/api/v1/system/llm-config",
        json={"openai_api_key": reference},
        headers=_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["secret_persistence"] == "reference_only"
    assert body["session_only_fields"] == []
    assert body["persisted_fields"] == ["openai_api_key"]
    assert get_settings().llm.openai_api_key == "resolved-secret"
    stored = json.loads(system_module._LLM_OVERRIDES_PATH.read_text(encoding="utf-8"))
    assert stored == {"openai_api_key": reference}

    read_response = await client.get("/api/v1/system/llm-config", headers=_headers())
    serialized = read_response.text
    assert read_response.json()["has_openai_key"] is True
    assert reference not in serialized
    assert "resolved-secret" not in serialized


def test_historic_plaintext_override_fails_closed_in_full_mode(
    monkeypatch, tmp_path
) -> None:
    path = tmp_path / "llm_config_overrides.json"
    path.write_text('{"openai_api_key":"historic-secret"}', encoding="utf-8")
    monkeypatch.setattr(system_module, "_LLM_OVERRIDES_PATH", path)

    with pytest.raises(RuntimeError, match="openai_api_key"):
        system_module._load_llm_overrides(mode=RunMode.full)


def test_historic_plaintext_override_is_ignored_in_lite_mode(
    monkeypatch, tmp_path
) -> None:
    path = tmp_path / "llm_config_overrides.json"
    path.write_text(
        '{"openai_api_key":"historic-secret","proxy_url":"http://proxy"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(system_module, "_LLM_OVERRIDES_PATH", path)
    warnings: list[tuple[str, dict]] = []

    class _Logger:
        def warning(self, event: str, **values) -> None:
            warnings.append((event, values))

    monkeypatch.setattr(system_module, "logger", _Logger())

    loaded = system_module._load_llm_overrides(mode=RunMode.lite)

    assert loaded == {"proxy_url": "http://proxy"}
    assert warnings == [
        ("llm_plaintext_overrides_ignored", {"fields": ["openai_api_key"]})
    ]


def test_llm_override_save_uses_private_atomic_writer(monkeypatch, tmp_path) -> None:
    target = tmp_path / "llm_config_overrides.json"
    monkeypatch.setattr(system_module, "_LLM_OVERRIDES_PATH", target)
    calls: list[tuple[object, object]] = []

    monkeypatch.setattr(
        system_module,
        "write_private_json",
        lambda path, value: calls.append((path, value)),
    )

    system_module._save_llm_overrides({"proxy_url": "http://proxy"})

    assert calls == [(target, {"proxy_url": "http://proxy"})]
