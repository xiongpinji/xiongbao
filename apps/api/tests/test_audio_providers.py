"""配音 TTS 闭环测试：EdgeTTS provider（mock 网络层）+ 音色分配 + 管线配音步骤 + 音频混流。

edge-tts 真实调用需外网，本文件一律 mock edge_tts.Communicate / 阻断 import，
测试离线确定性运行。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from xagent.domains.creative_studio.media.audio_providers import (
    DEFAULT_VOICE,
    EdgeTTSProvider,
    VolcanoTTSProvider,
    edge_tts_available,
)
from xagent.domains.creative_studio.media.base import (
    GenerationMode,
    GenerationRequest,
    GenerationTask,
    MediaKind,
)


class _FakeCommunicate:
    """替代 edge_tts.Communicate 的假实现：不落网，直接写假 mp3 文件。"""

    instances: list[_FakeCommunicate] = []
    fail_with: Exception | None = None

    def __init__(self, text: str, voice: str, **kwargs) -> None:
        self.text = text
        self.voice = voice
        self.kwargs = kwargs
        _FakeCommunicate.instances.append(self)

    async def save(self, path: str) -> None:
        if _FakeCommunicate.fail_with is not None:
            raise _FakeCommunicate.fail_with
        Path(path).write_bytes(b"fake-mp3")


@pytest.fixture
def fake_communicate(monkeypatch: pytest.MonkeyPatch):
    # edge-tts 为可选 extra（tts），CI 默认环境未安装时跳过而非 ERROR；
    # 缺包降级路径由 test_edge_tts_not_installed_degrades 覆盖
    edge_tts = pytest.importorskip("edge_tts")

    _FakeCommunicate.instances = []
    _FakeCommunicate.fail_with = None
    monkeypatch.setattr(edge_tts, "Communicate", _FakeCommunicate)
    return _FakeCommunicate


def _req(text: str = "你好，短剧", **kw) -> GenerationRequest:
    return GenerationRequest(
        kind=MediaKind.audio, prompt=text, mode=GenerationMode.text_to_speech, **kw
    )


# ---- EdgeTTSProvider ----


async def test_edge_tts_submit_success(tmp_path, fake_communicate) -> None:
    p = EdgeTTSProvider(output_dir=str(tmp_path))
    task = await p.submit(_req())
    assert task.status == "succeeded"
    assert task.provider == "edge_tts"
    assert len(task.outputs) == 1
    out = Path(task.outputs[0])
    assert out.exists() and out.read_bytes() == b"fake-mp3"
    # 默认音色 + poll 缓存
    assert task.raw["voice"] == DEFAULT_VOICE
    polled = await p.poll(task.task_id)
    assert polled.status == "succeeded"
    assert polled.outputs == task.outputs


async def test_edge_tts_voice_resolution_and_params(tmp_path, fake_communicate) -> None:
    p = EdgeTTSProvider(output_dir=str(tmp_path))
    # params.voice 优先
    task = await p.submit(
        _req(params={"voice": "zh-CN-YunxiNeural", "rate": "+10%", "pitch": "-2Hz"})
    )
    assert task.status == "succeeded"
    inst = fake_communicate.instances[-1]
    assert inst.voice == "zh-CN-YunxiNeural"
    assert inst.kwargs == {"rate": "+10%", "pitch": "-2Hz"}
    # model_id 其次
    task2 = await p.submit(_req(model_id="zh-CN-YunjianNeural"))
    assert task2.status == "succeeded"
    assert fake_communicate.instances[-1].voice == "zh-CN-YunjianNeural"
    # 默认兜底
    await p.submit(_req())
    assert fake_communicate.instances[-1].voice == DEFAULT_VOICE


async def test_edge_tts_network_failure_degrades_gracefully(tmp_path, fake_communicate) -> None:
    """网络不可用：返回 failed 任务而不抛异常（单镜头降级语义）。"""
    fake_communicate.fail_with = ConnectionError("no network")
    p = EdgeTTSProvider(output_dir=str(tmp_path))
    task = await p.submit(_req())
    assert task.status == "failed"
    assert "no network" in (task.error or "")
    assert task.outputs == []


async def test_edge_tts_empty_text_fails(tmp_path, fake_communicate) -> None:
    p = EdgeTTSProvider(output_dir=str(tmp_path))
    task = await p.submit(_req("   "))
    assert task.status == "failed"
    assert task.error


async def test_edge_tts_not_installed_degrades(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未安装 edge-tts：submit 返回 failed（不抛），registry 侧则由 edge_tts_available 拦截。"""
    monkeypatch.setitem(sys.modules, "edge_tts", None)
    assert not edge_tts_available()
    p = EdgeTTSProvider(output_dir=str(tmp_path))
    task = await p.submit(_req())
    assert task.status == "failed"
    assert "edge-tts" in (task.error or "")


