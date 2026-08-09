"""provider payload 拼接 + model 透传 Mock 测试（不真发请求）。

覆盖:
- VolcanoArkVideoProvider._build_parameters 正确挑字段
- VolcanoArkVideoProvider.submit payload 含 model/parameters
- OpenAIImageProvider._build_payload 含 n/quality/seed
- OpenAIImageProvider._endpoint 拼接（中转站 base_url 末尾斜杠）
- litellm_client.effective_model deepseek 前缀路由
"""

from __future__ import annotations

from unittest.mock import patch

from xagent.adapters.llm.base import Message
from xagent.adapters.llm.litellm_client import LiteLLMClient
from xagent.domains.creative_studio.media import (
    GenerationMode,
    GenerationRequest,
    MediaKind,
)
from xagent.domains.creative_studio.media.image_providers import OpenAIImageProvider
from xagent.domains.creative_studio.media.video_providers import VolcanoArkVideoProvider
from xagent.infra.settings import LLMSettings

# ---------------------------------------------------------------------------
# VolcanoArkVideoProvider
# ---------------------------------------------------------------------------


def test_volcano_ark_default_model_is_seedance_2() -> None:
    p = VolcanoArkVideoProvider(api_key="fake")
    assert p.default_model == "doubao-seedance-2-0-260128"


def test_volcano_ark_build_parameters_picks_supported_fields() -> None:
    p = VolcanoArkVideoProvider(api_key="fake")
    req = GenerationRequest(
        kind=MediaKind.video,
        prompt="测试",
        mode=GenerationMode.text_to_video,
        resolution="1080p",
        duration_seconds=5,
        seed=42,
        params={"sampler": "euler", "shotType": "近景", "ignored": "x"},
    )
    params = p._build_parameters(req)
    assert params["resolution"] == "1080p"
    assert params["duration"] == 5
    assert params["seed"] == 42
    assert params["camera"] == {"type": "近景"}
    # 不支持的字段被过滤掉
    assert "sampler" not in params
    assert "ignored" not in params


async def test_volcano_ark_submit_payload_contains_model_and_parameters() -> None:
    p = VolcanoArkVideoProvider(api_key="fake", default_model="doubao-seedance-2-0-260128")
    req = GenerationRequest(
        kind=MediaKind.video,
        prompt="测试视频",
        mode=GenerationMode.text_to_video,
        resolution="720p",
        duration_seconds=5,
    )
    captured: dict = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"id": "task-123", "status": "queued"}

    class FakeClient:
        def __init__(self, *a, **kw) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["payload"] = json
            captured["headers"] = headers
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        task = await p.submit(req)

    assert task.task_id == "task-123"
    assert task.status == "queued"
    assert captured["payload"]["model"] == "doubao-seedance-2-0-260128"
    assert captured["payload"]["content"][0]["text"] == "测试视频"
    assert captured["payload"]["parameters"]["resolution"] == "720p"
    assert captured["payload"]["parameters"]["duration"] == 5
    assert captured["headers"]["Authorization"] == "Bearer fake"


async def test_volcano_ark_submit_model_override_from_request() -> None:
    """节点 settings.model 透传到 req.model_id 时应覆盖默认。"""
    p = VolcanoArkVideoProvider(api_key="fake")
    req = GenerationRequest(
        kind=MediaKind.video,
        prompt="x",
        mode=GenerationMode.text_to_video,
        model_id="doubao-seedance-1-5-pro-251215",
    )
    captured: dict = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "t1"}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json=None, headers=None):
            captured["payload"] = json
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        await p.submit(req)

    assert captured["payload"]["model"] == "doubao-seedance-1-5-pro-251215"


# ---------------------------------------------------------------------------
# OpenAIImageProvider
# ---------------------------------------------------------------------------


def test_openai_image_endpoint_strips_trailing_slash() -> None:
    """中转站 base_url 末尾带斜杠时不应产生双斜杠。"""
    p = OpenAIImageProvider(api_key="fake", base_url="https://yunqiaoapi.com/v1/")
    assert p._endpoint("/images/generations") == "https://yunqiaoapi.com/v1/images/generations"
    assert p._endpoint("images/generations") == "https://yunqiaoapi.com/v1/images/generations"


def test_openai_image_build_payload_picks_n_quality_seed() -> None:
    p = OpenAIImageProvider(api_key="fake")
    req = GenerationRequest(
        kind=MediaKind.image,
        prompt="测试图",
        mode=GenerationMode.text_to_image,
        resolution="1024x1024",
        seed=99,
        params={"batch": 3, "quality": "high", "sampler": "euler", "ignored": "x"},
    )
    payload = p._build_payload(req, size="1024x1024")
    assert payload["model"] == "gpt-image-2"
    assert payload["prompt"] == "测试图"
    assert payload["size"] == "1024x1024"
    assert payload["n"] == 3
    assert payload["quality"] == "high"
    assert payload["seed"] == 99
    # 不支持的字段被过滤
    assert "sampler" not in payload
    assert "ignored" not in payload


