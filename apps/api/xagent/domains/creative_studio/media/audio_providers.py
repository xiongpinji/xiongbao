"""音频/TTS provider：EdgeTTS（免费、免 key）+ 火山 TTS 扩展位。

EdgeTTS 走微软 Edge 大声朗读在线服务，无需 API key，中文音色齐全
（zh-CN-XiaoxiaoNeural / zh-CN-YunxiNeural / zh-CN-YunjianNeural 等）。
同步语义（与 OpenAIImageProvider 一致）：edge-tts 一次性产出 mp3 文件，
submit 直接合成落盘并返回 succeeded/failed，poll 从缓存返回结果。
网络不可用 / 未安装 edge-tts 时 submit 返回 failed 任务（不抛异常），
由调用方按单镜头降级；registry 未注册音频 provider 时整体回退 NullProvider 占位。
VolcanoTTSProvider 为火山引擎语音合成预留的类骨架（待配 key 后补实现）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from uuid import uuid4

from xagent.domains.creative_studio.media.base import (
    GenerationMode,
    GenerationRequest,
    GenerationTask,
    MediaKind,
    ModelCard,
)
from xagent.infra.logging import get_logger

logger = get_logger("xagent.media.audio")

# 常用中文音色（edge-tts 在线音色列表的短剧场景子集）
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
ZH_CN_VOICES: list[tuple[str, str]] = [
    ("zh-CN-XiaoxiaoNeural", "晓晓 · 女声 · 温暖活泼"),
    ("zh-CN-XiaoyiNeural", "晓伊 · 女声 · 轻快甜妹"),
    ("zh-CN-XiaohanNeural", "晓涵 · 女声 · 温柔成熟"),
    ("zh-CN-XiaomoNeural", "晓墨 · 女声 · 沉稳知性"),
    ("zh-CN-XiaoshuangNeural", "晓双 · 女童声"),
    ("zh-CN-YunxiNeural", "云希 · 男声 · 青年"),
    ("zh-CN-YunjianNeural", "云健 · 男声 · 低沉有力（霸总向）"),
    ("zh-CN-YunyangNeural", "云扬 · 男声 · 沉稳播报"),
    ("zh-CN-YunzeNeural", "云泽 · 男声 · 年长沧桑"),
]


def edge_tts_available() -> bool:
    """edge-tts 是否已安装（不探测网络，网络失败在 submit 时降级）。"""
    try:
        import edge_tts  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class EdgeTTSProvider:
    """Edge TTS 配音 provider（免费、免 key，需外网）。

    voice 选取优先级：req.params["voice"] > req.model_id > default_voice。
    params 可透传 rate/volume/pitch（edge-tts 格式，如 "+10%"/"-2Hz"）。
    """

    name: str = "edge_tts"
    default_voice: str = DEFAULT_VOICE
    output_dir: str = "./data/tts"
    supported_kinds: set = field(default_factory=lambda: {MediaKind.audio})
    supported_modes: set = field(default_factory=lambda: {GenerationMode.text_to_speech})
    _results: dict = field(default_factory=dict)

    def _resolve_voice(self, req: GenerationRequest) -> str:
        if req.params and req.params.get("voice"):
            return str(req.params["voice"])
        return req.model_id or self.default_voice

    async def submit(self, req: GenerationRequest) -> GenerationTask:
        text = req.prompt.strip()
        voice = self._resolve_voice(req)
        task_id = f"edge-tts-{abs(hash((text, voice))) % 100000}-{uuid4().hex[:8]}"
        if not text:
            task = GenerationTask(
                task_id=task_id, provider=self.name,
                status="failed", error="配音文本为空",
            )
            self._results[task_id] = task
            return task
        try:
            import edge_tts
        except ImportError:
            task = GenerationTask(
                task_id=task_id, provider=self.name,
                status="failed", error="未安装 edge-tts：pip install edge-tts 后重试",
            )
            self._results[task_id] = task
            return task
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            out_path = os.path.join(self.output_dir, f"{task_id}.mp3")
            # 透传 edge-tts 语音参数（非法值由 edge-tts 侧校验并抛错 -> failed 降级）
            params = req.params or {}
            kwargs = {
                k: str(params[k])
                for k in ("rate", "volume", "pitch")
                if params.get(k)
            }
            communicate = edge_tts.Communicate(text, voice, **kwargs)
            await communicate.save(out_path)
            task = GenerationTask(
                task_id=task_id, provider=self.name, status="succeeded",
                outputs=[out_path], raw={"voice": voice},
            )
        except Exception as exc:  # 网络不可用/音色非法等：优雅降级为 failed，不阻断流程
            logger.warning("edge_tts_submit_failed", error=str(exc), voice=voice)
            task = GenerationTask(
                task_id=task_id, provider=self.name, status="failed", error=str(exc),
            )
        self._results[task.task_id] = task
        return task

    async def poll(self, task_id: str) -> GenerationTask:
        task = self._results.get(task_id)
        if task is None:
            task = GenerationTask(
                task_id=task_id, provider=self.name,
                status="failed", error="任务不存在（可能进程已重启）",
            )
        return task

    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]:
        if kind is not None and kind != MediaKind.audio:
            return []
        return [
            ModelCard(
                model_id=voice_id, name=label, kind=MediaKind.audio,
                modes=[GenerationMode.text_to_speech], provider=self.name,
            )
            for voice_id, label in ZH_CN_VOICES
        ]


@dataclass
class VolcanoTTSProvider:
    """火山引擎语音合成（预留扩展位，类骨架，未接入）。

    接入步骤（待实现）：
      1. settings.media 增加 volcano_tts_app_id / access_token / cluster 配置；
      2. submit 调火山 TTS HTTP/WebSocket 接口合成并落盘音频文件；
      3. registry 按 default_audio_provider == "volcano_tts" 注册本 provider。
    """

    name: str = "volcano_tts"
    app_id: str = ""
    access_token: str = ""
    cluster: str = "volcano_tts"
    default_voice: str = "BV001_streaming"
    supported_kinds: set = field(default_factory=lambda: {MediaKind.audio})
    supported_modes: set = field(default_factory=lambda: {GenerationMode.text_to_speech})

    async def submit(self, req: GenerationRequest) -> GenerationTask:  # noqa: ARG002
        return GenerationTask(
            task_id="volcano-tts-unimplemented", provider=self.name,
            status="failed", error="火山 TTS 尚未接入（预留扩展位）",
        )

    async def poll(self, task_id: str) -> GenerationTask:
        return GenerationTask(
            task_id=task_id, provider=self.name,
            status="failed", error="火山 TTS 尚未接入（预留扩展位）",
        )

    def list_models(self, kind: MediaKind | None = None) -> list[ModelCard]:
        return []
