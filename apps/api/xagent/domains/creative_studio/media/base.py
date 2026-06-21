"""媒体 provider 抽象 + Null 降级实现。

NullProvider 保证 lite/CI 无外部 key 即可走完草稿工作流（产物为占位），
沿用旧仓「确定性回退，流程不中断」思想。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class MediaKind(str, Enum):  # noqa: UP042
    image = "image"
    video = "video"
    audio = "audio"


@dataclass
class ModelCard:
    model_id: str
    name: str
    kind: MediaKind
    description: str = ""


@dataclass
class GenerationRequest:
    kind: MediaKind
    prompt: str
    model_id: str | None = None
    loras: list[str] = field(default_factory=list)
    reference_images: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationTask:
    task_id: str
    status: str = "queued"  # queued | running | succeeded | failed
    outputs: list[str] = field(default_factory=list)
    error: str | None = None


@runtime_checkable
class MediaProvider(Protocol):
    name: str
    supported_kinds: set[MediaKind]

    async def submit(self, req: GenerationRequest) -> GenerationTask: ...
    async def poll(self, task_id: str) -> GenerationTask: ...
    def list_models(self, kind: MediaKind) -> list[ModelCard]: ...


class NullProvider:
    """降级实现：返回占位产物，保证草稿流程不中断。"""

    name = "null"
    supported_kinds = {MediaKind.image, MediaKind.video, MediaKind.audio}

    async def submit(self, req: GenerationRequest) -> GenerationTask:
        return GenerationTask(
            task_id=f"null-{req.kind.value}",
            status="succeeded",
            outputs=[f"placeholder://{req.kind.value}/{abs(hash(req.prompt))}"],
        )

    async def poll(self, task_id: str) -> GenerationTask:
        return GenerationTask(task_id=task_id, status="succeeded", outputs=[f"placeholder://{task_id}"])

    def list_models(self, kind: MediaKind) -> list[ModelCard]:
        return [ModelCard(model_id="null", name="占位模型", kind=kind)]
