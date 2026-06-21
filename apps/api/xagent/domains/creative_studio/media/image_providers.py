"""图像生成 provider：OpenAI 兼容（gpt-image-2 / DALL·E-3）+ 通用 HTTP。

gpt-image-2 / DALL·E 是同步返回（非任务轮询）：submit 直接拿结果，poll 返回缓存。
文生图 + 图生图（edits）均支持。通过 OpenAI 兼容端点，可指向 OpenAI 官方或代理。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from xagent.domains.creative_studio.media.base import (
    GenerationMode,
    GenerationRequest,
    GenerationTask,
    MediaKind,
    ModelCard,
)


@dataclass
class OpenAIImageProvider:
    """gpt-image-2 / DALL·E-3 图像生成（OpenAI 兼容）。"""

    name: str = "openai_image"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    default_model: str = "gpt-image-2"
    supported_kinds: set = field(default_factory=lambda: {MediaKind.image})
    supported_modes: set = field(
        default_factory=lambda: {GenerationMode.text_to_image, GenerationMode.image_to_image}
    )
    _results: dict = field(default_factory=dict)

    async def submit(self, req: GenerationRequest) -> GenerationTask:
        import httpx

        model = req.model_id or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}"}
        size = req.resolution or "1024x1024"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                if req.mode == GenerationMode.image_to_image and req.reference_images:
                    # 图生图：images/edits（需上传参考图，这里传 URL/base64 由调用方准备）
                    resp = await client.post(
                        f"{self.base_url}/images/edits",
                        headers=headers,
                        json={
                            "model": model,
                            "prompt": req.prompt,
                            "image": req.reference_images[0],
                            "size": size,
                        },
                    )
                else:
                    resp = await client.post(
                        f"{self.base_url}/images/generations",
                        headers=headers,
                        json={"model": model, "prompt": req.prompt, "size": size, "n": 1},
                    )
                resp.raise_for_status()
                data = resp.json()
            outputs = [
                item.get("url") or f"data:image/png;base64,{item.get('b64_json', '')}"
                for item in data.get("data", [])
            ]
            task = GenerationTask(
                task_id=f"openai-img-{abs(hash(req.prompt)) % 100000}",
                provider=self.name, status="succeeded", outputs=outputs, raw=data,
            )
        except Exception as exc:
            task = GenerationTask(
                task_id="openai-img-err", provider=self.name, status="failed", error=str(exc)
            )
        self._results[task.task_id] = task
        return task

    async def poll(self, task_id: str) -> GenerationTask:
        # 同步模型：submit 已拿结果，poll 返回缓存
        return self._results.get(
            task_id, GenerationTask(task_id=task_id, provider=self.name, status="failed",
                                    error="未知任务")
        )

    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]:
        if kind not in (None, MediaKind.image):
            return []
        return [
            ModelCard("gpt-image-2", "GPT Image 2", MediaKind.image,
                      [GenerationMode.text_to_image, GenerationMode.image_to_image],
                      self.name, "OpenAI 文生图/图生图",
                      resolutions=["1024x1024", "1536x1024", "1024x1536"]),
            ModelCard("dall-e-3", "DALL·E 3", MediaKind.image,
                      [GenerationMode.text_to_image], self.name, "OpenAI 文生图",
                      resolutions=["1024x1024", "1792x1024", "1024x1792"]),
        ]
