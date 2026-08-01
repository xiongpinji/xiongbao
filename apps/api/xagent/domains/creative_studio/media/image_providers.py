"""图像生成 provider：OpenAI 兼容（gpt-image-2 / DALL·E-3）+ Pollinations(免费) + 通用 HTTP。

gpt-image-2 / DALL·E 是同步返回（非任务轮询）：submit 直接拿结果，poll 返回缓存。
文生图 + 图生图（edits）均支持。通过 OpenAI 兼容端点，可指向 OpenAI 官方或代理。
Pollinations.ai 免费文生图，无需 API key。
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

    def _endpoint(self, path: str) -> str:
        """拼接 base_url + path，自动去末尾斜杠避免双斜杠。"""
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _build_payload(self, req: GenerationRequest, *, size: str) -> dict:
        """构造请求 payload，把节点 settings 透传的 params 挑 OpenAI 兼容字段塞进去。

        OpenAI images/generations 支持: model/prompt/n/size/quality/style/response_format/seed
        节点 settings 透传过来的 params 里可能含: sampler/scheduler/steps/cfg/batch/strategy 等，
        只挑 OpenAI 兼容字段，其余忽略。
        """
        params = dict(req.params or {})
        payload: dict = {
            "model": req.model_id or self.default_model,
            "prompt": req.prompt,
            "size": size,
        }
        # n: 批量（来自 settings.batch 透传）
        batch = params.get("batch")
        if batch is not None:
            try:
                n = int(batch)
                if n > 0:
                    payload["n"] = n
            except (TypeError, ValueError):
                pass
        # quality: gpt-image-2 支持 "low"|"medium"|"high"|"auto"
        quality = params.get("quality")
        if quality:
            payload["quality"] = str(quality)
        # style: dall-e-3 支持 "vivid"|"natural"
        style = params.get("style")
        if style:
            payload["style"] = str(style)
        # response_format: "url"|"b64_json"
        response_format = params.get("response_format")
        if response_format:
            payload["response_format"] = str(response_format)
        # seed: 部分中转站支持
        if req.seed is not None:
            payload["seed"] = int(req.seed)
        return payload

    async def submit(self, req: GenerationRequest) -> GenerationTask:
        import httpx

        size = req.resolution or "1024x1024"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                if req.mode == GenerationMode.image_to_image and req.reference_images:
                    # 图生图：images/edits（需上传参考图，这里传 URL/base64 由调用方准备）
                    payload = self._build_payload(req, size=size)
                    payload["image"] = req.reference_images[0]
                    resp = await client.post(
                        self._endpoint("/images/edits"),
                        headers=headers,
                        json=payload,
                    )
                else:
                    payload = self._build_payload(req, size=size)
                    if "n" not in payload:
                        payload["n"] = 1
                    resp = await client.post(
                        self._endpoint("/images/generations"),
                        headers=headers,
                        json=payload,
                    )
                resp.raise_for_status()
                data = resp.json()
            outputs = []
            for item in data.get("data", []):
                url = item.get("url")
                if url:
                    outputs.append(url)
                elif item.get("b64_json"):
                    outputs.append(f"data:image/png;base64,{item['b64_json']}")
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


@dataclass
class PollinationsProvider:
    """免费文生图（pollinations.ai），无需 API key。

    通过 URL 生成图像：https://image.pollinations.ai/prompt/{prompt}
    支持 width/height/seed/nologo 参数。
    """

    name: str = "pollinations"
    base_url: str = "https://image.pollinations.ai"
    supported_kinds: set = field(default_factory=lambda: {MediaKind.image})
    supported_modes: set = field(default_factory=lambda: {GenerationMode.text_to_image})
    _results: dict = field(default_factory=dict)

    async def submit(self, req: GenerationRequest) -> GenerationTask:
        import uuid
        from urllib.parse import quote

        try:
            # 解析分辨率
            width, height = 1024, 1024
            if req.resolution:
                parts = req.resolution.lower().split("x")
                if len(parts) == 2:
                    width, height = int(parts[0]), int(parts[1])

            params = f"width={width}&height={height}&nologo=true"
            if req.seed is not None:
                params += f"&seed={req.seed}"
            # 添加负面提示词
            if req.negative_prompt:
                params += f"&negative={quote(req.negative_prompt)}"

            image_url = f"{self.base_url}/prompt/{quote(req.prompt)}?{params}"

            # 验证 URL 可访问（HEAD 请求）
            import httpx

            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                resp = await client.get(image_url, headers={"Accept": "image/*"})
                if resp.status_code == 200 and len(resp.content) > 1000:
                    # 图片生成成功，保存到本地
                    import os
                    out_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(
                            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        ))),
                        "data", "storage", "images",
                    )
                    os.makedirs(out_dir, exist_ok=True)
                    fname = f"{uuid.uuid4().hex[:12]}.png"
                    fpath = os.path.join(out_dir, fname)
                    with open(fpath, "wb") as f:
                        f.write(resp.content)
                    outputs = [f"local://images/{fname}"]
                    task_id = f"pollinations-{uuid.uuid4().hex[:8]}"
                    task = GenerationTask(
                        task_id=task_id, provider=self.name,
                        status="succeeded", outputs=outputs,
                    )
                else:
                    # 返回 URL 作为产物（用户可直接访问）
                    task_id = f"pollinations-{uuid.uuid4().hex[:8]}"
                    task = GenerationTask(
                        task_id=task_id, provider=self.name,
                        status="succeeded", outputs=[image_url],
                    )
        except Exception as exc:
            task = GenerationTask(
                task_id="pollinations-err", provider=self.name,
                status="failed", error=f"{type(exc).__name__}: {exc}",
            )
        self._results[task.task_id] = task
        return task

    async def poll(self, task_id: str) -> GenerationTask:
        return self._results.get(
            task_id, GenerationTask(task_id=task_id, provider=self.name,
                                    status="failed", error="未知任务")
        )

    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]:
        if kind not in (None, MediaKind.image):
            return []
        return [
            ModelCard(
                "pollinations-flux", "免费文生图 (Pollinations)", MediaKind.image,
                [GenerationMode.text_to_image], self.name,
                "免费 AI 文生图，无需 API key，基于 FLUX 模型",
                resolutions=["1024x1024", "1024x1536", "1536x1024", "720x1280"],
            ),
        ]
