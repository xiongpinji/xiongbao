"""自进化技能系统（Skill Store）。

对标 Codex Skills / Hermes GEPA 学习闭环：
- Agent 完成复杂任务后自动提炼可复用 Skill
- Skill 以 JSON 持久化，支持搜索/调用/迭代优化
- 下次遇到类似任务时自动匹配并注入 system prompt
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.skills")

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


@dataclass
class Skill:
    skill_id: str
    name: str
    description: str
    trigger_pattern: str  # 触发关键词/正则
    steps: list[dict[str, Any]] = field(default_factory=list)  # 工具调用序列
    system_prompt_hint: str = ""  # 注入 system prompt 的提示
    use_count: int = 0
    success_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.use_count, 1)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["success_rate"] = self.success_rate
        return d


class SkillStore:
    """文件持久化技能库（轻量，无需额外 DB 表）。"""

    def __init__(self, storage_dir: Path | None = None) -> None:
        base = storage_dir or _PROJECT_ROOT / "data" / "skills"
        self._dir = base
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Skill] = {}
        self._load_all()

    def _load_all(self) -> None:
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                skill = Skill(**{k: v for k, v in data.items() if k != "success_rate"})
                self._cache[skill.skill_id] = skill
            except Exception:
                continue
        logger.info("skills_loaded", count=len(self._cache))

    def _persist(self, skill: Skill) -> None:
        path = self._dir / f"{skill.skill_id}.json"
        path.write_text(json.dumps(skill.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def create_skill(
        self,
        name: str,
        description: str,
        trigger_pattern: str,
        steps: list[dict[str, Any]] | None = None,
        system_prompt_hint: str = "",
        tags: list[str] | None = None,
    ) -> Skill:
        """从成功的任务中提炼新技能。"""
        skill = Skill(
            skill_id=uuid.uuid4().hex[:12],
            name=name,
            description=description,
            trigger_pattern=trigger_pattern,
            steps=steps or [],
            system_prompt_hint=system_prompt_hint,
            tags=tags or [],
        )
        self._cache[skill.skill_id] = skill
        self._persist(skill)
        logger.info("skill_created", skill_id=skill.skill_id, name=name)
        return skill

    def match(self, goal: str) -> list[Skill]:
        """根据目标文本匹配可用技能（关键词匹配）。"""
        matches = []
        goal_lower = goal.lower()
        for skill in self._cache.values():
            keywords = skill.trigger_pattern.lower().split("|")
            if any(kw.strip() in goal_lower for kw in keywords if kw.strip()):
                matches.append(skill)
        # 按成功率排序
        matches.sort(key=lambda s: s.success_rate, reverse=True)
        return matches[:3]

    def record_usage(self, skill_id: str, success: bool) -> None:
        """记录技能使用结果（自进化核心）。"""
        skill = self._cache.get(skill_id)
        if not skill:
            return
        skill.use_count += 1
        if success:
            skill.success_count += 1
        skill.updated_at = time.time()
        self._persist(skill)

    def get(self, skill_id: str) -> Skill | None:
        return self._cache.get(skill_id)

    def list_all(self) -> list[Skill]:
        return sorted(self._cache.values(), key=lambda s: s.use_count, reverse=True)

    def delete(self, skill_id: str) -> bool:
        if skill_id in self._cache:
            del self._cache[skill_id]
            path = self._dir / f"{skill_id}.json"
            path.unlink(missing_ok=True)
            return True
        return False

    def build_prompt_injection(self, goal: str) -> str:
        """为匹配的技能生成 system prompt 注入段。"""
        matched = self.match(goal)
        if not matched:
            return ""
        parts = ["## 可用技能（历史成功经验）"]
        for s in matched:
            parts.append(f"- **{s.name}**: {s.description}")
            if s.system_prompt_hint:
                parts.append(f"  提示: {s.system_prompt_hint}")
        return "\n".join(parts)


# 全局单例
_store: SkillStore | None = None


def get_skill_store() -> SkillStore:
    global _store
    if _store is None:
        _store = SkillStore()
    return _store