async def test_openai_image_submit_uses_endpoint_and_returns_outputs() -> None:
    p = OpenAIImageProvider(api_key="fake", base_url="https://yunqiaoapi.com/v1/")
    req = GenerationRequest(
        kind=MediaKind.image,
        prompt="cyber cat",
        mode=GenerationMode.text_to_image,
        resolution="1024x1024",
    )
    captured: dict = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"url": "https://cdn.test/img.png"}]}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["payload"] = json
            return FakeResp()

    with patch("httpx.AsyncClient", FakeClient):
        task = await p.submit(req)

    assert task.status == "succeeded"
    assert task.outputs == ["https://cdn.test/img.png"]
    assert captured["url"] == "https://yunqiaoapi.com/v1/images/generations"
    assert captured["payload"]["model"] == "gpt-image-2"


# ---------------------------------------------------------------------------
# LiteLLMClient deepseek 路由
# ---------------------------------------------------------------------------


def test_litellm_effective_model_adds_deepseek_prefix() -> None:
    cfg = LLMSettings(default_model="deepseek-v4-flash", deepseek_api_key="sk-fake")
    client = LiteLLMClient(cfg)
    assert client.effective_model == "deepseek/deepseek-v4-flash"


def test_litellm_effective_model_prefers_proxy_default_over_ollama_prefix() -> None:
    cfg = LLMSettings(
        default_model="proxy-default",
        proxy_url="http://localhost:4000",
        ollama_base_url="http://host.docker.internal:11434",
        ollama_model="qwen3:4b",
    )
    client = LiteLLMClient(cfg)
    assert client.effective_model == "proxy-default"


def test_litellm_call_kwargs_uses_request_timeout_seconds() -> None:
    cfg = LLMSettings(
        ollama_base_url="http://host.docker.internal:11434",
        ollama_model="qwen2.5vl:7b",
        request_timeout_seconds=150,
    )
    client = LiteLLMClient(cfg)

    kwargs = client._call_kwargs()

    assert kwargs["timeout"] == 150
    assert kwargs["api_base"] == "http://host.docker.internal:11434"
    assert kwargs["model"] == "ollama/qwen2.5vl:7b"


def test_litellm_call_kwargs_deepseek_key_transmitted() -> None:
    cfg = LLMSettings(default_model="deepseek-v4-flash", deepseek_api_key="sk-fake")
    client = LiteLLMClient(cfg)
    kwargs = client._call_kwargs()
    assert kwargs["api_key"] == "sk-fake"
    assert kwargs["model"].startswith("deepseek/")


async def test_litellm_health_true_with_deepseek_key() -> None:
    cfg = LLMSettings(deepseek_api_key="sk-fake")
    client = LiteLLMClient(cfg)
    assert await client.health() is True


async def test_litellm_health_false_without_any_key() -> None:
    cfg = LLMSettings()
    client = LiteLLMClient(cfg)
    assert await client.health() is False


async def test_litellm_complete_with_tools_transmits_named_tool_choice(
    monkeypatch,
) -> None:
    captured: dict = {}

    async def _fake_acompletion(*, messages, **kwargs):
        captured.update(kwargs)
        return {
            "choices": [{"message": {"content": "", "tool_calls": []}}],
            "usage": {},
        }

    monkeypatch.setattr("litellm.acompletion", _fake_acompletion)
    client = LiteLLMClient(
        LLMSettings(
            ollama_base_url="http://localhost:11434",
            ollama_model="qwen3:4b",
        )
    )
    required_choice = {
        "type": "function",
        "function": {"name": "file_write"},
    }

    await client.complete_with_tools(
        [Message(role="user", content="create a file")],
        [{"type": "function", "function": {"name": "file_write"}}],
        tool_choice=required_choice,
    )

    assert captured["tool_choice"] == required_choice


async def test_litellm_stream_with_tools_transmits_named_choice_and_defaults_auto(
    monkeypatch,
) -> None:
    captured: list[dict] = []

    class _FakeStream:
        def __init__(self) -> None:
            self._done = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._done:
                raise StopAsyncIteration
            self._done = True
            return {
                "choices": [
                    {"delta": {"content": "ok"}, "finish_reason": "stop"}
                ]
            }

    async def _fake_acompletion(*, messages, **kwargs):  # noqa: ARG001
        captured.append(kwargs)
        return _FakeStream()

    monkeypatch.setattr("litellm.acompletion", _fake_acompletion)
    client = LiteLLMClient(
        LLMSettings(
            ollama_base_url="http://localhost:11434",
            ollama_model="qwen3:4b",
        )
    )
    messages = [Message(role="user", content="create a file")]
    tools = [{"type": "function", "function": {"name": "file_write"}}]
    required_choice = {
        "type": "function",
        "function": {"name": "file_write"},
    }

    _ = [
        chunk
        async for chunk in client.stream_with_tools(
            messages, tools, tool_choice=required_choice
        )
    ]
    _ = [chunk async for chunk in client.stream_with_tools(messages, tools)]

    assert captured[0]["tool_choice"] == required_choice
    assert captured[1]["tool_choice"] == "auto"
