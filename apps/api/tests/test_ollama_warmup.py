from __future__ import annotations

import itertools
import sys
import types

import pytest
from xagent.infra.settings import LLMSettings
from xagent.scripts.ollama_warmup import WarmupResult, warmup_ollama_model


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {
            "message": {"content": "好。"},
            "done": True,
        }

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


@pytest.mark.asyncio
async def test_warmup_ollama_model_posts_minimal_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict = {}

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            seen["tags_url"] = url
            return _FakeResponse(payload={"models": [{"name": "qwen2.5vl:7b"}]})

        async def post(self, url: str, json: dict):
            seen["chat_url"] = url
            seen["payload"] = json
            return _FakeResponse()

    monkeypatch.setattr(
        "xagent.scripts.ollama_warmup.httpx.AsyncClient",
        lambda **_: _FakeAsyncClient(),
    )
    cfg = LLMSettings(
        ollama_base_url="http://host.docker.internal:11434",
        ollama_model="qwen2.5vl:7b",
        warmup_enabled=True,
        warmup_prompt="回复一个字：好",
        warmup_max_tokens=8,
    )

    result = await warmup_ollama_model(cfg)

    assert result == WarmupResult(ok=True, skipped=False, detail="ok")
    assert seen["tags_url"].endswith("/api/tags")
    assert seen["chat_url"].endswith("/api/chat")
    assert seen["payload"] == {
        "model": "qwen2.5vl:7b",
        "messages": [{"role": "user", "content": "回复一个字：好"}],
        "stream": False,
        "options": {"num_predict": 8},
    }


@pytest.mark.asyncio
async def test_warmup_ollama_model_prefers_proxy_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict = {}

    async def _fake_complete(
        self,
        messages,
        *,
        model=None,
        temperature=0.7,
        max_tokens=None,
        **kwargs,
    ):
        seen["messages"] = messages
        seen["model"] = model
        seen["temperature"] = temperature
        seen["max_tokens"] = max_tokens
        seen["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("xagent.scripts.ollama_warmup.LiteLLMClient.complete", _fake_complete)
    cfg = LLMSettings(
        proxy_url="http://localhost:4000",
        proxy_api_key="sk-proxy",
        default_model="qwen3:4b",
        warmup_enabled=True,
        warmup_prompt="回复一个字：好",
        warmup_max_tokens=8,
    )

    result = await warmup_ollama_model(cfg)

    assert result == WarmupResult(ok=True, skipped=False, detail="ok")
    assert [message.role for message in seen["messages"]] == ["user"]
    assert [message.content for message in seen["messages"]] == ["回复一个字：好"]
    assert seen["model"] is None
    assert seen["temperature"] == 0
    assert seen["max_tokens"] == 8
    assert set(seen["kwargs"]) == {"timeout"}
    assert 29 < seen["kwargs"]["timeout"] <= 30


@pytest.mark.asyncio
async def test_warmup_ollama_model_uses_proxy_model_even_when_ollama_base_url_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict = {}

    async def _fake_acompletion(*, messages, **kwargs):
        seen["messages"] = messages
        seen["kwargs"] = kwargs
        return {
            "choices": [{"message": {"content": "好", "tool_calls": []}}],
            "usage": {},
        }

    monkeypatch.setitem(
        sys.modules,
        "litellm",
        types.SimpleNamespace(acompletion=_fake_acompletion),
    )
    cfg = LLMSettings(
        proxy_url="http://localhost:4000",
        proxy_api_key="sk-proxy",
        default_model="proxy-default",
        ollama_base_url="http://host.docker.internal:11434",
        ollama_model="qwen3:4b",
        warmup_enabled=True,
        warmup_prompt="回复一个字：好",
        warmup_max_tokens=8,
    )

    result = await warmup_ollama_model(cfg)

    assert result == WarmupResult(ok=True, skipped=False, detail="ok")
    assert seen["kwargs"]["model"] == "proxy-default"
    assert seen["kwargs"]["api_base"] == "http://localhost:4000"
    assert seen["kwargs"]["api_key"] == "sk-proxy"
    assert seen["kwargs"]["max_tokens"] == 8
    assert seen["kwargs"]["temperature"] == 0


@pytest.mark.asyncio
async def test_warmup_ollama_model_normalizes_ollama_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict = {}

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            seen["tags_url"] = url
            return _FakeResponse(payload={"models": [{"name": "qwen3:4b"}]})

        async def post(self, url: str, json: dict):
            seen["chat_url"] = url
            seen["payload"] = json
            return _FakeResponse()

    monkeypatch.setattr(
        "xagent.scripts.ollama_warmup.httpx.AsyncClient",
        lambda **_: _FakeAsyncClient(),
    )
    cfg = LLMSettings(
        ollama_base_url="http://host.docker.internal:11434",
        default_model="ollama/qwen3:4b",
        warmup_enabled=True,
    )

    result = await warmup_ollama_model(cfg)

    assert result == WarmupResult(ok=True, skipped=False, detail="ok")
    assert seen["payload"]["model"] == "qwen3:4b"


@pytest.mark.asyncio
async def test_warmup_ollama_model_retries_within_wait_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []

    class _FlakyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("ollama unreachable")
            return _FakeResponse(payload={"models": [{"name": "qwen3:4b"}]})

        async def post(self, url: str, json: dict):
            return _FakeResponse()

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "xagent.scripts.ollama_warmup.httpx.AsyncClient",
        lambda **_: _FlakyClient(),
    )
    monkeypatch.setattr("xagent.scripts.ollama_warmup.asyncio.sleep", _fake_sleep)
    cfg = LLMSettings(
        ollama_base_url="http://host.docker.internal:11434",
        ollama_model="qwen3:4b",
        warmup_enabled=True,
        warmup_wait_timeout_seconds=5,
        warmup_poll_interval_seconds=0.25,
    )

    result = await warmup_ollama_model(cfg)

    assert result == WarmupResult(ok=True, skipped=False, detail="ok")
    assert attempts["count"] == 2
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_warmup_ollama_model_caps_attempt_timeout_to_remaining_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeouts: list[float] = []

    class _TimeoutAsyncClient:
        def __init__(self, *, timeout):
            timeouts.append(timeout.connect)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            raise RuntimeError("ollama still starting")

    monotonic_values = itertools.chain([100.0, 100.0, 103.0], itertools.repeat(103.0))

    async def _fake_sleep(seconds: float) -> None:
        raise AssertionError("sleep should not run after budget is exhausted")

    monkeypatch.setattr(
        "xagent.scripts.ollama_warmup.httpx.AsyncClient",
        lambda **kwargs: _TimeoutAsyncClient(**kwargs),
    )
    monkeypatch.setattr("xagent.scripts.ollama_warmup.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr(
        "xagent.scripts.ollama_warmup.time.monotonic",
        lambda: next(monotonic_values),
    )
    cfg = LLMSettings(
        ollama_base_url="http://host.docker.internal:11434",
        ollama_model="qwen3:4b",
        warmup_enabled=True,
        request_timeout_seconds=60,
        warmup_wait_timeout_seconds=3,
        warmup_poll_interval_seconds=1,
    )

    result = await warmup_ollama_model(cfg)

    assert result.ok is False
    assert result.skipped is False
    assert "ollama still starting" in result.detail
    assert timeouts == [3]


