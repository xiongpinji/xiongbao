"""Deep health dependency probes."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from xagent.api import health


class _FakeRedis:
    def __init__(self, ping_result: object = True) -> None:
        self.ping_result = ping_result
        self.ping_started = asyncio.Event()
        self.closed = False

    async def ping(self) -> object:
        self.ping_started.set()
        if isinstance(self.ping_result, BaseException):
            raise self.ping_result
        if self.ping_result is _BLOCK:
            await asyncio.Event().wait()
        return self.ping_result

    async def aclose(self) -> None:
        self.closed = True


_BLOCK = object()


def _install_fake_redis(
    monkeypatch: pytest.MonkeyPatch,
    fake: _FakeRedis,
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def _from_url(url: str, **kwargs: object) -> _FakeRedis:
        captured.update(url=url, **kwargs)
        return fake

    monkeypatch.setattr(
        health,
        "get_settings",
        lambda: SimpleNamespace(cache=SimpleNamespace(redis_url="redis://redis:6379/0")),
    )
    monkeypatch.setattr("redis.asyncio.from_url", _from_url)
    monkeypatch.setattr(health, "_REDIS_CONNECT_TIMEOUT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(health, "_REDIS_PING_TIMEOUT_SECONDS", 0.01, raising=False)
    return captured


async def test_check_redis_times_out_blocking_ping_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis(_BLOCK)
    captured = _install_fake_redis(monkeypatch, fake)

    result = await asyncio.wait_for(health._check_redis(), timeout=0.2)

    assert result["status"] == "degraded"
    assert result["fallback"] == "skip_cache"
    assert fake.closed is True
    assert captured == {
        "url": "redis://redis:6379/0",
        "socket_connect_timeout": 0.01,
        "socket_timeout": 0.01,
    }


async def test_check_redis_success_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis(True)
    captured = _install_fake_redis(monkeypatch, fake)

    result = await health._check_redis()

    assert result["status"] == "healthy"
    assert fake.closed is True
    assert captured["socket_connect_timeout"] == 0.01
    assert captured["socket_timeout"] == 0.01


async def test_check_redis_failure_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis(ConnectionError("redis unavailable"))
    _install_fake_redis(monkeypatch, fake)

    result = await health._check_redis()

    assert result["status"] == "degraded"
    assert result["fallback"] == "skip_cache"
    assert fake.closed is True


async def test_check_redis_cancellation_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis(_BLOCK)
    _install_fake_redis(monkeypatch, fake)
    monkeypatch.setattr(health, "_REDIS_PING_TIMEOUT_SECONDS", 10)

    task = asyncio.create_task(health._check_redis())
    await fake.ping_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.closed is True


async def test_deep_health_keeps_degraded_http_200_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _healthy() -> dict[str, object]:
        return {"status": "healthy", "latency_ms": 1}

    async def _degraded_redis() -> dict[str, object]:
        return {"status": "degraded", "fallback": "skip_cache"}

    monkeypatch.setattr(health, "_check_db", _healthy)
    monkeypatch.setattr(health, "_check_redis", _degraded_redis)
    monkeypatch.setattr(health, "_check_qdrant", _healthy)

    response = await health.deep_health()
    body = json.loads(response.body)

    assert response.status_code == 200
    assert body["status"] == "degraded"
    assert body["degraded_services"] == ["redis"]
    assert body["checks"]["database"]["status"] == "healthy"
    assert body["checks"]["redis"] == {
        "status": "degraded",
        "fallback": "skip_cache",
    }
    assert body["checks"]["qdrant"]["status"] == "healthy"
