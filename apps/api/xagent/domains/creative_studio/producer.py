"""短剧制作人：用 LLM 从 brief 生成结构化故事板。

DI：注入 llm_caller（默认走 adapters.llm），LLM 不可用/解析失败时回退确定性
模板，保证流程不中断（沿用旧仓 producer 的「出保底」思想）。
"""

from __future__ import annotations

import json
from typing import Any

from xagent.adapters.llm import LLMClient, Message, get_llm_client
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
)


def _safe_json(text: str) -> Any:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j == -1 or j <= i:
        return None
    try:
        return json.loads(text[i : j + 1])
    except Exception:
        return None


_SYSTEM = """你是短剧分镜师。根据用户的一句话 brief 生成结构化故事板 JSON。
字段：title, genre, characters[{name,role,appearance,personality}],
scenes[{location,time_of_day,description}], shots[{duration_seconds,scene,
characters,plot_purpose,camera{shot_size,angle,movement},lighting{style,mood},
dialogue,action,subtitle}]。
要求：3-8 个镜头；总时长接近目标；台词与字幕一致。只输出 JSON。"""


def _fill_continuity_refs(sb: Storyboard) -> None:
    """分镜阶段记录 ShotContinuity 引用，供一致性管理器/图像生成消费。

    按名字把 shot.characters / shot.scene 解析为 character_id / scene_id，
    style_ref 记录题材风格 token。仅填充空字段，不覆盖已有值。
    """
    chars_by_name = {c.name: c for c in sb.characters if c.name}
    scenes_by_loc = {s.location: s for s in sb.scenes if s.location}
    for shot in sb.shots:
        if not shot.continuity.character_ref:
            ids = [
                chars_by_name[n].character_id
                for n in shot.characters
                if n in chars_by_name
            ]
            if ids:
                shot.continuity.character_ref = ";".join(ids)
        if not shot.continuity.scene_ref and shot.scene in scenes_by_loc:
            shot.continuity.scene_ref = scenes_by_loc[shot.scene].scene_id
        if not shot.continuity.style_ref:
            shot.continuity.style_ref = sb.genre or "default"


async def generate_storyboard(
    brief: str,
    *,
    genre: str = "逆袭",
    platform: str = "抖音",
    target_duration_seconds: float = 60.0,
    llm: LLMClient | None = None,
) -> Storyboard:
    """用 LLM 生成故事板；失败回退确定性模板。"""
    llm = llm or get_llm_client()
    user = json.dumps(
        {
            "brief": brief,
            "genre": genre,
            "platform": platform,
            "target_duration_seconds": target_duration_seconds,
            "aspect_ratio": "9:16",
        },
        ensure_ascii=False,
    )
    try:
        resp = await llm.complete(
            [Message(role="system", content=_SYSTEM), Message(role="user", content=user)],
            temperature=0.8,
        )
        data = _safe_json(resp.content)
        if isinstance(data, dict) and data.get("shots"):
            return _from_llm_dict(data, brief, genre, platform, target_duration_seconds)
    except Exception:  # noqa: S110  LLM 失败走保底模板
        pass
    return _fallback_storyboard(brief, genre, platform, target_duration_seconds)


def _from_llm_dict(
    data: dict[str, Any],
    brief: str,
    genre: str,
    platform: str,
    target_duration_seconds: float,
) -> Storyboard:
    chars = [
        CharacterCard(
            name=c.get("name", ""),
            role=c.get("role", ""),
            appearance=c.get("appearance", ""),
            personality=c.get("personality", ""),
        )
        for c in data.get("characters", [])
    ]
    scenes = [
        SceneCard(
            location=s.get("location", ""),
            time_of_day=s.get("time_of_day", ""),
            description=s.get("description", ""),
        )
        for s in data.get("scenes", [])
    ]
    shots = [
        Shot(
            duration_seconds=float(sh.get("duration_seconds", 4)),
            scene=sh.get("scene", ""),
            characters=sh.get("characters", []),
            plot_purpose=sh.get("plot_purpose", ""),
            camera=CameraSpec(**{k: sh.get("camera", {}).get(k, "") for k in (
                "shot_size", "angle", "movement", "lens", "focus", "composition"
            ) if sh.get("camera", {}).get(k)} or {}),
            lighting=LightingSpec(**{k: sh.get("lighting", {}).get(k, "") for k in (
                "style", "key_light", "fill_light", "back_light",
                "contrast", "color_temperature", "mood",
            ) if sh.get("lighting", {}).get(k)} or {}),
            dialogue=sh.get("dialogue", ""),
            action=sh.get("action", ""),
            subtitle=sh.get("subtitle", ""),
            image_prompt=sh.get("image_prompt", ""),
            video_prompt=sh.get("video_prompt", ""),
            continuity=ShotContinuity(),
        )
        for sh in data.get("shots", [])
    ]
    sb = Storyboard(
        title=data.get("title", brief[:20]),
        brief=brief,
        genre=genre,
        platform=platform,
        aspect_ratio=AspectRatio.VERTICAL,
        target_duration_seconds=target_duration_seconds,
        characters=chars,
        scenes=scenes,
        shots=shots,
        status=StoryboardStatus.SCRIPTED,
    )
    _fill_continuity_refs(sb)
    return sb


def _fallback_storyboard(
    brief: str,
    genre: str,
    platform: str,
    target_duration_seconds: float,
) -> Storyboard:
    """LLM 不可用时的确定性保底故事板。"""
    n_shots = max(3, min(8, int(target_duration_seconds // 8)))
    shots = [
        Shot(
            duration_seconds=target_duration_seconds / n_shots,
            scene="主场景",
            characters=["主角"],
            plot_purpose=["引入", "冲突", "高潮", "反转", "收尾"][min(i, 4)],
            camera=CameraSpec(shot_size="medium", movement="static"),
            lighting=LightingSpec(style="natural", mood="neutral"),
            dialogue="" if i else f"{genre}开场",
            subtitle="" if i else f"{genre}开场",
            continuity=ShotContinuity(),
        )
        for i in range(n_shots)
    ]
    sb = Storyboard(
        title=brief[:20],
        brief=brief,
        genre=genre,
        platform=platform,
        target_duration_seconds=target_duration_seconds,
        characters=[CharacterCard(name="主角", role=genre)],
        scenes=[SceneCard(location="主场景", description=brief)],
        shots=shots,
        status=StoryboardStatus.DRAFT,
    )
    _fill_continuity_refs(sb)
    return sb
