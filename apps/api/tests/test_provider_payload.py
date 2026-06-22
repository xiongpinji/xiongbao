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


def test_litellm_effective_model_no_prefix_when_proxy() -> None:
    cfg = LLMSettings(
        default_model="deepseek-v4-flash",
        deepseek_api_key="sk-fake",
        proxy_url="http://localhost:4000",
    )
    client = LiteLLMClient(cfg)
    # 有 proxy 时不加 deepseek/ 前缀（由 proxy 路由）
    assert client.effective_model == "deepseek-v4-flash"


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
