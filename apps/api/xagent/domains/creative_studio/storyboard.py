"""故事板数据契约（storyboard-first），移植自旧仓 creative_studio 并清理。

故事板是整个短剧工作流的核心契约：编剧/分镜/摄影灯光/图片/视频/TTS/字幕/剪辑
都从这里读取结构化字段；模型 adapter 只负责把字段编译成各自 prompt。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class StoryboardStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    SCRIPTED = "scripted"
    STORYBOARDED = "storyboarded"
    ASSETS_READY = "assets_ready"
    COMPOSED = "composed"
    FAILED = "failed"


class AspectRatio(str, Enum):  # noqa: UP042
    """画面比例，短剧默认竖屏 9:16。"""

    VERTICAL = "9:16"
    HORIZONTAL = "16:9"
    SQUARE = "1:1"


class CameraSpec(BaseModel):
    shot_size: str = "medium"
    angle: str = "eye-level"
    movement: str = "static"
    lens: str = "50mm"
    focus: str = "deep focus"
    composition: str = "rule of thirds"


class LightingSpec(BaseModel):
    style: str = "natural"
    key_light: str = "soft frontal"
    fill_light: str = "minimal"
    back_light: str = "subtle rim"
    contrast: str = "medium"
    color_temperature: str = "neutral"
    mood: str = "neutral"


class ShotContinuity(BaseModel):
    character_ref: str = ""
    scene_ref: str = ""
    style_ref: str = ""


class Shot(BaseModel):
    shot_id: str = Field(default_factory=lambda: uuid4().hex[:8])
    duration_seconds: float = 4.0
    scene: str = ""
    characters: list[str] = Field(default_factory=list)
    plot_purpose: str = ""
    camera: CameraSpec = Field(default_factory=CameraSpec)
    lighting: LightingSpec = Field(default_factory=LightingSpec)
    continuity: ShotContinuity = Field(default_factory=ShotContinuity)
    dialogue: str = ""
    action: str = ""
    subtitle: str = ""
    image_prompt: str = ""
    video_prompt: str = ""


class SceneCard(BaseModel):
    scene_id: str = Field(default_factory=lambda: uuid4().hex[:8])
    location: str = ""
    time_of_day: str = ""
    description: str = ""


class CharacterCard(BaseModel):
    character_id: str = Field(default_factory=lambda: uuid4().hex[:8])
    name: str = ""
    role: str = ""  # 逆袭女主/霸总/甜宠男主...
    appearance: str = ""
    personality: str = ""


class SubtitleTrack(BaseModel):
    shot_id: str
    text: str
    start: float
    end: float


class QualityGate(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class Storyboard(BaseModel):
    """故事板根契约。"""

    storyboard_id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = ""
    brief: str = ""
    genre: str = ""            # 逆袭/霸总/甜宠/重生...
    platform: str = ""         # 抖音/快手/小红书
    aspect_ratio: AspectRatio = AspectRatio.VERTICAL
    target_duration_seconds: float = 60.0
    characters: list[CharacterCard] = Field(default_factory=list)
    scenes: list[SceneCard] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
    subtitles: list[SubtitleTrack] = Field(default_factory=list)
    status: StoryboardStatus = StoryboardStatus.DRAFT
    created_at: datetime = Field(default_factory=_utcnow)

    def total_shot_duration(self) -> float:
        return sum(s.duration_seconds for s in self.shots)
