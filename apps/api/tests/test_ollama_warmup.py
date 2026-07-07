from __future__ import annotations

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
async def test_warmup_ollama_model_posts_minimal_chat(monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr("xagent.scripts.ollama_warmup.httpx.AsyncClient", lambda **_: _FakeAsyncClient())
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

    monkeypatch.setattr("xagent.scripts.ollama_warmup.httpx.AsyncClient", lambda **_: _BoomClient())
    cfg = LLMSettings(ollama_base_url="http://host.docker.internal:11434", warmup_enabled=True)
    result = await warmup_ollama_model(cfg)
    assert result.ok is False
    assert result.skipped is False
    assert "ollama unreachable" in result.detail
