"""角色/场景一致性管理：基准参考图生成/缓存 + 关键帧参考图注入。

背景：ShotContinuity 契约此前未被使用，关键帧生成未注入角色参考图，
跨镜头角色一致性无保障。本模块补齐这条链路：

  1. 分镜阶段（producer._fill_continuity_refs）在 ShotContinuity 记录
     character_ref / scene_ref / style_ref 引用；
  2. ConsistencyManager 为每个 CharacterCard / SceneCard 生成基准参考图，
     按内容指纹缓存于租户目录（local FS 约定：
     <storage_root>/<tenant>/consistency/index.json），同指纹直接复用，
     不重复调用图像生成；
  3. 关键帧生成前调用 apply_to_shot / generate_keyframe_image：
     解析镜头涉及的角色/场景 → 产出 reference_images + prompt 一致性
     修饰词，写回 shot.continuity（贯穿记录），由图像生成消费。

向后兼容：故事板无角色卡/场景卡时产出为空，prompt 原样返回，
关键帧仍为纯文生图，行为与现状一致。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xagent.domains.creative_studio.media.registry import MediaProviderRegistry

from xagent.domains.creative_studio.media.base import (
    GenerationMode,
    GenerationRequest,
    GenerationTask,
    MediaKind,
    MediaProvider,
)
from xagent.domains.creative_studio.storyboard import (
    CharacterCard,
    SceneCard,
    Shot,
    Storyboard,
)
from xagent.infra.logging import get_logger

logger = get_logger("xagent.creative.consistency")


@dataclass
class ShotConsistency:
    """单个镜头的一致性解析结果。"""

    reference_images: list[str] = field(default_factory=list)
    prompt_modifier: str = ""
    characters: list[CharacterCard] = field(default_factory=list)
    scene: SceneCard | None = None


def _safe_tenant(tenant_id: str) -> str:
    """与 adapters.storage.base 一致的 tenant 目录名安全化。"""
    return "".join(c for c in tenant_id if c.isalnum() or c in "-_") or "default"


def _fingerprint(payload: dict) -> str:
    """卡片内容指纹：内容变则基准图重生成，内容不变则缓存复用。"""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _character_base_prompt(card: CharacterCard) -> str:
    parts = [card.name, card.role, card.appearance, card.personality]
    desc = "，".join(p for p in parts if p)
    return f"{desc}，角色设定基准图，全身像，正面，纯色背景，影视级写实风格"


def _scene_base_prompt(card: SceneCard) -> str:
    parts = [card.location, card.time_of_day, card.description]
    desc = "，".join(p for p in parts if p)
    return f"{desc}，场景概念基准图，无人物，影视级写实风格"


def build_prompt_modifier(
    characters: list[CharacterCard],
    scene: SceneCard | None,
    style_ref: str = "",
) -> str:
    """组装 prompt 一致性修饰词；无角色且无场景时返回空串（向后兼容）。"""
    segments: list[str] = []
    for c in characters:
        parts = [p for p in (c.role, c.appearance) if p]
        segments.append(f"{c.name}（{'，'.join(parts)}）" if parts else c.name)
    prefix = ""
    if segments:
        prefix += "角色一致性：" + "；".join(segments)
    if scene is not None:
        scene_desc = "，".join(
            p for p in (scene.time_of_day, scene.description) if p
        )
        scene_seg = scene.location + (f"（{scene_desc}）" if scene_desc else "")
        prefix += ("；" if prefix else "") + f"场景一致性：{scene_seg}"
    if not prefix:
        return ""
    style = f"，{style_ref}题材" if style_ref else ""
    return f"{prefix}；保持跨镜头角色外观与场景一致{style}，竖屏短剧电影感"


class ConsistencyManager:
    """角色/场景基准参考图管理器（按租户缓存）。"""

    def __init__(
        self,
        *,
        tenant_id: str = "default",
        provider: MediaProvider | None = None,
        cache_dir: Path | str | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self._provider = provider
        if cache_dir is None:
            root = os.environ.get("XAGENT_STORAGE__LOCAL_ROOT", "./data/storage")
            cache_dir = Path(root) / _safe_tenant(tenant_id) / "consistency"
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, str] = self._load_index()

    # ---- 缓存 ----------------------------------------------------------

    @property
    def _index_path(self) -> Path:
        return self._cache_dir / "index.json"

    def _load_index(self) -> dict[str, str]:
        try:
            if self._index_path.exists():
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
        except Exception as exc:  # noqa: BLE001  索引损坏则重建，不阻断流程
            logger.warning("consistency_index_load_failed", error=str(exc))
        return {}

    def _save_index(self) -> None:
        try:
            self._index_path.write_text(
                json.dumps(self._index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001  缓存写失败不阻断生成
            logger.warning("consistency_index_save_failed", error=str(exc))

    def _get_provider(self) -> MediaProvider:
        if self._provider is None:
            from xagent.domains.creative_studio.media import get_media_registry

            self._provider = get_media_registry().get(MediaKind.image)
        return self._provider

    # ---- 基准参考图 ------------------------------------------------------

    async def ensure_base_image(
        self,
        kind: str,
        card: CharacterCard | SceneCard,
    ) -> str:
        """生成（或复用缓存的）基准参考图，返回图 URL；失败返回空串。

        kind: "character" | "scene"。按卡片内容指纹缓存于租户目录。
        """
        if isinstance(card, CharacterCard):
            key = f"{kind}:{card.character_id}:{_fingerprint(card.model_dump())}"
            prompt = _character_base_prompt(card)
        else:
            key = f"{kind}:{card.scene_id}:{_fingerprint(card.model_dump())}"
            prompt = _scene_base_prompt(card)
        cached = self._index.get(key)
        if cached:
            return cached
        try:
            task = await self._get_provider().submit(
                GenerationRequest(
                    kind=MediaKind.image,
                    prompt=prompt,
                    mode=GenerationMode.text_to_image,
                )
            )
        except Exception as exc:  # noqa: BLE001  基准图失败降级：不注入参考图
            logger.warning(
                "consistency_base_image_failed", key=key, error=str(exc)
            )
            return ""
        if task.status != "succeeded" or not task.outputs:
            logger.warning(
                "consistency_base_image_failed", key=key, error=task.error
            )
            return ""
        url = task.outputs[0]
        self._index[key] = url
        self._save_index()
        return url

    # ---- 镜头解析 --------------------------------------------------------

    def resolve_shot(
        self, sb: Storyboard, shot: Shot
    ) -> tuple[list[CharacterCard], SceneCard | None]:
        """解析镜头涉及的角色卡/场景卡。

        优先按 ShotContinuity 引用（character_id/scene_id）解析，
        再按 shot.characters（名字）/shot.scene（location）兜底。
        """
        by_id = {c.character_id: c for c in sb.characters}
        by_name = {c.name: c for c in sb.characters if c.name}
        characters: list[CharacterCard] = []
        seen: set[str] = set()
        tokens = [
            t.strip()
            for t in shot.continuity.character_ref.replace(",", ";").split(";")
            if t.strip()
        ]
        tokens.extend(shot.characters)
        for token in tokens:
            card = by_id.get(token) or by_name.get(token)
            if card is not None and card.character_id not in seen:
                seen.add(card.character_id)
                characters.append(card)

        scene: SceneCard | None = None
        scenes_by_id = {s.scene_id: s for s in sb.scenes}
        scenes_by_loc = {s.location: s for s in sb.scenes if s.location}
        for token in (shot.continuity.scene_ref, shot.scene):
            if token and scene is None:
                scene = scenes_by_id.get(token) or scenes_by_loc.get(token)
        return characters, scene

    # ---- 关键帧注入 ------------------------------------------------------

    async def apply_to_shot(self, sb: Storyboard, shot: Shot) -> ShotConsistency:
        """解析镜头一致性并把产物写回 shot.continuity（贯穿记录）。"""
        characters, scene = self.resolve_shot(sb, shot)
        result = ShotConsistency(characters=characters, scene=scene)
        if not characters and scene is None:
            return result

        refs: list[str] = []
        for card in characters:
            url = await self.ensure_base_image("character", card)
            if url:
                refs.append(url)
        if scene is not None:
            url = await self.ensure_base_image("scene", scene)
            if url:
                refs.append(url)
        result.reference_images = refs
        result.prompt_modifier = build_prompt_modifier(
            characters, scene, shot.continuity.style_ref
        )
        # 写回 continuity，图像生成/下游直接消费
        shot.continuity.reference_images = list(refs)
        shot.continuity.prompt_modifier = result.prompt_modifier
        return result

    def apply_to_prompt(self, base_prompt: str, prompt_modifier: str) -> str:
        """把一致性修饰词拼到基础 prompt 后；修饰词为空则原样返回。"""
        if not prompt_modifier:
            return base_prompt
        return f"{base_prompt}，{prompt_modifier}" if base_prompt else prompt_modifier

    async def prepare_keyframe(
        self, sb: Storyboard, shot: Shot, base_prompt: str
    ) -> tuple[str, list[str]]:
        """关键帧生成前置：返回 (prompt, reference_images)。"""
        result = await self.apply_to_shot(sb, shot)
        prompt = self.apply_to_prompt(base_prompt, result.prompt_modifier)
        return prompt, result.reference_images


async def generate_keyframe_image(
    sb: Storyboard,
    shot: Shot,
    *,
    prompt: str,
    tenant_id: str = "default",
    manager: ConsistencyManager | None = None,
    registry: MediaProviderRegistry | None = None,
) -> GenerationTask:
    """生成单镜头关键帧图（消费 ShotContinuity，注入角色/场景参考图）。

    pipeline 关键帧步骤的一行替换入口：
    有一致性参考图时走 image_to_image，否则保持 text_to_image（向后兼容）。
    """
    manager = manager or ConsistencyManager(tenant_id=tenant_id)
    final_prompt, refs = await manager.prepare_keyframe(sb, shot, prompt)
    if registry is None:
        from xagent.domains.creative_studio.media import get_media_registry

        registry = get_media_registry()
    return await registry.generate(
        GenerationRequest(
            kind=MediaKind.image,
            prompt=final_prompt,
            mode=(
                GenerationMode.image_to_image
                if refs
                else GenerationMode.text_to_image
            ),
            reference_images=refs,
        ),
        wait=True,
    )
