"""短剧工厂：一句话 brief → 生产工作流草稿 → 人工审核导出（★护城河）。

媒体生成走云端 AI 生成平台 API（LibLib/LibTV 风格），不自托管 ComfyUI。
详见 docs/CREATIVE_STUDIO_MEDIA.md。

模块：
  storyboard       —— 故事板数据契约（移植自旧仓，去除 backend.app 依赖）
  quality          —— 质量门
  media            —— 云生成 provider 抽象（image/video/audio）
  producer         —— 制作人 agent（DI：llm_caller + media registry）
  workflow_draft   —— 一句话→待审核工作流草稿（节点链）
"""

from xagent.domains.creative_studio.storyboard import (
    AspectRatio,
    CameraSpec,
    CharacterCard,
    LightingSpec,
    SceneCard,
    Shot,
    ShotContinuity,
    Storyboard,
    StoryboardStatus,
    SubtitleTrack,
)
from xagent.domains.creative_studio.workflow_draft import (
    WorkflowDraft,
    WorkflowDraftNode,
    build_draft_from_brief,
)

__all__ = [
    "AspectRatio",
    "CameraSpec",
    "CharacterCard",
    "LightingSpec",
    "SceneCard",
    "Shot",
    "ShotContinuity",
    "Storyboard",
    "StoryboardStatus",
    "SubtitleTrack",
    "WorkflowDraft",
    "WorkflowDraftNode",
    "build_draft_from_brief",
]
