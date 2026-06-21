"""多模型媒体生成测试：provider 路由 + Null 降级 + 模式区分 + API。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.domains.creative_studio.media import (
    GenerationMode,
    GenerationRequest,
    MediaKind,
    get_media_registry,
)
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_null_image_text_to_image() -> None:
    reg = get_media_registry()
    task = await reg.generate(
        GenerationRequest(kind=MediaKind.image, prompt="夕阳海滩",
                          mode=GenerationMode.text_to_image),
        wait=False,
    )
    assert task.status == "succeeded"
    assert task.outputs
    assert "text_to_image" in task.outputs[0]


async def test_null_image_to_image() -> None:
    reg = get_media_registry()
    task = await reg.generate(
        GenerationRequest(kind=MediaKind.image, prompt="加滤镜",
                          mode=GenerationMode.image_to_image,
                          reference_images=["ref.png"]),
        wait=False,
    )
    assert task.status == "succeeded"
    assert "image_to_image" in task.outputs[0]


async def test_null_video() -> None:
    reg = get_media_registry()
    task = await reg.generate(
        GenerationRequest(kind=MediaKind.video, prompt="奔跑的猫",
                          mode=GenerationMode.text_to_video),
        wait=False,
    )
    assert task.status == "succeeded"
    assert "text_to_video" in task.outputs[0]


def test_list_models_includes_null() -> None:
    reg = get_media_registry()
    image_models = reg.list_models(MediaKind.image)
    video_models = reg.list_models(MediaKind.video)
    assert any(m.kind == MediaKind.image for m in image_models)
    assert any(m.kind == MediaKind.video for m in video_models)


async def test_media_models_api(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.get("/api/v1/creative-studio/media/models", headers=_h(token))
    assert resp.status_code == 200
    models = resp.json()["models"]
    assert models
    # 应含图像+视频
    kinds = {m["kind"] for m in models}
    assert "image" in kinds and "video" in kinds


async def test_media_generate_api(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.post(
        "/api/v1/creative-studio/media/generate",
        json={"kind": "image", "prompt": "霸总办公室", "mode": "text_to_image"},
        headers=_h(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["outputs"]


async def test_media_generate_viewer_forbidden(client: AsyncClient) -> None:
    token = create_access_token(user_id="v", tenant_id="t1", roles=["viewer"])
    resp = await client.post(
        "/api/v1/creative-studio/media/generate",
        json={"kind": "image", "prompt": "x"},
        headers=_h(token),
    )
    assert resp.status_code == 403


def test_image_provider_models() -> None:
    from xagent.domains.creative_studio.media.image_providers import OpenAIImageProvider

    p = OpenAIImageProvider(api_key="test")
    models = p.list_models(MediaKind.image)
    ids = {m.model_id for m in models}
    assert "gpt-image-2" in ids
    assert "dall-e-3" in ids


def test_video_provider_models() -> None:
    from xagent.domains.creative_studio.media.video_providers import (
        JimengProvider,
        KlingProvider,
    )

    kling_models = KlingProvider().list_models(MediaKind.video)
    jimeng_models = JimengProvider().list_models(MediaKind.video)
    assert any(m.model_id == "kling-v1" for m in kling_models)
    assert any(m.model_id == "jimeng-video-1" for m in jimeng_models)
