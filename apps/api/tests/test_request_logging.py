from __future__ import annotations

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware
from xagent.api import middleware


class _RecordingLogger:
    def __init__(self) -> None:
        self.debug_calls: list[tuple[str, dict[str, object]]] = []
        self.info_calls: list[tuple[str, dict[str, object]]] = []

    def debug(self, event: str, **kwargs: object) -> None:
        self.debug_calls.append((event, kwargs))

    def info(self, event: str, **kwargs: object) -> None:
        self.info_calls.append((event, kwargs))

    def exception(self, event: str, **kwargs: object) -> None:
        pass


async def test_successful_request_logging_is_debug_only(monkeypatch) -> None:
    recording_logger = _RecordingLogger()
    monkeypatch.setattr(middleware, "logger", recording_logger)

    app = FastAPI()
    app.add_middleware(middleware.RequestContextMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/ok")

    assert response.status_code == 200
    assert recording_logger.info_calls == []
    assert len(recording_logger.debug_calls) == 1
    event, fields = recording_logger.debug_calls[0]
    assert event == "request"
    assert fields["method"] == "GET"
    assert fields["path"] == "/ok"
    assert fields["status"] == 200


async def test_request_context_preserves_headers_and_request_state() -> None:
    app = FastAPI()
    app.add_middleware(middleware.RequestContextMiddleware)

    @app.get("/context")
    async def context(request: Request) -> dict[str, str]:
        return {
            "request_id": request.state.request_id,
            "tenant_id": request.state.tenant_id,
        }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/context",
            headers={"x-request-id": "req-123", "x-tenant-id": "tenant-456"},
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"
    assert response.json() == {
        "request_id": "req-123",
        "tenant_id": "tenant-456",
    }


def test_request_context_uses_native_asgi_middleware() -> None:
    assert not issubclass(middleware.RequestContextMiddleware, BaseHTTPMiddleware)
