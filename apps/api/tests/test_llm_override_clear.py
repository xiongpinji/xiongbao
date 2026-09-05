"""LLM 覆盖一键清除：API DELETE 端点 + CLI clear-override 子命令。

运维场景：磁盘 override 优先级高于 env/.env，改环境变量不生效时，
需要一条命令/API 恢复环境来源控制（审计 2026-09-05 F-3）。
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.api.v1 import system as system_module
from xagent.enterprise.auth import create_access_token
from xagent.infra.settings import get_settings
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


async def test_delete_removes_override_file_and_restores_env(client: AsyncClient) -> None:
    system_module._LLM_OVERRIDES_PATH.write_text(
        json.dumps({"default_model": "gpt-5.5", "proxy_url": "https://example.com/v1"}),
        encoding="utf-8",
    )

    resp = await client.delete("/api/v1/system/llm-config/override", headers=_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["cleared"] is True
    assert body["restored_from"] == "env"
    assert body["removed_fields"] == ["default_model", "proxy_url"]
    assert not system_module._LLM_OVERRIDES_PATH.exists()
    # 覆盖移除后，GET 不再报告 override 生效
    cfg = (await client.get("/api/v1/system/llm-config", headers=_headers())).json()
    assert cfg["override_active"] is False


async def test_delete_is_idempotent_when_no_override_exists(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/system/llm-config/override", headers=_headers())

    assert resp.status_code == 200
    assert resp.json()["cleared"] is True
    assert resp.json()["removed_fields"] == []


async def test_delete_requires_auth(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/system/llm-config/override")
    assert resp.status_code == 401


async def test_delete_recovers_from_corrupt_override_file(client: AsyncClient) -> None:
    system_module._LLM_OVERRIDES_PATH.write_text("{not-json", encoding="utf-8")

    resp = await client.delete("/api/v1/system/llm-config/override", headers=_headers())

    assert resp.status_code == 200
    assert resp.json()["removed_fields"] == []
    assert not system_module._LLM_OVERRIDES_PATH.exists()


def test_cli_clear_override_removes_file_with_backup(tmp_path, monkeypatch) -> None:
    from xagent import cli as cli_module
    from xagent.infra import paths as paths_module

    override = tmp_path / "llm_config_overrides.json"
    override.write_text(
        json.dumps({"default_model": "gpt-5.5"}), encoding="utf-8"
    )
    monkeypatch.setattr(paths_module, "data_path", lambda _name: override)

    rc = cli_module.main(["config", "clear-override"])

    assert rc == 0
    assert not override.exists()
    assert json.loads(override.with_name(override.name + ".bak").read_text("utf-8")) == {
        "default_model": "gpt-5.5"
    }


def test_cli_clear_override_no_backup(tmp_path, monkeypatch) -> None:
    from xagent import cli as cli_module
    from xagent.infra import paths as paths_module

    override = tmp_path / "llm_config_overrides.json"
    override.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths_module, "data_path", lambda _name: override)

    rc = cli_module.main(["config", "clear-override", "--no-backup"])

    assert rc == 0
    assert not override.exists()
    assert not override.with_name(override.name + ".bak").exists()


def test_cli_clear_override_idempotent_when_missing(tmp_path, monkeypatch) -> None:
    from xagent import cli as cli_module
    from xagent.infra import paths as paths_module

    monkeypatch.setattr(
        paths_module, "data_path", lambda _name: tmp_path / "llm_config_overrides.json"
    )

    assert cli_module.main(["config", "clear-override"]) == 0
