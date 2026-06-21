"""语音适配层：STT(faster-whisper) + TTS(Piper/Kokoro)。

未安装模型库时降级为 stub（返回占位），保证 lite/CI 可跑。
生产装 faster-whisper + piper 后即真实可用。
"""

from xagent.adapters.audio.base import STTEngine, TTSEngine, get_stt, get_tts

__all__ = ["STTEngine", "TTSEngine", "get_stt", "get_tts"]
