"""视频剪辑数据模型（引擎无关的中间表示）。

Timeline 是核心：包含轨道 + 片段 + 转场，可渲染为视频（MoviePy）
或导出为剪映草稿（pyJianYingDraft）。智能体通过工具操作这些模型。
"""

from xagent.domains.creative_studio.editor.models import (
    Clip,
    Timeline,
    TrackType,
    Transition,
    TransitionType,
)

__all__ = [
    "Clip",
    "Timeline",
    "TrackType",
    "Transition",
    "TransitionType",
]
