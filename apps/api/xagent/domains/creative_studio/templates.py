"""短剧模板库：预设题材一键生成节点链。

用户选择模板（逆袭/甜宠/霸总/重生/悬疑），直接生成对应节点链，
无需从零写 brief。模板含预设角色、场景、镜头数、节奏。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DramaTemplate:
    id: str
    name: str
    genre: str
    description: str
    brief: str
    default_platform: str = "抖音"
    target_duration: float = 60.0
    tags: list[str] = field(default_factory=list)


TEMPLATES: list[DramaTemplate] = [
    DramaTemplate(
        id="nixi", name="逆袭爽文", genre="逆袭",
        description="落魄主角逆袭翻盘，打脸全场",
        brief="一个被轻视的底层人物，通过隐藏实力逐步翻盘，最终在关键时刻震惊所有人",
        tags=["打脸", "翻盘", "爽感"],
    ),
    DramaTemplate(
        id="tianchong", name="甜宠日常", genre="甜宠",
        description="高冷男主独宠女主，甜到齁",
        brief="表面冷酷的总裁对平凡女孩展露温柔一面，日常互动甜蜜有爱",
        tags=["高甜", "日常", "治愈"],
    ),
    DramaTemplate(
        id="bazong", name="霸总强制爱", genre="霸总",
        description="霸道总裁爱上我经典桥段",
        brief="强势霸总与倔强女主的冲突与吸引，从对立到心动的经典霸总剧情",
        tags=["霸总", "冲突", "心动"],
    ),
    DramaTemplate(
        id="chongsheng", name="重生复仇", genre="重生",
        description="重生回到过去，改写命运",
        brief="主角重生回到关键时刻，带着前世记忆步步为营，复仇并改写命运",
        tags=["重生", "复仇", "智斗"],
    ),
    DramaTemplate(
        id="xuanyi", name="悬疑反转", genre="悬疑",
        description="层层反转，不到最后猜不到结局",
        brief="一个看似简单的事件背后隐藏惊天秘密，每个角色都有不可告人的动机",
        tags=["反转", "烧脑", "悬疑"],
    ),
    DramaTemplate(
        id="gufeng", name="古风虐恋", genre="古风",
        description="古代背景的爱恨纠葛",
        brief="古代王朝背景下，权谋与爱情的纠葛，虐心虐情最终圆满或遗憾",
        tags=["古风", "虐恋", "权谋"],
    ),
]


def list_templates() -> list[dict[str, Any]]:
    return [
        {
            "id": t.id, "name": t.name, "genre": t.genre,
            "description": t.description, "brief": t.brief,
            "default_platform": t.default_platform,
            "target_duration": t.target_duration, "tags": t.tags,
        }
        for t in TEMPLATES
    ]


def get_template(template_id: str) -> DramaTemplate | None:
    for t in TEMPLATES:
        if t.id == template_id:
            return t
    return None