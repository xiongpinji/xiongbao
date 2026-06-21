"""剪辑数据模型：时间线 / 轨道 / 片段 / 转场。

设计为引擎无关的中间表示——VideoEditor 据此驱动 MoviePy 或 pyJianYingDraft。
智能体通过工具操作这些模型（增删片段/转场/字幕/配乐），最后渲染或导出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4


class TrackType(str, Enum):  # noqa: UP042
    video = "video"
    audio = "audio"
    text = "text"


class TransitionType(str, Enum):  # noqa: UP042
    dissolve = "dissolve"
    fade = "fade"
    wipe = "wipe"
    slide = "slide"
    zoom = "zoom"


@dataclass
class Clip:
    """时间线上的一个片段（视频/音频/文本）。"""

    id: str = field(default_factory=lambda: uuid4().hex[:8])
    track_type: TrackType = TrackType.video
    source_url: str = ""           # 视频/音频素材 URL 或本地路径
    # 时间线位置（秒）
    timeline_start: float = 0.0
    timeline_end: float = 4.0
    # 素材截取范围（秒）；None 表示从头到尾
    source_start: float | None = None
    source_end: float | None = None
    # 文本属性（track_type=text 时）
    text: str = ""
    font_size: int = 48
    color: str = "#ffffff"
    position: str = "center"       # center / bottom / top / (x,y)
    # 音频属性
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0

    @property
    def duration(self) -> float:
        return max(0, self.timeline_end - self.timeline_start)


@dataclass
class Transition:
    """片段间转场。"""

    id: str = field(default_factory=lambda: uuid4().hex[:8])
    clip_id: str = ""              # 应用到哪个片段（与前一片段的过渡）
    type: TransitionType = TransitionType.dissolve
    duration: float = 0.5


@dataclass
class Timeline:
    """完整时间线（项目）。"""

    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = "未命名"
    width: int = 1080
    height: int = 1920             # 竖屏短剧默认 9:16
    fps: int = 30
    clips: list[Clip] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    created_at: str = ""

    @property
    def total_duration(self) -> float:
        if not self.clips:
            return 0.0
        return max(c.timeline_end for c in self.clips)

    def add_clip(self, clip: Clip) -> Clip:
        self.clips.append(clip)
        return clip

    def add_transition(self, tr: Transition) -> Transition:
        self.transitions.append(tr)
        return tr

    def remove_clip(self, clip_id: str) -> bool:
        before = len(self.clips)
        self.clips = [c for c in self.clips if c.id != clip_id]
        self.transitions = [t for t in self.transitions if t.clip_id != clip_id]
        return len(self.clips) < before

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "total_duration": round(self.total_duration, 2),
            "clips": [
                {
                    "id": c.id, "track_type": c.track_type.value,
                    "source_url": c.source_url,
                    "timeline_start": c.timeline_start,
                    "timeline_end": c.timeline_end,
                    "source_start": c.source_start, "source_end": c.source_end,
                    "text": c.text, "font_size": c.font_size,
                    "color": c.color, "position": c.position,
                    "volume": c.volume, "fade_in": c.fade_in, "fade_out": c.fade_out,
                    "duration": round(c.duration, 2),
                }
                for c in self.clips
            ],
            "transitions": [
                {"id": t.id, "clip_id": t.clip_id, "type": t.type.value, "duration": t.duration}
                for t in self.transitions
            ],
        }
