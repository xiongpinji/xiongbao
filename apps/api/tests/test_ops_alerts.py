"""ops 告警 webhook 端点测试（P1 告警联动）。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.infra.settings import get_settings
from xagent.main import create_app

_PAYLOAD = {
    "status": "firing",
    "receiver": "critical-webhook",
    "commonLabels": {"severity": "critical"},
    "alerts": [
        {
            "labels": {"alertname": "HighErrorRate", "severity": "critical"},
            "annotations": {"summary": "5xx 率超阈值"},
            "startsAt": "2026-08-03T00:00:00Z",
            "fingerprint": "fp-001",
        },
        {
            "labels": {"alertname": "HighP99Latency", "severity": "warning"},
            "annotations": {"summary": "P99 延迟偏高"},
            "startsAt": "2026-08-03T00:01:00Z",
            "fingerprint": "fp-002",
        },
    ],
}


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_webhook_disabled_when_token_unset(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("XAGENT_SECURITY__ALERT_WEBHOOK_TOKEN", "")
    get_settings.cache_clear()
    try:
        resp = await client.post("/api/v1/ops/alerts/webhook", json=_PAYLOAD)
        assert resp.status_code == 503
    finally:
        get_settings.cache_clear()


async def test_webhook_rejects_wrong_token(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("XAGENT_SECURITY__ALERT_WEBHOOK_TOKEN", "secret-token")
    get_settings.cache_clear()
    try:
        resp = await client.post(
            "/api/v1/ops/alerts/webhook",
            json=_PAYLOAD,
            headers={"X-Alert-Token": "wrong"},
        )
        assert resp.status_code == 401
        resp2 = await client.post("/api/v1/ops/alerts/webhook", json=_PAYLOAD)
        assert resp2.status_code == 401
    finally:
        get_settings.cache_clear()


async def test_webhook_persists_and_lists(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("XAGENT_SECURITY__ALERT_WEBHOOK_TOKEN", "secret-token")
    get_settings.cache_clear()
    try:
        resp = await client.post(
            "/api/v1/ops/alerts/webhook",
            json=_PAYLOAD,
            headers={"X-Alert-Token": "secret-token"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"received": 2, "group_status": "firing"}

        # 列表端点需 system:read 权限——lite 默认 admin token 有 admin 角色
        login = await client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
        )
        token = login.json()["access_token"]
        lst = await client.get(
            "/api/v1/ops/alerts", headers={"Authorization": f"Bearer {token}"}
        )
        assert lst.status_code == 200, lst.text
        alerts = lst.json()["alerts"]
        names = {a["alertname"] for a in alerts}
        assert {"HighErrorRate", "HighP99Latency"} <= names
        by_name = {a["alertname"]: a for a in alerts}
        assert by_name["HighErrorRate"]["severity"] == "critical"
        assert by_name["HighP99Latency"]["fingerprint"] == "fp-002"
    finally:
        get_settings.cache_clear()
