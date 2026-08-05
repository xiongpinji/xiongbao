"""角色/场景一致性参考图注入测试（mock 图像 provider，离线可跑）。"""

from __future__ import annotations

import json

from xagent.domains.creative_studio.consistency import (
    ConsistencyManager,
    build_prompt_modifier,
    generate_keyframe_image,
)
from xagent.domains.creative_studio.media.base import (
    GenerationMode,
    GenerationRequest,
    GenerationTask,
    MediaKind,
)
from xagent.domains.creative_studio.media.registry import MediaProviderRegistry
from xagent.domains.creative_studio.producer import (
    _fill_continuity_refs,
    generate_storyboard,
)
from xagent.domains.creative_studio.storyboard import (
    CharacterCard,
    SceneCard,
    Shot,
    ShotContinuity,
    Storyboard,
)


class _MockImageProvider:
    """记录请求的 mock 图像 provider。"""

    name = "mock_image"
    supported_kinds = {MediaKind.image}
    supported_modes = set(GenerationMode)

    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    async def submit(self, req: GenerationRequest) -> GenerationTask:
        self.requests.append(req)
        n = len(self.requests)
        return GenerationTask(
            task_id=f"mock-{n}",
            provider=self.name,
            status="succeeded",
            outputs=[f"mock://img/{n}"],
        )

    async def poll(self, task_id: str) -> GenerationTask:
        return GenerationTask(
            task_id=task_id, provider=self.name, status="succeeded",
            outputs=[f"mock://img/{task_id}"],
        )

    def list_models(self, kind: MediaKind | None = None) -> list:
        return []


def _storyboard() -> Storyboard:
    return Storyboard(
        title="t",
        brief="b",
        genre="逆袭",
        characters=[
            CharacterCard(
                character_id="char-a", name="小花", role="逆袭女主",
                appearance="黑色长发，白裙",
            ),
            CharacterCard(
                character_id="char-b", name="顾总", role="霸总",
                appearance="西装，背头",
            ),
        ],
        scenes=[
            SceneCard(
                scene_id="scene-1", location="夜总会", time_of_day="夜晚",
                description="霓虹灯",
            ),
        ],
        shots=[
            Shot(
                shot_id="s1", scene="夜总会", characters=["小花", "顾总"],
                plot_purpose="冲突", dialogue="你走吧",
                continuity=ShotContinuity(
                    character_ref="char-a;char-b", scene_ref="scene-1",
                    style_ref="逆袭",
                ),
            ),
        ],
    )


def _manager(tmp_path, provider: _MockImageProvider) -> ConsistencyManager:
    return ConsistencyManager(
        tenant_id="t1", provider=provider, cache_dir=tmp_path / "consistency"
    )


async def test_base_image_cached_and_reused(tmp_path) -> None:
    provider = _MockImageProvider()
    sb = _storyboard()
    m1 = _manager(tmp_path, provider)

    url1 = await m1.ensure_base_image("character", sb.characters[0])
    url2 = await m1.ensure_base_image("character", sb.characters[0])
    assert url1 and url1 == url2
    assert len(provider.requests) == 1  # 第二次命中缓存，不再生成

    # 索引持久化到租户目录，新实例直接复用
    index_path = tmp_path / "consistency" / "index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert any(v == url1 for v in index.values())

    m2 = _manager(tmp_path, provider)
    url3 = await m2.ensure_base_image("character", sb.characters[0])
    assert url3 == url1
    assert len(provider.requests) == 1

    # 卡片内容变化 → 指纹变 → 重新生成
    changed = sb.characters[0].model_copy(update={"appearance": "红色短发"})
    url4 = await m2.ensure_base_image("character", changed)
    assert url4 != url1
    assert len(provider.requests) == 2


async def test_base_image_failure_degrades(tmp_path) -> None:
    class _FailProvider(_MockImageProvider):
        async def submit(self, req: GenerationRequest) -> GenerationTask:
            return GenerationTask(
                task_id="mock-err", provider=self.name,
                status="failed", error="boom",
            )

    m = _manager(tmp_path, _FailProvider())
    url = await m.ensure_base_image("character", _storyboard().characters[0])
    assert url == ""


def test_prompt_modifier_backward_compatible() -> None:
    assert build_prompt_modifier([], None) == ""
    sb = _storyboard()
    modifier = build_prompt_modifier(sb.characters, sb.scenes[0], "逆袭")
    assert "小花（逆袭女主，黑色长发，白裙）" in modifier
    assert "顾总（霸总，西装，背头）" in modifier
    assert "场景一致性：夜总会（夜晚，霓虹灯）" in modifier
    assert "逆袭题材" in modifier


