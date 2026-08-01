"""provider 注册表 + 工厂。

据 settings 注册图像/视频 provider；image/video 各有默认 provider。
未配 key 时回退 NullProvider（占位产物，流程不中断）。
对外暴露 get(kind)、list_models()、generate()（submit+轮询封装）。
"""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache

from xagent.domains.creative_studio.media.base import (
    GenerationRequest,
    GenerationTask,
    MediaKind,
    MediaProvider,
    ModelCard,
    NullProvider,
)
from xagent.infra.settings import get_settings


class MediaProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[MediaKind, MediaProvider] = {}
        self._null = NullProvider()
        self._all: list[MediaProvider] = [self._null]
        # task_id -> (kind, provider name) 用于轮询时反查
        self._task_kinds: dict[str, MediaKind] = {}

    def register(self, kind: MediaKind, provider: MediaProvider) -> None:
        self._providers[kind] = provider
        if provider not in self._all:
            self._all.append(provider)

    def get(self, kind: MediaKind) -> MediaProvider:
        return self._providers.get(kind, self._null)

    @property
    def null(self) -> MediaProvider:
        return self._null

    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]:
        cards: list[ModelCard] = []
        for p in self._all:
            cards.extend(p.list_models(kind))
        return cards

    def remember_task(self, task: GenerationTask, kind: MediaKind) -> None:
        if task.task_id:
            self._task_kinds[task.task_id] = kind

    def kind_of(self, task_id: str) -> MediaKind | None:
        return self._task_kinds.get(task_id)

    async def poll_task(self, task_id: str) -> GenerationTask | None:
        kind = self._task_kinds.get(task_id)
        if kind is None:
            return None
        provider = self.get(kind)
        return await provider.poll(task_id)

    async def generate(self, req: GenerationRequest, *, wait: bool = True) -> GenerationTask:
        """提交生成任务；wait=True 时轮询直到完成或超时。"""
        provider = self.get(req.kind)
        task = await provider.submit(req)
        self.remember_task(task, req.kind)
        if not wait or task.status in ("succeeded", "failed"):
            return task
        cfg = get_settings().media
        elapsed = 0
        while elapsed < cfg.task_timeout_seconds:
            await asyncio.sleep(cfg.poll_interval_seconds)
            elapsed += cfg.poll_interval_seconds
            task = await provider.poll(task.task_id)
            if task.status in ("succeeded", "failed"):
                self.remember_task(task, req.kind)
                return task
        task.status = "failed"
        task.error = "生成超时"
        self.remember_task(task, req.kind)
        return task


def _build_registry() -> MediaProviderRegistry:
    registry = MediaProviderRegistry()
    cfg = get_settings().media

    # 图像 provider
    if cfg.default_image_provider == "openai" and (
        cfg.openai_image_api_key or os.environ.get("OPENAI_API_KEY")
    ):
        from xagent.domains.creative_studio.media.image_providers import OpenAIImageProvider

        registry.register(
            MediaKind.image,
            OpenAIImageProvider(
                api_key=cfg.openai_image_api_key or os.environ.get("OPENAI_API_KEY", ""),
                base_url=cfg.openai_image_base_url,
                default_model=cfg.openai_image_model,
            ),
        )
    else:
        # 无 OpenAI key 时使用免费 Pollinations 文生图
        from xagent.domains.creative_studio.media.image_providers import PollinationsProvider

        registry.register(MediaKind.image, PollinationsProvider())

    # 视频 provider
    from xagent.domains.creative_studio.media.video_providers import (
        GenericVideoProvider,
        JimengProvider,
        KlingProvider,
        VolcanoArkVideoProvider,
    )

    vp = cfg.default_video_provider
    if vp == "volcano_ark" and cfg.volcano_ark_api_key:
        registry.register(MediaKind.video, VolcanoArkVideoProvider(
            api_key=cfg.volcano_ark_api_key,
            base_url=cfg.volcano_ark_base_url,
            default_model=cfg.volcano_ark_model,
        ))
    elif vp == "kling" and cfg.kling_api_key:
        registry.register(MediaKind.video, KlingProvider(
            api_key=cfg.kling_api_key, submit_url=cfg.kling_submit_url,
            poll_url=cfg.kling_poll_url))
    elif vp == "jimeng" and cfg.jimeng_api_key:
        registry.register(MediaKind.video, JimengProvider(
            api_key=cfg.jimeng_api_key, submit_url=cfg.jimeng_submit_url,
            poll_url=cfg.jimeng_poll_url))
    elif vp == "generic" and cfg.generic_video_submit_url:
        registry.register(MediaKind.video, GenericVideoProvider(
            api_key=cfg.generic_video_api_key, submit_url=cfg.generic_video_submit_url,
            poll_url=cfg.generic_video_poll_url, default_model=cfg.generic_video_model))

    return registry


@lru_cache
def get_media_registry() -> MediaProviderRegistry:
    return _build_registry()


def reset_media_registry() -> None:
    get_media_registry.cache_clear()
