"""媒体 provider 抽象 + Null 降级实现。

支持多模型媒体生成（文生图/图生图/文生视频/图生视频），provider 可插拔。
预留：gpt-image-2 / DALL·E（图像）、可灵 Kling / 即梦（视频）等通用接口。
NullProvider 保证 lite/CI 无外部 key 即可走完草稿工作流（产物为占位）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


class MediaKind(str, Enum):  # noqa: UP042
    image = "image"
    video = "video"
    audio = "audio"


class GenerationMode(str, Enum):  # noqa: UP042
    """生成模式：区分文生/图生。"""

    text_to_image = "text_to_image"
    image_to_image = "image_to_image"
    text_to_video = "text_to_video"
    image_to_video = "image_to_video"
    text_to_speech = "text_to_speech"


@dataclass
class ModelCard:
    model_id: str
    name: str
    kind: MediaKind
    modes: list[GenerationMode] = field(default_factory=list)
    provider: str = ""
    description: str = ""
    max_duration_seconds: float | None = None  # 视频模型时长上限
    resolutions: list[str] = field(default_factory=list)


@dataclass
class GenerationRequest:
    kind: MediaKind
    prompt: str
    mode: GenerationMode = GenerationMode.text_to_image
    model_id: str | None = None
    negative_prompt: str = ""
    loras: list[str] = field(default_factory=list)
    reference_images: list[str] = field(default_factory=list)  # 图生图/图生视频输入
    # 视频参数
    duration_seconds: float | None = None
    fps: int | None = None
    resolution: str | None = None
    seed: int | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationTask:
    task_id: str
    provider: str = ""
    status: str = "queued"  # queued | running | succeeded | failed
    outputs: list[str] = field(default_factory=list)  # 产物 URL / 路径
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MediaProvider(Protocol):
    name: str
    supported_kinds: set[MediaKind]
    supported_modes: set[GenerationMode]

    async def submit(self, req: GenerationRequest) -> GenerationTask: ...
    async def poll(self, task_id: str) -> GenerationTask: ...
    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]: ...


class NullProvider:
    """降级实现：返回占位产物，保证草稿流程不中断（无需任何 key）。"""

    name = "null"
    supported_kinds = {MediaKind.image, MediaKind.video, MediaKind.audio}
    supported_modes = set(GenerationMode)

    async def submit(self, req: GenerationRequest) -> GenerationTask:
        h = abs(hash(req.prompt)) % 100000
        return GenerationTask(
            task_id=f"null-{req.kind.value}-{h}-{uuid4().hex[:8]}",
            provider=self.name,
            status="succeeded",
            outputs=[f"placeholder://{req.kind.value}/{req.mode.value}/{h}"],
        )

    async def poll(self, task_id: str) -> GenerationTask:
        return GenerationTask(
            task_id=task_id, provider=self.name, status="succeeded",
            outputs=[f"placeholder://{task_id}"],
        )

    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]:
        cards = [
            ModelCard("null-image", "占位图像模型", MediaKind.image,
                      [GenerationMode.text_to_image, GenerationMode.image_to_image], "null"),
            ModelCard("null-video", "占位视频模型", MediaKind.video,
                      [GenerationMode.text_to_video, GenerationMode.image_to_video], "null"),
            ModelCard("null-audio", "占位音频模型", MediaKind.audio,
                      [GenerationMode.text_to_speech], "null"),
        ]
        return [c for c in cards if kind is None or c.kind == kind]
