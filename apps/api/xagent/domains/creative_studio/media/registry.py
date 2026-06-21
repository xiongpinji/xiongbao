"""provider 注册表 + 工厂。lite 默认 NullProvider；配置 key 后启用云 provider。"""

from __future__ import annotations

import os
from functools import lru_cache

from xagent.domains.creative_studio.media.base import (
    MediaKind,
    MediaProvider,
    NullProvider,
)


class MediaProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[MediaKind, MediaProvider] = {}
        self._default = NullProvider()

    def register(self, kind: MediaKind, provider: MediaProvider) -> None:
        self._providers[kind] = provider

    def get(self, kind: MediaKind) -> MediaProvider:
        return self._providers.get(kind, self._default)

    @property
    def default(self) -> MediaProvider:
        return self._default


@lru_cache
def get_media_registry() -> MediaProviderRegistry:
    registry = MediaProviderRegistry()
    # 配置了 LibLib key 则注册云 provider（Phase 3 后段接入真实 API）
    if os.environ.get("XAGENT_MEDIA__LIBLIB_ACCESS_KEY"):
        from xagent.domains.creative_studio.media.liblib_provider import LiblibProvider

        lib = LiblibProvider(
            base_url=os.environ.get("XAGENT_MEDIA__LIBLIB_BASE_URL", ""),
            access_key=os.environ["XAGENT_MEDIA__LIBLIB_ACCESS_KEY"],
            secret_key=os.environ.get("XAGENT_MEDIA__LIBLIB_SECRET_KEY", ""),
        )
        registry.register(MediaKind.image, lib)
        registry.register(MediaKind.video, lib)
    return registry


def reset_media_registry() -> None:
    get_media_registry.cache_clear()