async def test_edge_tts_poll_unknown_task(tmp_path) -> None:
    p = EdgeTTSProvider(output_dir=str(tmp_path))
    task = await p.poll("no-such-task")
    assert task.status == "failed"


def test_edge_tts_list_models(tmp_path) -> None:
    p = EdgeTTSProvider(output_dir=str(tmp_path))
    models = p.list_models(MediaKind.audio)
    assert models
    assert all(m.kind == MediaKind.audio for m in models)
    assert all(GenerationMode.text_to_speech in m.modes for m in models)
    assert any(m.model_id == "zh-CN-XiaoxiaoNeural" for m in models)
    # 非音频 kind 过滤为空
    assert p.list_models(MediaKind.image) == []


# ---- VolcanoTTSProvider（扩展位骨架）----


async def test_volcano_tts_skeleton_not_implemented() -> None:
    p = VolcanoTTSProvider()
    assert p.supported_kinds == {MediaKind.audio}
    task = await p.submit(_req())
    assert task.status == "failed"
    assert "尚未接入" in (task.error or "")
    assert p.list_models(MediaKind.audio) == []


# ---- registry 音频 provider 注册 ----


def test_registry_audio_defaults_to_null() -> None:
    from xagent.domains.creative_studio.media import get_media_registry

    reg = get_media_registry()
    assert reg.get(MediaKind.audio).name == "null"


def test_registry_audio_edge_tts_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("edge_tts", reason="edge-tts 为可选 extra（tts），未装时跳过")
    from xagent.domains.creative_studio.media import (
        get_media_registry,
        reset_media_registry,
    )
    from xagent.infra.settings import get_settings

    monkeypatch.setenv("XAGENT_MEDIA__DEFAULT_AUDIO_PROVIDER", "edge_tts")
    get_settings.cache_clear()
    reset_media_registry()
    try:
        reg = get_media_registry()
        provider = reg.get(MediaKind.audio)
        assert provider.name == "edge_tts"
        assert isinstance(provider, EdgeTTSProvider)
    finally:
        get_settings.cache_clear()
        reset_media_registry()


async def test_null_audio_placeholder() -> None:
    """NullProvider 音频占位产物：lite/CI 无网也可走通配音步骤。"""
    from xagent.domains.creative_studio.media import get_media_registry

    reg = get_media_registry()
    task = await reg.generate(_req("占位台词"), wait=False)
    assert task.status == "succeeded"
    assert "text_to_speech" in task.outputs[0]


# ---- voice_assigner 音色映射 ----


def test_voice_assigner_gender_and_age_heuristics() -> None:
    from xagent.domains.creative_studio.storyboard import CharacterCard
    from xagent.domains.creative_studio.voice_assigner import (
        assign_voice,
        infer_age_group,
        infer_gender,
    )

    assert infer_gender("逆袭女主") == "female"
    assert infer_gender("霸总") == "male"
    assert infer_gender("路人") == "unknown"
    assert infer_age_group("白发苍苍的老爷爷") == "older"
    assert infer_age_group("十七岁少女") == "young"
    assert infer_age_group("职场精英") == "adult"

    boss = assign_voice(CharacterCard(name="苏总", role="霸总"))
    assert boss.gender == "male"
    assert boss.voice == "zh-CN-YunjianNeural"

    heroine = assign_voice(CharacterCard(name="林晚", role="逆袭女主"))
    assert heroine.gender == "female"
    assert heroine.voice.startswith("zh-CN-Xiao")

    grandpa = assign_voice(CharacterCard(name="老爷子", role="家族老爷爷"))
    assert grandpa.voice == "zh-CN-YunzeNeural"


def test_voice_assigner_distinct_voices_same_bucket() -> None:
    from xagent.domains.creative_studio.storyboard import CharacterCard, Storyboard
    from xagent.domains.creative_studio.voice_assigner import assign_voices

    sb = Storyboard(
        characters=[
            CharacterCard(name="甲", role="霸总"),
            CharacterCard(name="乙", role="霸道总裁"),
        ]
    )
    profiles = assign_voices(sb)
    # 同（男, 成年）桶的两个角色应错开音色
    assert profiles["甲"].voice != profiles["乙"].voice


