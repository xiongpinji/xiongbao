"""安全中间件测试：限流 + 安全响应头。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_security_headers_present(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


async def test_rate_limit_exempt_for_health(client: AsyncClient) -> None:
    # /health 豁免限流，多次请求不应 429
    for _ in range(30):
        resp = await client.get("/health")
        assert resp.status_code == 200


async def test_rate_limit_triggers() -> None:
    """构造低阈值实例验证限流生效。"""
    from fastapi import FastAPI
    from xagent.api.security_middleware import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, max_requests=3, window_seconds=60)

    @app.get("/api/test")
    async def _t():
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        codes = []
        for _ in range(5):
            codes.append((await c.get("/api/test")).status_code)
    assert 429 in codes


async def test_rate_limit_custom_exempt_paths() -> None:
    """豁免路径清单可配：自定义豁免前缀不再触发 429。"""
    from fastapi import FastAPI
    from xagent.api.security_middleware import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=3,
        window_seconds=60,
        exempt_paths=["/health", "/api/v1/auth/oidc"],
    )

    @app.get("/api/v1/auth/oidc/providers")
    async def _oidc():
        return {"enabled": False}

    @app.get("/api/test")
    async def _t():
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # 豁免端点：超过阈值也不 429
        for _ in range(10):
            assert (await c.get("/api/v1/auth/oidc/providers")).status_code == 200
        # 非豁免端点：仍受限
        codes = [(await c.get("/api/test")).status_code for _ in range(5)]
    assert 429 in codes


async def test_rate_limit_default_exempt_unchanged() -> None:
    """不传 exempt_paths 时默认豁免 /health /ready /metrics（与历史行为一致）。"""
    from xagent.api.security_middleware import RateLimitMiddleware

    assert RateLimitMiddleware.DEFAULT_EXEMPT == ("/health", "/ready", "/metrics")


async def test_rate_limit_env_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """XAGENT_SECURITY__RATE_LIMIT_REQUESTS 驱动全局限流阈值。"""
    monkeypatch.setenv("XAGENT_SECURITY__RATE_LIMIT_REQUESTS", "3")
    from xagent.infra.settings import get_settings

    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        codes = [
            (await c.get("/api/v1/auth/oidc/providers")).status_code for _ in range(6)
        ]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:]


async def test_rate_limit_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """XAGENT_SECURITY__RATE_LIMIT_ENABLED=false 整体关闭限流（压测/内网）。"""
    monkeypatch.setenv("XAGENT_SECURITY__RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("XAGENT_SECURITY__RATE_LIMIT_REQUESTS", "1")
    from xagent.infra.settings import get_settings

    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        for _ in range(10):
            assert (await c.get("/api/v1/auth/oidc/providers")).status_code == 200


def test_rate_limit_settings_defaults() -> None:
    """默认配置与历史硬编码行为一致：300 req / 60s / IP。"""
    from xagent.infra.settings import Settings

    s = Settings()
    assert s.security.rate_limit_enabled is True
    assert s.security.rate_limit_requests == 300
    assert s.security.rate_limit_window_seconds == 60
    assert s.security.rate_limit_exempt_paths == ["/health", "/ready", "/metrics"]
