"""STT/TTS 抽象 + stub 降级 + 真实实现接入点。

faster-whisper（MIT）：STT，比官方 whisper 快 4x。
Piper（MIT）：本地 TTS，轻量。两者未装时 stub。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, runtime_checkable


@dataclass
class STTResult:
    ok: bool
    text: str = ""
    segments: list[dict] | None = None
    error: str | None = None


@dataclass
class TTSResult:
    ok: bool
    audio_path: str = ""
    error: str | None = None


@runtime_checkable
class STTEngine(Protocol):
    async def transcribe(self, audio_path: str, *, language: str = "zh") -> STTResult: ...


@runtime_checkable
class TTSEngine(Protocol):
    async def synthesize(self, text: str, *, voice: str = "default") -> TTSResult: ...


class StubSTT:
    async def transcribe(self, audio_path: str, *, language: str = "zh") -> STTResult:
        return STTResult(ok=False, error="STT 未启用：未安装 faster-whisper。")


class StubTTS:
    async def synthesize(self, text: str, *, voice: str = "default") -> TTSResult:
        return TTSResult(ok=False, error="TTS 未启用：未安装 piper。")


class FasterWhisperSTT:
    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size

    async def transcribe(self, audio_path: str, *, language: str = "zh") -> STTResult:
        from faster_whisper import WhisperModel

        model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(audio_path, language=language)
        segs = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
        text = "".join(s["text"] for s in segs)
        return STTResult(ok=True, text=text.strip(), segments=segs)


class PiperTTS:
    def __init__(self, model_path: str) -> None:
        self._model_path = model_path

    async def synthesize(self, text: str, *, voice: str = "default") -> TTSResult:
        import os
        import subprocess
        import tempfile

        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        result = subprocess.run(  # noqa: S603
            ["piper", "--model", self._model_path, "--output_file", out],
            input=text.encode("utf-8"),
            capture_output=True,
        )
        if result.returncode != 0 or not os.path.exists(out):
            return TTSResult(ok=False, error=result.stderr.decode("utf-8", "ignore"))
        return TTSResult(ok=True, audio_path=out)


@lru_cache
def get_stt() -> STTEngine:
    try:
        import faster_whisper  # noqa: F401

        return FasterWhisperSTT()
    except ImportError:
        return StubSTT()


@lru_cache
def get_tts() -> TTSEngine:
    import os

    model_path = os.environ.get("XAGENT_TTS__PIPER_MODEL", "")
    if model_path:
        try:
            return PiperTTS(model_path)
        except Exception:
            pass
    return StubTTS()