def test_voice_for_shot_fallback() -> None:
    from xagent.domains.creative_studio.storyboard import (
        CharacterCard,
        Shot,
        Storyboard,
    )
    from xagent.domains.creative_studio.voice_assigner import (
        assign_voices,
        voice_for_shot,
    )

    sb = Storyboard(characters=[CharacterCard(name="苏总", role="霸总")])
    profiles = assign_voices(sb)
    hit = voice_for_shot(Shot(characters=["苏总"], dialogue="你走吧"), profiles)
    assert hit.voice == "zh-CN-YunjianNeural"
    # 未匹配角色 -> 旁白默认音色
    miss = voice_for_shot(Shot(characters=["不存在"], dialogue="x"), profiles)
    assert miss.voice == DEFAULT_VOICE


# ---- canvas 节点 → 媒体规格映射（batch-generate 配音分支的领域侧支撑）----


def test_canvas_media_spec_for_voiceover_node() -> None:
    from xagent.domains.creative_studio.canvas import NodeType, media_spec_for_node

    assert media_spec_for_node(NodeType.keyframe) == (
        MediaKind.image, GenerationMode.text_to_image,
    )
    assert media_spec_for_node(NodeType.video) == (
        MediaKind.video, GenerationMode.text_to_video,
    )
    assert media_spec_for_node(NodeType.voiceover) == (
        MediaKind.audio, GenerationMode.text_to_speech,
    )
    assert media_spec_for_node(NodeType.subtitle) is None


# ---- pipeline 配音步骤 ----


class _ScriptedLLM:
    """返回合法故事板 JSON 的测试 LLM（含角色卡 + 台词）。"""

    supports_tools = False

    async def complete(self, messages, **kw):  # noqa: ARG002
        import json

        from xagent.adapters.llm.base import LLMResponse

        payload = {
            "title": "霸总逆袭",
            "characters": [
                {"name": "苏总", "role": "霸总"},
                {"name": "林晚", "role": "逆袭女主"},
            ],
            "scenes": [{"location": "办公室", "description": "对峙"}],
            "shots": [
                {
                    "duration_seconds": 4, "scene": "办公室",
                    "characters": ["苏总"], "plot_purpose": "引入",
                    "dialogue": "你以为能赢？", "subtitle": "你以为能赢？",
                },
                {
                    "duration_seconds": 4, "scene": "办公室",
                    "characters": ["林晚"], "plot_purpose": "反转",
                    "dialogue": "我早赢了。", "subtitle": "我早赢了。",
                },
                {
                    "duration_seconds": 4, "scene": "走廊", "plot_purpose": "空镜",
                    "dialogue": "", "subtitle": "",
                },
            ],
        }
        return LLMResponse(content=json.dumps(payload, ensure_ascii=False), model="test")

    async def complete_with_tools(self, messages, tools, **kw):  # noqa: ARG002
        raise NotImplementedError

    async def health(self) -> bool:
        return True


class _FailingAudioProvider:
    """永远失败的音频 provider（验证配音降级不阻断整体）。"""

    name = "failing_audio"
    supported_kinds = {MediaKind.audio}
    supported_modes = {GenerationMode.text_to_speech}

    async def submit(self, req: GenerationRequest) -> GenerationTask:  # noqa: ARG002
        return GenerationTask(
            task_id="fail-1", provider=self.name, status="failed", error="TTS 服务不可用",
        )

    async def poll(self, task_id: str) -> GenerationTask:
        return GenerationTask(task_id=task_id, provider=self.name, status="failed", error="x")

    def list_models(self, kind=None):  # noqa: ARG002
        return []