@pytest.mark.asyncio
async def test_warmup_ollama_model_skips_when_disabled() -> None:
    cfg = LLMSettings(warmup_enabled=False)
    result = await warmup_ollama_model(cfg)
    assert result == WarmupResult(ok=True, skipped=True, detail="warmup disabled")


@pytest.mark.asyncio
async def test_warmup_ollama_model_returns_failure_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BoomClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            raise RuntimeError("ollama unreachable")

    async def _fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(
        "xagent.scripts.ollama_warmup.httpx.AsyncClient",
        lambda **_: _BoomClient(),
    )
    monkeypatch.setattr("xagent.scripts.ollama_warmup.asyncio.sleep", _fake_sleep)
    cfg = LLMSettings(
        ollama_base_url="http://host.docker.internal:11434",
        warmup_enabled=True,
        warmup_wait_timeout_seconds=0,
    )
    result = await warmup_ollama_model(cfg)

    assert result.ok is False
    assert result.skipped is False
    assert "ollama unreachable" in result.detail


@pytest.mark.asyncio
async def test_warmup_ollama_model_zero_wait_budget_still_makes_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeouts: list[float] = []
    attempts = {"count": 0}
    sleeps: list[float] = []

    class _SingleAttemptClient:
        def __init__(self, *, timeout):
            timeouts.append(timeout.connect)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            attempts["count"] += 1
            raise RuntimeError("ollama unreachable")

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "xagent.scripts.ollama_warmup.httpx.AsyncClient",
        lambda **kwargs: _SingleAttemptClient(**kwargs),
    )
    monkeypatch.setattr("xagent.scripts.ollama_warmup.asyncio.sleep", _fake_sleep)
    cfg = LLMSettings(
        ollama_base_url="http://host.docker.internal:11434",
        ollama_model="qwen3:4b",
        warmup_enabled=True,
        request_timeout_seconds=60,
        warmup_wait_timeout_seconds=0,
        warmup_poll_interval_seconds=1,
    )

    result = await warmup_ollama_model(cfg)

    assert result.ok is False
    assert result.skipped is False
    assert "ollama unreachable" in result.detail
    assert attempts["count"] == 1
    assert timeouts == [60]
    assert sleeps == []
