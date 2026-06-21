"""云媒体生成 provider（参考 LibLib / LibTV 模式）。

不自托管 ComfyUI（规避 GPL）。provider 协议为「云任务」语义：
submit() -> task_id；poll(task_id) -> status/outputs。详见
docs/CREATIVE_STUDIO_MEDIA.md。
"""

from xagent.domains.creative_studio.media.base import (
    GenerationRequest,
    GenerationTask,
    MediaKind,
    MediaProvider,
    ModelCard,
)
from xagent.domains.creative_studio.media.registry import (
    MediaProviderRegistry,
    get_media_registry,
    reset_media_registry,
)

__all__ = [
    "GenerationRequest",
    "GenerationTask",
    "MediaKind",
    "MediaProvider",
    "ModelCard",
    "MediaProviderRegistry",
    "get_media_registry",
    "reset_media_registry",
]
