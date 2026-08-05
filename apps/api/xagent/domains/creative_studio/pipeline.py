"""短剧全链路编排器：一句话 brief → 成片产物。

链路：
  1. LLM 生成结构化故事板（producer.generate_storyboard）
  2. 逐镜头生成关键帧图（image provider，text_to_image）
  3. 逐镜头生成视频片段（video provider，image_to_video 用关键帧驱动；无关键帧则 text_to_video）
  4. 逐镜头配音（audio provider，text_to_speech，按台词/字幕文本 + 角色音色分配）
  5. 汇总成 ProductionResult（含故事板 + 每镜头图/视频/音频产物 + 质量门）

设计为「尽力而为」：单镜头媒体生成失败不中断整片，记录 error 继续。
配音为增强轨：单镜头配音失败仅记 audio_error，不影响整体 status。
未配 media key 时走 NullProvider（占位产物），全链路仍可端到端跑通。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from xagent.adapters.llm import LLMClient
from xagent.domains.creative_studio.media import (
    GenerationMode,
    GenerationRequest,
    MediaKind,
    get_media_registry,
)
from xagent.domains.creative_studio.producer import generate_storyboard
from xagent.domains.creative_studio.quality import run_gates
from xagent.domains.creative_studio.storyboard import Storyboard
from xagent.domains.creative_studio.voice_assigner import assign_voices, voice_for_shot
from xagent.infra.logging import get_logger

logger = get_logger("xagent.creative.pipeline")


@dataclass
class ShotProduct:
    shot_id: str
    scene: str
    image_prompt: str
    video_prompt: str
    image_outputs: list[str] = field(default_factory=list)
    video_outputs: list[str] = field(default_factory=list)
    audio_outputs: list[str] = field(default_factory=list)
    voice: str = ""  # 配音音色（edge-tts voice id）
    image_error: str | None = None
    video_error: str | None = None
    audio_error: str | None = None


@dataclass
class ProductionResult:
    storyboard_id: str
    title: str
    brief: str
    genre: str
    platform: str
    status: str  # produced | partial | failed
    shots: list[ShotProduct] = field(default_factory=list)
    quality_passed: bool = False
    quality_gates: list[dict] = field(default_factory=list)
    timeline_id: str | None = None  # 自动创建的剪辑时间线 ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "storyboard_id": self.storyboard_id,
            "title": self.title,
            "brief": self.brief,
            "genre": self.genre,
            "platform": self.platform,
            "status": self.status,
            "quality_passed": self.quality_passed,
            "quality_gates": self.quality_gates,
            "timeline_id": self.timeline_id,
            "shots": [
                {
                    "shot_id": s.shot_id,
                    "scene": s.scene,
                    "image_prompt": s.image_prompt,
                    "video_prompt": s.video_prompt,
                    "image_outputs": s.image_outputs,
                    "video_outputs": s.video_outputs,
                    "audio_outputs": s.audio_outputs,
                    "voice": s.voice,
                    "image_error": s.image_error,
                    "video_error": s.video_error,
                    "audio_error": s.audio_error,
                }
                for s in self.shots
            ],
        }


def _shot_image_prompt(shot) -> str:
    """组合镜头的图像提示词。"""
    if shot.image_prompt:
        return shot.image_prompt
    parts = [shot.scene, shot.action, shot.dialogue]
    return "，".join(p for p in parts if p) or shot.plot_purpose or "电影感画面"


def _shot_video_prompt(shot) -> str:
    if shot.video_prompt:
        return shot.video_prompt
    return _shot_image_prompt(shot)


async def produce_short_drama(
    brief: str,
    *,
    genre: str = "逆袭",
    platform: str = "抖音",
    target_duration_seconds: float = 60.0,
    with_video: bool = True,
    with_voiceover: bool = True,
    llm: LLMClient | None = None,
) -> ProductionResult:
    """一句话 brief 全链路产出短剧（故事板 + 逐镜头图/视频/配音）。"""
    # 1. 生成故事板
    sb: Storyboard = await generate_storyboard(
        brief, genre=genre, platform=platform,
        target_duration_seconds=target_duration_seconds, llm=llm,
    )
    gates = run_gates(sb)
    registry = get_media_registry()
    # 角色 → 音色分配（启发式，离线确定性）
    voice_assignments = assign_voices(sb) if with_voiceover else {}

    shots: list[ShotProduct] = []
    any_fail = False
    for shot in sb.shots:
        img_prompt = _shot_image_prompt(shot)
        vid_prompt = _shot_video_prompt(shot)
        product = ShotProduct(
            shot_id=shot.shot_id, scene=shot.scene,
            image_prompt=img_prompt, video_prompt=vid_prompt,
        )
        # 2. 关键帧图
        try:
            img_task = await registry.generate(
                GenerationRequest(
                    kind=MediaKind.image, prompt=img_prompt,
                    mode=GenerationMode.text_to_image,
                ),
                wait=True,
            )
            if img_task.status == "succeeded":
                product.image_outputs = img_task.outputs
            else:
                product.image_error = img_task.error
                any_fail = True
        except Exception as exc:
            product.image_error = str(exc)
            any_fail = True

        # 3. 视频片段（用关键帧驱动 image_to_video；无图则 text_to_video）
        if with_video:
            try:
                ref = product.image_outputs[:1]
                mode = (
                    GenerationMode.image_to_video if ref
                    else GenerationMode.text_to_video
                )
                vid_task = await registry.generate(
                    GenerationRequest(
                        kind=MediaKind.video, prompt=vid_prompt, mode=mode,
                        reference_images=ref,
                        duration_seconds=shot.duration_seconds,
                    ),
                    wait=True,
                )
                if vid_task.status == "succeeded":
                    product.video_outputs = vid_task.outputs
                else:
                    product.video_error = vid_task.error
                    any_fail = True
            except Exception as exc:
                product.video_error = str(exc)
                any_fail = True

        # 4. 配音（按台词/字幕文本；增强轨，失败仅记录不阻断整体）
        if with_voiceover:
            vo_text = (shot.dialogue or shot.subtitle or "").strip()
            if vo_text:
                try:
                    profile = voice_for_shot(shot, voice_assignments)
                    product.voice = profile.voice
                    audio_task = await registry.generate(
                        GenerationRequest(
                            kind=MediaKind.audio, prompt=vo_text,
                            mode=GenerationMode.text_to_speech,
                            params=profile.to_params(),
                        ),
                        wait=True,
                    )
                    if audio_task.status == "succeeded":
                        product.audio_outputs = audio_task.outputs
                    else:
                        product.audio_error = audio_task.error
                except Exception as exc:
                    product.audio_error = str(exc)

        shots.append(product)

    status = "partial" if any_fail else "produced"
    if not shots:
        status = "failed"

    # 自动创建剪辑时间线（把产出视频导入剪辑工作台）
    timeline_id = _create_timeline_from_shots(shots, sb, genre, platform)

    logger.info(
        "short_drama_produced",
        storyboard_id=sb.storyboard_id, shots=len(shots), status=status,
        timeline_id=timeline_id,
    )
    return ProductionResult(
        storyboard_id=sb.storyboard_id,
        title=sb.title or brief[:20],
        brief=brief, genre=genre, platform=platform,
        status=status,
        shots=shots,
        quality_passed=all(g.passed for g in gates),
        quality_gates=[g.model_dump() for g in gates],
        timeline_id=timeline_id,
    )


def _create_timeline_from_shots(
    shots: list[ShotProduct], sb: Storyboard, genre: str, platform: str
) -> str | None:
    """把产出视频自动创建为剪辑时间线，导入剪辑工作台。"""
    try:
        from xagent.domains.creative_studio.editor.models import (
            Clip,
            Timeline,
            TrackType,
        )
        from xagent.domains.creative_studio.editor.tools import _timelines

        tl = Timeline(
            name=f"短剧-{sb.title or genre}",
            width=1080,
            height=1920 if platform in ("抖音", "快手") else 1920,
            fps=30,
        )
        cursor = 0.0
        for i, shot in enumerate(shots):
            # 视频片段
            if shot.video_outputs:
                dur = sb.shots[i].duration_seconds if i < len(sb.shots) else 4.0
                tl.add_clip(Clip(
                    track_type=TrackType.video,
                    source_url=shot.video_outputs[0],
                    timeline_start=cursor,
                    timeline_end=cursor + dur,
                ))
                cursor += dur
            # 字幕片段
            if i < len(sb.shots) and sb.shots[i].dialogue:
                dur = sb.shots[i].duration_seconds if i < len(sb.shots) else 4.0
                tl.add_clip(Clip(
                    track_type=TrackType.text,
                    text=sb.shots[i].dialogue,
                    timeline_start=cursor - dur if shot.video_outputs else cursor,
                    timeline_end=cursor if shot.video_outputs else cursor + dur,
                    font_size=56,
                    position="bottom",
                ))
            # 配音片段（仅本地音频文件进时间线；占位 URL 跳过，MoviePy 无法打开）
            if shot.audio_outputs and "://" not in shot.audio_outputs[0]:
                a_dur = sb.shots[i].duration_seconds if i < len(sb.shots) else 4.0
                tl.add_clip(Clip(
                    track_type=TrackType.audio,
                    source_url=shot.audio_outputs[0],
                    timeline_start=cursor - a_dur if shot.video_outputs else cursor,
                    timeline_end=cursor if shot.video_outputs else cursor + a_dur,
                ))
        _timelines[tl.id] = tl
        logger.info("timeline_auto_created", timeline_id=tl.id, clips=len(tl.clips))
        return tl.id
    except Exception as exc:
        logger.warning("timeline_create_failed", error=str(exc))
        return None
