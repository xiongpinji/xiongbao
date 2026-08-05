"""角色 → TTS 音色分配（配音前置步骤）。

基于 CharacterCard 的 role/appearance/personality 文本做性别/年龄启发式推断，
把每个角色映射到 edge-tts 中文音色；同（性别, 年龄）桶的角色尽量分配不同音色，
避免「多角色共用一声」。输出 VoiceProfile 供 pipeline 配音步骤 / canvas 配音节点消费。
启发式仅依赖角色卡文本，无网络/LLM 调用，离线确定性。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from xagent.domains.creative_studio.media.audio_providers import DEFAULT_VOICE

if TYPE_CHECKING:
    from xagent.domains.creative_studio.storyboard import CharacterCard, Shot, Storyboard

# 性别线索（role/appearance/personality 文本中的关键词；先判女后判男）
_FEMALE_HINTS = ("女", "她", "小姐", "夫人", "太", "妈", "姨", "姐", "妹", "公主", "妃", "娘")
_MALE_HINTS = ("男", "他", "霸总", "少爷", "先生", "爷", "爸", "叔", "哥", "弟", "将军", "王")

# 年龄线索
_OLDER_HINTS = ("老", "奶", "婆", "叔", "姨", "父", "母", "中年后", "沧桑")
_YOUNG_HINTS = ("少", "小", "孩", "童", "学生", "萝莉", "正太")

# (性别, 年龄段) → 候选音色（有序，同桶多角色依次取不同音色）
_VOICE_BUCKETS: dict[tuple[str, str], list[str]] = {
    ("female", "young"): ["zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural"],
    ("female", "adult"): ["zh-CN-XiaohanNeural", "zh-CN-XiaomoNeural", "zh-CN-XiaoxiaoNeural"],
    ("female", "older"): ["zh-CN-XiaomoNeural", "zh-CN-XiaohanNeural"],
    ("male", "young"): ["zh-CN-YunxiNeural", "zh-CN-YunyangNeural"],
    ("male", "adult"): ["zh-CN-YunjianNeural", "zh-CN-YunyangNeural", "zh-CN-YunxiNeural"],
    ("male", "older"): ["zh-CN-YunzeNeural", "zh-CN-YunyangNeural"],
}


@dataclass
class VoiceProfile:
    """单个角色/旁白的配音配置。"""

    character_name: str
    voice: str = DEFAULT_VOICE
    gender: str = "unknown"      # female | male | unknown
    age_group: str = "adult"     # young | adult | older
    rate: str = "+0%"            # edge-tts 语速
    pitch: str = "+0Hz"          # edge-tts 音高
    reason: str = ""             # 分配依据（审计/前端展示）

    def to_params(self) -> dict[str, str]:
        """转成 GenerationRequest.params 透传字段。"""
        return {"voice": self.voice, "rate": self.rate, "pitch": self.pitch}


def infer_gender(*texts: str) -> str:
    """从角色卡文本推断性别；无法判断返回 unknown。"""
    blob = " ".join(t for t in texts if t)
    if any(h in blob for h in _FEMALE_HINTS):
        return "female"
    if any(h in blob for h in _MALE_HINTS):
        return "male"
    return "unknown"


def infer_age_group(*texts: str) -> str:
    """从角色卡文本推断年龄段；默认 adult。"""
    blob = " ".join(t for t in texts if t)
    if any(h in blob for h in _OLDER_HINTS):
        return "older"
    if any(h in blob for h in _YOUNG_HINTS):
        return "young"
    return "adult"


def assign_voice(card: CharacterCard, *, used: set[str] | None = None) -> VoiceProfile:
    """给单个角色分配音色。used 为已占用音色集合，同桶角色会错开。"""
    gender = infer_gender(card.role, card.appearance, card.personality)
    age_group = infer_age_group(card.role, card.appearance, card.personality)
    candidates = _VOICE_BUCKETS.get((gender, age_group))
    if candidates is None:
        # unknown 性别：按年龄段落到女声默认（短剧女主向内容居多）
        candidates = _VOICE_BUCKETS.get(("female", age_group), [DEFAULT_VOICE])
    used = used or set()
    voice = next((v for v in candidates if v not in used), candidates[0])
    return VoiceProfile(
        character_name=card.name,
        voice=voice,
        gender=gender,
        age_group=age_group,
        reason=f"role={card.role or '未填'} -> {gender}/{age_group}",
    )


def assign_voices(storyboard: Storyboard) -> dict[str, VoiceProfile]:
    """给故事板所有角色分配音色（角色名 -> VoiceProfile），同桶错开。"""
    used: set[str] = set()
    result: dict[str, VoiceProfile] = {}
    for card in storyboard.characters:
        if not card.name:
            continue
        profile = assign_voice(card, used=used)
        used.add(profile.voice)
        result[card.name] = profile
    return result


def default_voice_profile(name: str = "旁白") -> VoiceProfile:
    """无角色卡/未匹配到角色时的默认音色（旁白/群像）。"""
    return VoiceProfile(character_name=name, voice=DEFAULT_VOICE, reason="默认音色")


def voice_for_shot(
    shot: Shot, assignments: Mapping[str, VoiceProfile]
) -> VoiceProfile:
    """取镜头第一个已分配角色的音色；无匹配则旁白默认。"""
    for name in shot.characters:
        profile = assignments.get(name)
        if profile is not None:
            return profile
    return default_voice_profile()
