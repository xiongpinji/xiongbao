"""云媒体生成 provider（多模型可插拔）。

图像：OpenAI 兼容（gpt-image-2 / DALL·E），文生图 + 图生图。
视频：可灵 Kling / 即梦 Jimeng / 通用任务式 HTTP，文生视频 + 图生视频。
provider 协议为「云任务」语义：submit() -> task_id；poll(task_id) -> status/outputs。
未配 key 时 NullProvider 占位，流程不中断。
"""

from xagent.domains.creative_studio.media.base import (
    GenerationMode,
    GenerationRequest,
    GenerationTask,
    MediaKind,
    MediaProvider,
    ModelCard,
    NullProvider,
)
from xagent.domains.creative_studio.media.registry import (
    MediaProviderRegistry,
    get_media_registry,
    reset_media_registry,
)

__all__ = [
    "GenerationMode",
    "GenerationRequest",
    "GenerationTask",
    "MediaKind",
    "MediaProvider",
    "ModelCard",
    "NullProvider",
    "MediaProviderRegistry",
    "get_media_registry",
    "reset_media_registry",
]
