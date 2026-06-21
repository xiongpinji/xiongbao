"""视频生成 provider：可灵 Kling / 即梦 Jimeng + 通用任务式 HTTP。

视频生成是异步任务式：submit -> task_id；poll -> 轮询状态取产物 URL。
通用 GenericVideoProvider 适配任意「提交+轮询」风格的视频 API（按 endpoint 配置），
KlingProvider / JimengProvider 为预留具体实现骨架（真实签名按各家文档补全）。
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
class GenericVideoProvider:
    """通用任务式视频 provider：适配「提交+轮询」风格 API。

    配置 submit_url / poll_url（{task_id} 占位）+ auth header，即可对接
    可灵 / 即梦 / Runway / Pika 等任意视频生成服务。
    """

    name: str = "generic_video"
    submit_url: str = ""
    poll_url: str = ""  # 含 {task_id} 占位
    api_key: str = ""
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    default_model: str = ""
    supported_kinds: set = field(default_factory=lambda: {MediaKind.video})
    supported_modes: set = field(
        default_factory=lambda: {GenerationMode.text_to_video, GenerationMode.image_to_video}
    )

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {self.auth_header: f"{self.auth_prefix}{self.api_key}"}

    async def submit(self, req: GenerationRequest) -> GenerationTask:
        import httpx

        payload = {
            "model": req.model_id or self.default_model,
            "prompt": req.prompt,
            "negative_prompt": req.negative_prompt,
            "mode": req.mode.value,
            "duration": req.duration_seconds,
            "fps": req.fps,
            "resolution": req.resolution,
            "image": req.reference_images[0] if req.reference_images else None,
            **req.params,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(self.submit_url, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
            # 兼容常见返回字段
            task_id = (
                data.get("task_id")
                or data.get("id")
                or data.get("data", {}).get("task_id", "")
            )
            return GenerationTask(
                task_id=str(task_id), provider=self.name,
                status=data.get("status", "queued"), raw=data,
            )
        except Exception as exc:
            return GenerationTask(
                task_id="video-err", provider=self.name, status="failed", error=str(exc)
            )

    async def poll(self, task_id: str) -> GenerationTask:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    self.poll_url.format(task_id=task_id), headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
            status = data.get("status", "running")
            # 兼容多种产物字段
            outputs = (
                data.get("outputs")
                or data.get("videos")
                or ([data["video_url"]] if data.get("video_url") else [])
            )
            return GenerationTask(
                task_id=task_id, provider=self.name, status=status,
                outputs=outputs, error=data.get("error"), raw=data,
            )
        except Exception as exc:
            return GenerationTask(
                task_id=task_id, provider=self.name, status="failed", error=str(exc)
            )

    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]:
        if kind not in (None, MediaKind.video):
            return []
        return [
            ModelCard(self.default_model or "generic-video", "通用视频模型", MediaKind.video,
                      list(self.supported_modes), self.name, "通用任务式视频生成")
        ]


@dataclass
class KlingProvider(GenericVideoProvider):
    """可灵 Kling 视频生成（预留：真实签名/端点按可灵开放平台文档补全）。"""

    name: str = "kling"
    default_model: str = "kling-v1"

    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]:
        if kind not in (None, MediaKind.video):
            return []
        return [
            ModelCard("kling-v1", "可灵 1.0", MediaKind.video,
                      [GenerationMode.text_to_video, GenerationMode.image_to_video],
                      self.name, "快手可灵视频生成", max_duration_seconds=10,
                      resolutions=["720p", "1080p"]),
            ModelCard("kling-v1-5", "可灵 1.5", MediaKind.video,
                      [GenerationMode.text_to_video, GenerationMode.image_to_video],
                      self.name, "快手可灵 1.5", max_duration_seconds=10),
        ]


@dataclass
class JimengProvider(GenericVideoProvider):
    """即梦 Jimeng 视频生成（预留：字节即梦 API）。"""

    name: str = "jimeng"
    default_model: str = "jimeng-video-1"

    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]:
        if kind not in (None, MediaKind.video):
            return []
        return [
            ModelCard("jimeng-video-1", "即梦视频", MediaKind.video,
                      [GenerationMode.text_to_video, GenerationMode.image_to_video],
                      self.name, "字节即梦视频生成", max_duration_seconds=12),
        ]


@dataclass
class VolcanoArkVideoProvider:
    """火山方舟 Seedance 视频生成（已验证真实可用）。

    API: POST /api/v3/contents/generations/tasks（提交）
         GET  /api/v3/contents/generations/tasks/{task_id}（轮询）
    返回 content.video_url。
    """

    name: str = "volcano_ark"
    api_key: str = ""
    base_url: str = "https://ark.cn-beijing.volces.com"
    default_model: str = "doubao-seedance-1-5-pro-251215"
    supported_kinds: set = field(default_factory=lambda: {MediaKind.video})
    supported_modes: set = field(
        default_factory=lambda: {GenerationMode.text_to_video, GenerationMode.image_to_video}
    )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def submit(self, req: GenerationRequest) -> GenerationTask:
        import httpx

        content = [{"type": "text", "text": req.prompt}]
        # 图生视频：加图片输入
        if req.mode == GenerationMode.image_to_video and req.reference_images:
            content.append({"type": "image_url", "image_url": {"url": req.reference_images[0]}})

        payload = {
            "model": req.model_id or self.default_model,
            "content": content,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v3/contents/generations/tasks",
                    json=payload, headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
            task_id = data.get("id", "")
            return GenerationTask(
                task_id=task_id, provider=self.name,
                status="queued", raw=data,
            )
        except Exception as exc:
            return GenerationTask(
                task_id="volcano-err", provider=self.name,
                status="failed", error=str(exc),
            )

    async def poll(self, task_id: str) -> GenerationTask:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.base_url}/api/v3/contents/generations/tasks/{task_id}",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
            status = data.get("status", "running")
            # 火山方舟状态: queued/running/succeeded/failed
            outputs = []
            content = data.get("content") or {}
            if content.get("video_url"):
                outputs.append(content["video_url"])
            elif content.get("image_url"):
                outputs.append(content["image_url"])
            return GenerationTask(
                task_id=task_id, provider=self.name, status=status,
                outputs=outputs, error=data.get("error"), raw=data,
            )
        except Exception as exc:
            return GenerationTask(
                task_id=task_id, provider=self.name,
                status="failed", error=str(exc),
            )

    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]:
        if kind not in (None, MediaKind.video):
            return []
        return [
            ModelCard(
                "doubao-seedance-1-5-pro-251215", "豆包 Seedance 1.5 Pro",
                MediaKind.video,
                [GenerationMode.text_to_video, GenerationMode.image_to_video],
                self.name, "火山方舟视频生成（已验证）", max_duration_seconds=10,
            ),
            ModelCard(
                "doubao-seedance-2-0-260128", "豆包 Seedance 2.0",
                MediaKind.video,
                [GenerationMode.text_to_video, GenerationMode.image_to_video],
                self.name, "火山方舟最新视频生成", max_duration_seconds=10,
            ),
        ]
