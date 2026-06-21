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