async def test_apply_to_shot_injects_references_and_modifier(tmp_path) -> None:
    provider = _MockImageProvider()
    sb = _storyboard()
    shot = sb.shots[0]
    m = _manager(tmp_path, provider)

    result = await m.apply_to_shot(sb, shot)
    # 2 角色 + 1 场景 = 3 张基准参考图
    assert len(result.reference_images) == 3
    assert len(provider.requests) == 3
    assert "黑色长发" in result.prompt_modifier
    # 贯穿记录：写回 ShotContinuity
    assert shot.continuity.reference_images == result.reference_images
    assert shot.continuity.prompt_modifier == result.prompt_modifier

    # 第二个镜头引用同一角色 → 基准图缓存复用，不重复生成
    shot2 = Shot(shot_id="s2", scene="夜总会", characters=["小花"])
    result2 = await m.apply_to_shot(sb, shot2)
    assert len(result2.reference_images) == 2  # 小花 + 夜总会
    assert len(provider.requests) == 3  # 未新增生成


async def test_resolve_shot_falls_back_to_names(tmp_path) -> None:
    provider = _MockImageProvider()
    sb = _storyboard()
    shot = Shot(scene="夜总会", characters=["小花"])  # 无 continuity 引用
    m = _manager(tmp_path, provider)
    characters, scene = m.resolve_shot(sb, shot)
    assert [c.character_id for c in characters] == ["char-a"]
    assert scene is not None and scene.scene_id == "scene-1"


async def test_generate_keyframe_injects_reference_images(tmp_path) -> None:
    provider = _MockImageProvider()
    registry = MediaProviderRegistry()
    registry.register(MediaKind.image, provider)
    sb = _storyboard()
    m = _manager(tmp_path, provider)

    task = await generate_keyframe_image(
        sb, sb.shots[0], prompt="夜总会对峙",
        manager=m, registry=registry,
    )
    assert task.status == "succeeded"
    keyframe_req = provider.requests[-1]
    assert keyframe_req.mode == GenerationMode.image_to_image
    assert len(keyframe_req.reference_images) == 3
    # prompt 组装：基础 prompt + 一致性修饰词
    assert keyframe_req.prompt.startswith("夜总会对峙")
    assert "角色一致性" in keyframe_req.prompt


async def test_generate_keyframe_without_cards_backward_compatible(tmp_path) -> None:
    provider = _MockImageProvider()
    registry = MediaProviderRegistry()
    registry.register(MediaKind.image, provider)
    sb = Storyboard(  # 无角色卡/场景卡
        title="t", brief="b",
        shots=[Shot(shot_id="s1", scene="街上", characters=["路人"])],
    )
    m = _manager(tmp_path, provider)

    task = await generate_keyframe_image(
        sb, sb.shots[0], prompt="街头画面",
        manager=m, registry=registry,
    )
    assert task.status == "succeeded"
    assert len(provider.requests) == 1  # 只有关键帧，无基准图生成
    req = provider.requests[0]
    assert req.mode == GenerationMode.text_to_image
    assert req.reference_images == []
    assert req.prompt == "街头画面"  # prompt 原样，行为与现状一致


async def test_producer_fallback_records_continuity_refs() -> None:
    class _FailLLM:
        async def complete(self, messages, **kwargs):
            raise RuntimeError("llm down")

    sb = await generate_storyboard("测试 brief", llm=_FailLLM())
    assert sb.shots
    for shot in sb.shots:
        assert shot.continuity.character_ref == sb.characters[0].character_id
        assert shot.continuity.scene_ref == sb.scenes[0].scene_id
        assert shot.continuity.style_ref == sb.genre


async def test_producer_llm_path_records_continuity_refs() -> None:
    from xagent.adapters.llm import Message  # noqa: F401  类型参照

    class _StubLLM:
        async def complete(self, messages, **kwargs):
            class _Resp:
                content = json.dumps(
                    {
                        "title": "t",
                        "characters": [
                            {"name": "小花", "role": "女主", "appearance": "长发"},
                        ],
                        "scenes": [{"location": "夜总会", "time_of_day": "夜晚"}],
                        "shots": [
                            {
                                "duration_seconds": 4, "scene": "夜总会",
                                "characters": ["小花"], "plot_purpose": "冲突",
                                "dialogue": "走", "action": "转身", "subtitle": "走",
                            },
                        ],
                    },
                    ensure_ascii=False,
                )

            return _Resp()

    sb = await generate_storyboard("测试 brief", llm=_StubLLM())
    shot = sb.shots[0]
    assert shot.continuity.character_ref == sb.characters[0].character_id
    assert shot.continuity.scene_ref == sb.scenes[0].scene_id
    assert shot.continuity.style_ref == "逆袭"


def test_fill_continuity_refs_does_not_override_existing() -> None:
    sb = _storyboard()
    shot = sb.shots[0]
    shot.continuity.character_ref = "manual-ref"
    _fill_continuity_refs(sb)
    assert shot.continuity.character_ref == "manual-ref"