async def test_pipeline_voiceover_step_with_null_provider() -> None:
    """默认 null 音频 provider：配音步骤产出占位产物，音色按角色分配。"""
    from xagent.domains.creative_studio.pipeline import produce_short_drama

    result = await produce_short_drama("霸总逆袭", llm=_ScriptedLLM(), with_video=False)
    assert result.status == "produced"
    assert len(result.shots) == 3
    # 有台词的镜头：占位音频 + 角色音色
    assert result.shots[0].audio_outputs
    assert "text_to_speech" in result.shots[0].audio_outputs[0]
    assert result.shots[0].voice == "zh-CN-YunjianNeural"  # 霸总 -> 低沉男声
    assert result.shots[1].audio_outputs
    assert result.shots[1].voice.startswith("zh-CN-Xiao")  # 女主 -> 女声
    assert result.shots[0].audio_error is None
    # 无台词镜头：跳过配音
    assert result.shots[2].audio_outputs == []
    assert result.shots[2].voice == ""
    # to_dict 透出配音字段
    d = result.to_dict()
    assert d["shots"][0]["voice"]
    assert "audio_outputs" in d["shots"][0]


async def test_pipeline_voiceover_disabled() -> None:
    from xagent.domains.creative_studio.pipeline import produce_short_drama

    result = await produce_short_drama(
        "霸总逆袭", llm=_ScriptedLLM(), with_video=False, with_voiceover=False,
    )
    assert result.status == "produced"
    for shot in result.shots:
        assert shot.audio_outputs == []
        assert shot.voice == ""


async def test_pipeline_voiceover_failure_degrades_not_blocks() -> None:
    """配音失败：单镜头记 audio_error，整体 status 不受影响。"""
    from xagent.domains.creative_studio.media import get_media_registry
    from xagent.domains.creative_studio.pipeline import produce_short_drama

    get_media_registry().register(MediaKind.audio, _FailingAudioProvider())
    result = await produce_short_drama("霸总逆袭", llm=_ScriptedLLM(), with_video=False)
    assert result.status == "produced"  # 配音失败不阻断
    assert result.shots[0].audio_error == "TTS 服务不可用"
    assert result.shots[0].audio_outputs == []
    # 图像产物不受影响
    assert result.shots[0].image_outputs


async def test_pipeline_timeline_includes_local_audio_clip() -> None:
    """配音产物为本地文件时，自动时间线包含音频轨片段；占位 URL 则跳过。"""
    from xagent.domains.creative_studio.editor.tools import _timelines
    from xagent.domains.creative_studio.media import get_media_registry
    from xagent.domains.creative_studio.pipeline import produce_short_drama

    class _LocalAudioProvider(_FailingAudioProvider):
        name = "local_audio"

        async def submit(self, req: GenerationRequest) -> GenerationTask:
            path = Path(sys.modules[__name__].__file__).parent / "_tmp_vo.mp3"
            path.write_bytes(b"fake")
            return GenerationTask(
                task_id="local-1", provider=self.name,
                status="succeeded", outputs=[str(path)],
            )

    get_media_registry().register(MediaKind.audio, _LocalAudioProvider())
    result = await produce_short_drama("霸总逆袭", llm=_ScriptedLLM(), with_video=False)
    assert result.timeline_id
    tl = _timelines[result.timeline_id]
    audio_clips = [c for c in tl.clips if c.track_type.value == "audio"]
    # 2 个有台词的镜头 -> 2 条音频片段
    assert len(audio_clips) == 2


# ---- editor 音频轨混流 ----


async def test_render_mixes_audio_track(tmp_path) -> None:
    """MoviePy 渲染：音频轨（配音）合成进成片。"""
    import os

    from xagent.domains.creative_studio.editor.models import (
        Clip,
        Timeline,
        TrackType,
    )
    from xagent.domains.creative_studio.editor.video_editor import VideoEditor

    editor = VideoEditor(output_dir=str(tmp_path))
    if not editor.has_moviepy():
        pytest.skip("moviepy 未安装")

    import math
    import struct
    import wave

    # 生成 0.5s 正弦波 wav 作为配音素材
    wav_path = tmp_path / "vo.wav"
    framerate = 8000
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        frames = b"".join(
            struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * t / framerate)))
            for t in range(int(framerate * 0.5))
        )
        w.writeframes(frames)

    tl = Timeline(name="混流测试", width=64, height=64, fps=10)
    tl.add_clip(Clip(
        track_type=TrackType.audio, source_url=str(wav_path),
        timeline_start=0, timeline_end=0.5,
    ))
    result = await editor.render(tl, "mix_test.mp4")
    assert result["ok"], result.get("error")
    assert os.path.exists(result["output_path"])

    # 成片含音频轨
    from moviepy import VideoFileClip

    rendered = VideoFileClip(result["output_path"])
    try:
        assert rendered.audio is not None
    finally:
        rendered.close()
