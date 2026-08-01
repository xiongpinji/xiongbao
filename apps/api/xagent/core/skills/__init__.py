"""自进化技能系统（Skill Store）。

对标 Codex Skills / Hermes GEPA 学习闭环：
- Agent 完成复杂任务后自动提炼可复用 Skill
- Skill 以 JSON 持久化，支持搜索/调用/迭代优化
- 下次遇到类似任务时自动匹配并注入 system prompt
- 版本迭代：技能可被更新/增强，保留演化历史
- 自动淘汰：低效技能自动降级/归档
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

# ─── 自进化配置 ───
MIN_STEPS_FOR_EXTRACTION = 3      # 任务步数 >= 此值才考虑提炼
MIN_ANSWER_LEN_FOR_EXTRACTION = 100  # 回答长度 >= 此值才考虑提炼
RETIRE_THRESHOLD = 0.3            # 成功率低于此值触发降级
RETIRE_MIN_USES = 5               # 至少使用 N 次后才评估淘汰
MAX_SKILLS = 100                  # 技能库上限


@dataclass
class SkillVersion:
    """技能版本快照。"""
    version: int
    description: str
    system_prompt_hint: str
    steps: list[dict[str, Any]]
    changed_at: float = field(default_factory=time.time)
    change_reason: str = ""


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
    # ── 自进化字段 ──
    version: int = 1
    retired: bool = False           # 是否已降级/归档
    source: str = "manual"          # manual | auto_extracted | evolved
    source_task: str = ""           # 来源任务摘要
    history: list[dict[str, Any]] = field(default_factory=list)  # 版本历史

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.use_count, 1)

    @property
    def is_active(self) -> bool:
        return not self.retired

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["success_rate"] = self.success_rate
        d["is_active"] = self.is_active
        return d


class SkillStore:
    """文件持久化技能库（轻量，无需额外 DB 表）。

    自进化能力：
    - auto_extract: 从成功任务中自动提炼新技能
    - evolve: 更新已有技能（新版本 + 历史记录）
    - retire_low_performers: 淘汰低效技能
    """

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
                # 兼容旧格式（无新字段）
                valid_keys = {k for k in Skill.__dataclass_fields__}  # type: ignore
                skill = Skill(**{k: v for k, v in data.items() if k in valid_keys})
                self._cache[skill.skill_id] = skill
            except Exception:
                continue
        logger.info("skills_loaded", count=len(self._cache))

    def _persist(self, skill: Skill) -> None:
        path = self._dir / f"{skill.skill_id}.json"
        path.write_text(json.dumps(skill.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    # ─── 基础 CRUD ───

    def create_skill(
        self,
        name: str,
        description: str,
        trigger_pattern: str,
        steps: list[dict[str, Any]] | None = None,
        system_prompt_hint: str = "",
        tags: list[str] | None = None,
        source: str = "manual",
        source_task: str = "",
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
            source=source,
            source_task=source_task,
        )
        self._cache[skill.skill_id] = skill
        self._persist(skill)
        logger.info("skill_created", skill_id=skill.skill_id, name=name, source=source)
        return skill

    def match(self, goal: str) -> list[Skill]:
        """根据目标文本匹配可用技能（关键词匹配，排除已淘汰）。"""
        matches = []
        goal_lower = goal.lower()
        for skill in self._cache.values():
            if skill.retired:
                continue
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
        # 自动淘汰检查
        self._check_retirement(skill)

    def get(self, skill_id: str) -> Skill | None:
        return self._cache.get(skill_id)

    def list_all(self, include_retired: bool = False) -> list[Skill]:
        skills = self._cache.values()
        if not include_retired:
            skills = [s for s in skills if not s.retired]
        return sorted(skills, key=lambda s: s.use_count, reverse=True)

    def delete(self, skill_id: str) -> bool:
        if skill_id in self._cache:
            del self._cache[skill_id]
            path = self._dir / f"{skill_id}.json"
            path.unlink(missing_ok=True)
            return True
        return False

    # ─── 自进化：版本迭代 ───

    def evolve_skill(
        self,
        skill_id: str,
        description: str | None = None,
        system_prompt_hint: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        trigger_pattern: str | None = None,
        change_reason: str = "",
    ) -> Skill | None:
        """迭代升级已有技能（保留历史版本）。"""
        skill = self._cache.get(skill_id)
        if not skill:
            return None
        # 保存当前版本到历史
        skill.history.append({
            "version": skill.version,
            "description": skill.description,
            "system_prompt_hint": skill.system_prompt_hint,
            "steps": skill.steps,
            "changed_at": time.time(),
            "change_reason": change_reason,
        })
        # 应用更新
        skill.version += 1
        if description is not None:
            skill.description = description
        if system_prompt_hint is not None:
            skill.system_prompt_hint = system_prompt_hint
        if steps is not None:
            skill.steps = steps
        if trigger_pattern is not None:
            skill.trigger_pattern = trigger_pattern
        skill.updated_at = time.time()
        skill.source = "evolved"
        self._persist(skill)
        logger.info("skill_evolved", skill_id=skill_id, version=skill.version, reason=change_reason)
        return skill

    # ─── 自进化：自动提炼 ───

    async def auto_extract(
        self,
        goal: str,
        answer: str,
        steps_count: int,
        tools_used: list[str] | None = None,
    ) -> Skill | None:
        """从成功的复杂任务中自动提炼技能。

        条件：步数 >= MIN_STEPS_FOR_EXTRACTION 且（回答有实质内容 或 使用了多个工具）。
        使用 LLM 生成技能摘要（若可用），否则用规则提取。
        """
        if steps_count < MIN_STEPS_FOR_EXTRACTION:
            logger.debug("skill_extract_skip", reason="too_few_steps", steps=steps_count)
            return None
        # 工具型任务可能回答很短，但工具调用多也说明复杂度足够
        tools_count = len(tools_used or [])
        if len(answer) < MIN_ANSWER_LEN_FOR_EXTRACTION and tools_count < 3:
            logger.debug("skill_extract_skip", reason="insufficient_content",
                         answer_len=len(answer), tools=tools_count)
            return None

        # 检查是否已有高度相似的技能（避免重复）
        existing = self.match(goal)
        for s in existing:
            if s.success_rate > 0.7 and s.use_count >= 2:
                # 已有高效技能覆盖此场景，不重复创建
                return None

        # 尝试用 LLM 提炼
        name = ""
        description = ""
        trigger = ""
        hint = ""
        try:
            from xagent.adapters.llm import get_llm_client
            llm = get_llm_client()
            extract_prompt = (
                "你是一个技能提炼专家。根据以下任务执行记录，提炼一个可复用的技能模板。\n"
                "输出严格 JSON 格式（无其他文字）：\n"
                '{"name": "技能名(简短)", "description": "技能描述", '
                '"trigger": "触发关键词(|分隔,3-5个)", "hint": "执行提示(给Agent的建议)"}\n\n'
                f"任务目标: {goal[:300]}\n"
                f"执行步数: {steps_count}\n"
                f"使用工具: {', '.join(tools_used or [])}\n"
                f"最终回答摘要: {answer[:500]}"
            )
            from xagent.adapters.llm import Message as LLMMessage
            resp = await llm.complete([LLMMessage(role="user", content=extract_prompt)])
            raw = (resp.content or "").strip()
            # 提取 JSON
            import re as _re
            m = _re.search(r'\{[^{}]+\}', raw, _re.DOTALL)
            if m:
                data = json.loads(m.group())
                name = data.get("name", "")
                description = data.get("description", "")
                trigger = data.get("trigger", "")
                hint = data.get("hint", "")
        except Exception as e:
            logger.debug("skill_extract_llm_failed", error=str(e))

        # LLM 失败时用规则兜底
        if not name:
            # 从 goal 提取关键词作为名称
            name = goal[:30].strip()
            description = f"自动提炼自任务: {goal[:100]}"
            # 提取中文/英文关键词
            import re as _re
            words = _re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z]{3,}', goal)
            trigger = "|".join(words[:5]) if words else goal[:10]
            hint = f"执行过 {steps_count} 步完成，使用工具: {', '.join(tools_used or ['unknown'])}"

        if not trigger:
            import re as _re
            words = _re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z]{3,}', goal)
            trigger = "|".join(words[:5])

        # 构建 steps（记录工具调用序列）
        steps = [{"tool": t, "order": i} for i, t in enumerate(tools_used or [])]

        skill = self.create_skill(
            name=name,
            description=description or f"自动提炼: {goal[:80]}",
            trigger_pattern=trigger,
            steps=steps,
            system_prompt_hint=hint,
            tags=["auto_extracted"],
            source="auto_extracted",
            source_task=goal[:200],
        )
        logger.info("skill_auto_extracted", skill_id=skill.skill_id, name=name, steps=steps_count)
        return skill

    # ─── 自进化：淘汰机制 ───

    def _check_retirement(self, skill: Skill) -> None:
        """低效技能自动降级。"""
        if skill.use_count >= RETIRE_MIN_USES and skill.success_rate < RETIRE_THRESHOLD:
            skill.retired = True
            skill.updated_at = time.time()
            self._persist(skill)
            logger.info("skill_retired", skill_id=skill.skill_id, name=skill.name,
                       success_rate=f"{skill.success_rate:.0%}")

    def retire_low_performers(self) -> list[str]:
        """批量检查并淘汰低效技能，返回被淘汰的 ID 列表。"""
        retired = []
        for skill in self._cache.values():
            if skill.retired:
                continue
            if skill.use_count >= RETIRE_MIN_USES and skill.success_rate < RETIRE_THRESHOLD:
                skill.retired = True
                skill.updated_at = time.time()
                self._persist(skill)
                retired.append(skill.skill_id)
        if retired:
            logger.info("skills_retired_batch", count=len(retired))
        return retired

    def restore_skill(self, skill_id: str) -> bool:
        """恢复已淘汰的技能。"""
        skill = self._cache.get(skill_id)
        if not skill or not skill.retired:
            return False
        skill.retired = False
        skill.updated_at = time.time()
        self._persist(skill)
        return True

    # ─── Prompt 注入 ───

    def build_prompt_injection(self, goal: str) -> str:
        """为匹配的技能生成 system prompt 注入段。"""
        matched = self.match(goal)
        if not matched:
            return ""
        parts = ["## 可用技能（历史成功经验）"]
        for s in matched:
            parts.append(f"- **{s.name}** (v{s.version}, 成功率{s.success_rate:.0%}): {s.description}")
            if s.system_prompt_hint:
                parts.append(f"  提示: {s.system_prompt_hint}")
            if s.steps:
                tools_str = " → ".join(st.get("tool", "?") for st in s.steps[:5])
                parts.append(f"  工具链: {tools_str}")
        return "\n".join(parts)

    # ─── 统计 ───

    def stats(self) -> dict[str, Any]:
        """技能库统计信息。"""
        active = [s for s in self._cache.values() if not s.retired]
        retired = [s for s in self._cache.values() if s.retired]
        return {
            "total": len(self._cache),
            "active": len(active),
            "retired": len(retired),
            "auto_extracted": len([s for s in active if s.source == "auto_extracted"]),
            "evolved": len([s for s in active if s.source == "evolved"]),
            "total_uses": sum(s.use_count for s in self._cache.values()),
            "avg_success_rate": (
                sum(s.success_rate for s in active) / len(active) if active else 0
            ),
        }


# 全局单例
_store: SkillStore | None = None


def get_skill_store() -> SkillStore:
    global _store
    if _store is None:
        _store = SkillStore()
    return _store
