"""短剧全链路编排器：一句话 brief → 成片产物。

链路：
  1. LLM 生成结构化故事板（producer.generate_storyboard）
  2. 逐镜头生成关键帧图（image provider，text_to_image）
  3. 逐镜头生成视频片段（video provider，image_to_video 用关键帧驱动；无关键帧则 text_to_video）
  4. 汇总成 ProductionResult（含故事板 + 每镜头图/视频产物 + 质量门）

设计为「尽力而为」：单镜头媒体生成失败不中断整片，记录 error 继续。
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
    image_error: str | None = None
    video_error: str | None = None


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
            "shots": [
                {
                    "shot_id": s.shot_id,
                    "scene": s.scene,
                    "image_prompt": s.image_prompt,
                    "video_prompt": s.video_prompt,
                    "image_outputs": s.image_outputs,
                    "video_outputs": s.video_outputs,
                    "image_error": s.image_error,
                    "video_error": s.video_error,
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
    llm: LLMClient | None = None,
) -> ProductionResult:
    """一句话 brief 全链路产出短剧（故事板 + 逐镜头图/视频）。"""
    # 1. 生成故事板
    sb: Storyboard = await generate_storyboard(
        brief, genre=genre, platform=platform,
        target_duration_seconds=target_duration_seconds, llm=llm,
    )
    gates = run_gates(sb)
    registry = get_media_registry()

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

        shots.append(product)

    status = "partial" if any_fail else "produced"
    if not shots:
        status = "failed"

    logger.info(
        "short_drama_produced",
        storyboard_id=sb.storyboard_id, shots=len(shots), status=status,
    )
    return ProductionResult(
        storyboard_id=sb.storyboard_id,
        title=sb.title or brief[:20],
        brief=brief, genre=genre, platform=platform,
        status=status,
        shots=shots,
        quality_passed=all(g.passed for g in gates),
        quality_gates=[g.model_dump() for g in gates],
    )
