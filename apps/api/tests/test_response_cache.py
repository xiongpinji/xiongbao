"""Response cache contracts for endpoints that must stay live."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.responses import Response
from xagent.api.response_cache import CacheEntry, ResponseCacheMiddleware


async def test_metrics_bypasses_cache_and_preserves_origin_response() -> None:
    calls = 0
    metrics_body = b"# TYPE xagent_probe_total counter\nxagent_probe_total 2\n"

    async def app(scope, receive, send) -> None:
        nonlocal calls
        calls += 1
        response = Response(
            content=metrics_body,
            status_code=200,
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )
        await response(scope, receive, send)

    middleware = ResponseCacheMiddleware(app)
    middleware._cache["/metrics?"] = CacheEntry(
        body=b"stale",
        etag='"stale-etag"',
        content_type="application/json",
        status_code=200,
    )
    cache_before = dict(middleware._cache)
    transport = ASGITransport(app=middleware)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/metrics", headers={"If-None-Match": '"stale-etag"'})
        second = await client.get("/metrics", headers={"If-None-Match": '"stale-etag"'})

    assert calls == 2
    assert middleware._cache == cache_before
    for response in (first, second):
        assert response.status_code == 200
        assert response.content == metrics_body
        assert response.headers["content-type"] == CONTENT_TYPE_LATEST
        assert "etag" not in response.headers
        assert "x-cache" not in response.headers


async def test_anonymous_get_with_metrics_prefix_still_uses_cache() -> None:
    calls = 0

    async def app(scope, receive, send) -> None:
        nonlocal calls
        calls += 1
        response = Response(content=f"response-{calls}", media_type="text/plain")
        await response(scope, receive, send)

    middleware = ResponseCacheMiddleware(app)
    transport = ASGITransport(app=middleware)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/metrics/details")
        second = await client.get("/metrics/details")

    assert calls == 1
    assert first.text == second.text == "response-1"
    assert first.headers["x-cache"] == "MISS"
    assert second.headers["x-cache"] == "HIT"
    assert first.headers["etag"] == second.headers["etag"]
