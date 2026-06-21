"""LibLib 云生成 provider（参考 LibLib/LibTV 开放平台 API 模式）。

submit -> 提交生成任务，拿 task_id；poll -> 轮询任务状态取产物 URL。
真实端点/签名需对接 LibLib 开放平台文档；此处为可运行骨架，配置 key 后即启用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from xagent.domains.creative_studio.media.base import (
    GenerationRequest,
    GenerationTask,
    MediaKind,
    ModelCard,
)


@dataclass
class LiblibProvider:
    name: str = "liblib"
    base_url: str = ""
    access_key: str = ""
    secret_key: str = ""
    supported_kinds: set[MediaKind] = field(
        default_factory=lambda: {MediaKind.image, MediaKind.video}
    )

    def _headers(self) -> dict[str, str]:
        # 真实签名按 LibLib 开放平台规范（HMAC/时间戳）补全
        return {"X-Access-Key": self.access_key}

    async def submit(self, req: GenerationRequest) -> GenerationTask:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/generations",
                json={
                    "kind": req.kind.value,
                    "prompt": req.prompt,
                    "model_id": req.model_id,
                    "loras": req.loras,
                    "reference_images": req.reference_images,
                    "params": req.params,
                },
                headers=self._headers(),
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        return GenerationTask(task_id=data["task_id"], status=data.get("status", "queued"))

    async def poll(self, task_id: str) -> GenerationTask:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/generations/{task_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        return GenerationTask(
            task_id=task_id,
            status=data.get("status", "running"),
            outputs=data.get("outputs", []),
            error=data.get("error"),
        )

    def list_models(self, kind: MediaKind) -> list[ModelCard]:
        # 真实实现调 /api/v1/models；此处返回空，由上层缓存或前端选择
        return []
