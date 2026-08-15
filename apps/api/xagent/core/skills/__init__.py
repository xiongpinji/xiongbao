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
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from xagent.infra.logging import get_logger
from xagent.infra.paths import data_path

logger = get_logger("xagent.skills")

def default_skills_root() -> Path:
    configured = os.environ.get("XAGENT_SKILLS_ROOT", "").strip()
    return Path(configured).expanduser() if configured else data_path("skills")

# ─── 自进化配置 ───
MIN_STEPS_FOR_EXTRACTION = 3      # 任务步数 >= 此值才考虑提炼
MIN_ANSWER_LEN_FOR_EXTRACTION = 100  # 回答长度 >= 此值才考虑提炼
RETIRE_THRESHOLD = 0.3            # 成功率低于此值触发降级
RETIRE_MIN_USES = 5               # 至少使用 N 次后才评估淘汰
MAX_SKILLS = 100                  # 技能库上限
# ─── 自动提炼门禁配置（对标 Hermes GEPA：变体须过最小评测门禁才入库） ───
DEDUP_SIMILARITY_THRESHOLD = 0.5  # 与现有技能 token 相似度 >= 此值视为重复，拒绝入库
MIN_TRIGGER_KEYWORD_LEN = 2       # 触发关键词最小长度（过短易误匹配）
# ─── 进化闭环配置（GEPA 轻量落地：变体生成 → 评测打分 → 优胜入库） ───
EVOLVE_DEFAULT_VARIANTS = 2       # 每次自动进化生成的变体数
EVOLVE_ACCEPT_THRESHOLD = 0.1     # 变体得分须显著优于父代（>= 此差值）才采纳
EVAL_POSITIVE_GOALS = 4           # 合成评测：应命中 goal 数（3-5）
EVAL_NEGATIVE_GOALS = 3           # 合成评测：不应命中 goal 数（2-3）
SCORE_WEIGHT_MATCH = 0.6          # 评分权重：匹配准确率
SCORE_WEIGHT_COMPLETENESS = 0.2   # 评分权重：字段完整度
SCORE_WEIGHT_HISTORY = 0.2        # 评分权重：历史成功率


def _tokenize(text: str) -> set[str]:
    """提取中文词组/英文单词 token 集合，用于相似度去重。"""
    import re as _re
    return set(_re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z]{3,}', text.lower()))


def _text_similarity(a: str, b: str) -> float:
    """token 集合 Jaccard 相似度（0~1）。"""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ─── LLM 输出 JSON 鲁棒提取（真实模型输出常带噪：尾逗号/多余文本/截断） ───


def _parse_llm_json(raw: str, *, expect: str = "object") -> Any | None:
    """从 LLM 输出提取 JSON。依次尝试：整串解析 → 贪心块 → 非贪心块 → 去尾逗号。

    expect: "object"（{}）或 "array"（[]）。失败返回 None（调用方降级处理）。
    """
    import re as _re

    text = (raw or "").strip()
    if not text:
        return None
    open_c, close_c = ("{", "}") if expect == "object" else ("[", "]")

    candidates: list[str] = []
    if text.startswith(open_c):
        candidates.append(text)
    m = _re.search(rf"\{open_c}[\s\S]*\{close_c}", text)
    if m:
        candidates.append(m.group())
    m = _re.search(rf"\{open_c}[\s\S]*?\{close_c}", text)
    if m:
        candidates.append(m.group())

    for cand in candidates:
        for variant in (cand, _re.sub(r",(\s*[}\]])", r"\1", cand)):
            try:
                return json.loads(variant)
            except (json.JSONDecodeError, ValueError):
                continue
    return None


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
    source: str = "manual"          # manual | auto_extracted | auto_distilled | evolved
    source_task: str = ""           # 来源任务摘要
    history: list[dict[str, Any]] = field(default_factory=list)  # 版本历史
    tenant_id: str = ""             # 空值表示历史全局技能
    package_id: str = ""            # 完整 Skill Package 关联

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
        base = storage_dir or default_skills_root()
        self._dir = base
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Skill] = {}
        # 单调递增版本号：任何库内容变更 +1，供读路径缓存失效判断
        self._version = 0
        self._load_all()

    @property
    def version(self) -> int:
        """库内容版本号（任何写操作递增，只增不减）。"""
        return self._version

    def _load_all(self) -> None:
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                # 兼容旧格式（无新字段）
                valid_keys = set(Skill.__dataclass_fields__)
                skill = Skill(**{k: v for k, v in data.items() if k in valid_keys})
                self._cache[skill.skill_id] = skill
            except Exception as exc:  # noqa: BLE001
                logger.warning("skill_load_failed", path=str(f), error=str(exc))
                continue
        logger.info("skills_loaded", count=len(self._cache))

    def _persist(self, skill: Skill) -> None:
        path = self._dir / f"{skill.skill_id}.json"
        path.write_text(json.dumps(skill.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._version += 1

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
        tenant_id: str = "",
        package_id: str = "",
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
            tenant_id=tenant_id,
            package_id=package_id,
        )
        self._cache[skill.skill_id] = skill
        self._persist(skill)
        logger.info("skill_created", skill_id=skill.skill_id, name=name, source=source)
        return skill

    def match(self, goal: str, tenant_id: str | None = None) -> list[Skill]:
        """根据目标文本匹配可用技能（关键词匹配，排除已淘汰）。"""
        matches = []
        goal_lower = goal.lower()
        for skill in self._cache.values():
            if skill.retired:
                continue
            if tenant_id is not None and skill.tenant_id not in {"", tenant_id}:
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

    def get_for_tenant(self, skill_id: str, tenant_id: str) -> Skill | None:
        skill = self._cache.get(skill_id)
        if skill is None or skill.tenant_id not in {"", tenant_id}:
            return None
        return skill

    def list_all(
        self, include_retired: bool = False, tenant_id: str | None = None
    ) -> list[Skill]:
        skills = list(self._cache.values())
        if tenant_id is not None:
            skills = [skill for skill in skills if skill.tenant_id in {"", tenant_id}]
        if not include_retired:
            skills = [s for s in skills if not s.retired]
        return sorted(skills, key=lambda s: s.use_count, reverse=True)

    def delete(self, skill_id: str) -> bool:
        if skill_id in self._cache:
            del self._cache[skill_id]
            path = self._dir / f"{skill_id}.json"
            path.unlink(missing_ok=True)
            self._version += 1
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

    # ─── 自进化：LLM 提炼 + 质量门禁（对标 Hermes GEPA 闭环） ───

    async def distill_candidate(
        self,
        goal: str,
        answer: str,
        steps_count: int,
        tools_used: list[str] | None = None,
        llm: Any | None = None,
    ) -> dict[str, Any] | None:
        """由 LLM 把成功任务提炼为候选技能（不入库）。

        无可用 LLM（Mock 降级）或调用/解析失败时静默跳过，返回 None。
        """
        if steps_count < MIN_STEPS_FOR_EXTRACTION:
            logger.debug("skill_distill_skip", reason="too_few_steps", steps=steps_count)
            return None
        tools_count = len(tools_used or [])
        if len(answer) < MIN_ANSWER_LEN_FOR_EXTRACTION and tools_count < 3:
            logger.debug("skill_distill_skip", reason="insufficient_content",
                         answer_len=len(answer), tools=tools_count)
            return None

        if llm is None:
            try:
                from xagent.adapters.llm import get_llm_client
                llm = get_llm_client()
            except Exception as e:
                logger.debug("skill_distill_skip", reason="no_llm", error=str(e))
                return None
        # Mock 降级客户端产出不了真实提炼结果，视为「无 LLM」静默跳过
        from xagent.adapters.llm.mock import MockLLMClient
        if isinstance(llm, MockLLMClient):
            logger.debug("skill_distill_skip", reason="mock_llm")
            return None

        import re as _re
        extract_prompt = (
            "你是一个技能提炼专家。根据以下任务执行记录，提炼一个可复用的技能模板。\n"
            "输出严格 JSON 格式（无其他文字）：\n"
            '{"name": "技能名(简短)", "description": "技能描述", '
            '"trigger": "触发关键词(|分隔,3-5个,须来自任务目标原文)", '
            '"hint": "执行提示(给Agent的建议)"}\n\n'
            f"任务目标: {goal[:300]}\n"
            f"执行步数: {steps_count}\n"
            f"使用工具: {', '.join(tools_used or [])}\n"
            f"最终回答摘要: {answer[:500]}"
        )
        try:
            from xagent.adapters.llm import Message as LLMMessage
            resp = await llm.complete([LLMMessage(role="user", content=extract_prompt)])
            raw = (resp.content or "").strip()
            m = _re.search(r'\{[^{}]+\}', raw, _re.DOTALL)
            if not m:
                logger.debug("skill_distill_skip", reason="llm_no_json")
                return None
            data = json.loads(m.group())
        except Exception as e:
            logger.debug("skill_distill_skip", reason="llm_failed", error=str(e))
            return None

        return {
            "name": str(data.get("name", "")).strip(),
            "description": str(data.get("description", "")).strip(),
            "trigger_pattern": str(data.get("trigger", "")).strip(),
            "system_prompt_hint": str(data.get("hint", "")).strip(),
            "steps": [{"tool": t, "order": i} for i, t in enumerate(tools_used or [])],
            "source_task": goal[:200],
        }

    def gate_candidate(
        self,
        candidate: dict[str, Any],
        goal: str,
        tenant_id: str = "",
    ) -> tuple[bool, str]:
        """入库质量门禁（对标 Hermes：变体须过最小评测才入库）。

        检查项：
        1. 字段完整：name/description/trigger_pattern/system_prompt_hint 均非空
        2. 触发模式可被匹配器命中：至少一个关键词出现在来源任务目标中
        3. 租户内去重：与同租户技能 token 相似度低于阈值
        4. 全局技能库未满

        返回 (是否通过, 失败原因)。
        """
        # 1. 字段完整性
        for key in ("name", "description", "trigger_pattern", "system_prompt_hint"):
            if not str(candidate.get(key, "")).strip():
                return False, f"incomplete_field:{key}"
        # 2. 触发模式可被匹配器命中（与 match() 同一匹配语义）
        goal_lower = goal.lower()
        keywords = [
            kw.strip().lower()
            for kw in candidate["trigger_pattern"].split("|")
            if len(kw.strip()) >= MIN_TRIGGER_KEYWORD_LEN
        ]
        if not keywords or not any(kw in goal_lower for kw in keywords):
            return False, "trigger_not_matchable"
        # 3. 去重（相似度阈值）
        cand_text = " ".join([
            candidate["name"], candidate["description"], candidate["trigger_pattern"],
        ])
        for s in self._cache.values():
            if s.retired or s.tenant_id != tenant_id:
                continue
            sim = _text_similarity(cand_text, f"{s.name} {s.description} {s.trigger_pattern}")
            if sim >= DEDUP_SIMILARITY_THRESHOLD:
                return False, f"duplicate:{s.skill_id}:sim={sim:.2f}"
        # 4. 技能库容量
        if len([s for s in self._cache.values() if not s.retired]) >= MAX_SKILLS:
            return False, "store_full"
        return True, ""

    async def auto_distill(
        self,
        goal: str,
        answer: str,
        steps_count: int,
        tools_used: list[str] | None = None,
        llm: Any | None = None,
    ) -> Skill | None:
        """任务成功后自动提炼技能：LLM 提炼候选 → 质量门禁 → 入库（source=auto_distilled）。

        对标 Hermes GEPA 闭环：不过门禁的候选记日志丢弃，绝不污染技能库。
        自动提炼的技能保留人工 evolve/retire 生命周期。
        """
        candidate = await self.distill_candidate(
            goal, answer, steps_count, tools_used, llm=llm
        )
        if candidate is None:
            return None
        ok, reason = self.gate_candidate(candidate, goal)
        if not ok:
            logger.info("skill_gate_reject", reason=reason, name=candidate.get("name", ""))
            return None
        skill = self.create_skill(
            name=candidate["name"],
            description=candidate["description"],
            trigger_pattern=candidate["trigger_pattern"],
            steps=candidate["steps"],
            system_prompt_hint=candidate["system_prompt_hint"],
            tags=["auto_distilled"],
            source="auto_distilled",
            source_task=candidate["source_task"],
        )
        logger.info("skill_auto_distilled", skill_id=skill.skill_id, name=skill.name)
        return skill

    # ─── 自进化：GEPA 式进化闭环（变体生成 → 评测打分 → 优胜入库） ───

    @staticmethod
    def _fields_of(skill: Skill) -> dict[str, Any]:
        """把 Skill 转为可评测的字段 dict（与变体同一形状）。"""
        return {
            "name": skill.name,
            "description": skill.description,
            "trigger_pattern": skill.trigger_pattern,
            "system_prompt_hint": skill.system_prompt_hint,
            "steps": skill.steps,
            "source_task": skill.source_task,
        }

    @staticmethod
    def _match_trigger(trigger_pattern: str, goal: str) -> bool:
        """与 match() 同一匹配语义：| 分隔关键词子串命中。"""
        keywords = [
            kw.strip().lower()
            for kw in str(trigger_pattern).split("|")
            if kw.strip()
        ]
        goal_lower = goal.lower()
        return any(kw in goal_lower for kw in keywords)

    @staticmethod
    def _completeness_score(fields: dict[str, Any]) -> float:
        """字段完整度分（0~1）：4 个文本字段各 0.2，steps 非空 0.2。"""
        score = 0.0
        for key in ("name", "description", "trigger_pattern", "system_prompt_hint"):
            if str(fields.get(key, "")).strip():
                score += 0.2
        if fields.get("steps"):
            score += 0.2
        return round(score, 4)

    def evaluate_fields(
        self,
        fields: dict[str, Any],
        eval_tasks: dict[str, list[str]] | None = None,
        success_rate: float = 0.5,
        has_history: bool = False,
    ) -> dict[str, Any]:
        """对一组技能字段打分（变体与父代同一评测口径）。

        得分 = 匹配准确率 * 0.6 + 字段完整度 * 0.2 + 历史成功率 * 0.2。
        - 有合成评测任务时：在应命中/不应命中 goal 上计算匹配准确率
        - 无 LLM（无评测任务）降级：纯匹配器准确率——触发模式能否命中技能自身语境
        """
        positive = [g for g in (eval_tasks or {}).get("positive", []) if str(g).strip()]
        negative = [g for g in (eval_tasks or {}).get("negative", []) if str(g).strip()]
        if positive or negative:
            total = len(positive) + len(negative)
            correct = sum(
                1 for g in positive if self._match_trigger(fields.get("trigger_pattern", ""), g)
            ) + sum(
                1 for g in negative if not self._match_trigger(fields.get("trigger_pattern", ""), g)
            )
            match_accuracy = correct / total
        else:
            ref = " ".join([
                str(fields.get("description", "")),
                str(fields.get("source_task", "")),
                str(fields.get("name", "")),
            ])
            match_accuracy = (
                1.0
                if self._match_trigger(fields.get("trigger_pattern", ""), ref)
                else 0.0
            )
        completeness = self._completeness_score(fields)
        history = success_rate if has_history else 0.5
        score = (
            SCORE_WEIGHT_MATCH * match_accuracy
            + SCORE_WEIGHT_COMPLETENESS * completeness
            + SCORE_WEIGHT_HISTORY * history
        )
        return {
            "score": round(score, 4),
            "match_accuracy": round(match_accuracy, 4),
            "completeness": completeness,
            "history": history,
            "eval_mode": "synthetic" if (positive or negative) else "matcher_only",
        }

    def _resolve_llm(self, llm: Any | None) -> Any | None:
        """解析 LLM 客户端；无真实 LLM（含 Mock 降级）返回 None。"""
        if llm is None:
            try:
                from xagent.adapters.llm import get_llm_client
                llm = get_llm_client()
            except Exception as e:
                logger.debug("skill_evolve_no_llm", error=str(e))
                return None
        from xagent.adapters.llm.mock import MockLLMClient
        if isinstance(llm, MockLLMClient):
            return None
        return llm

    async def generate_eval_tasks(self, skill: Skill, llm: Any) -> dict[str, list[str]] | None:
        """由 LLM 基于技能描述生成合成评测任务：应命中 goal 3-5 个 + 不应命中 2-3 个。"""
        prompt = (
            "你是一个技能评测专家。根据以下技能，生成评测样例，输出严格 JSON（无其他文字）：\n"
            '{"positive": ["应触发目标", ...], '
            '"negative": ["不应触发目标", ...]}\n'
            f"positive 生成 {EVAL_POSITIVE_GOALS} 个（语义多样），"
            f"negative 生成 {EVAL_NEGATIVE_GOALS} 个"
            "（与技能无关但领域相近）。\n\n"
            f"技能名称: {skill.name}\n"
            f"技能描述: {skill.description[:300]}\n"
            f"触发关键词: {skill.trigger_pattern}"
        )
        try:
            from xagent.adapters.llm import Message as LLMMessage
            resp = await llm.complete([LLMMessage(role="user", content=prompt)])
            raw = (resp.content or "").strip()
            data = _parse_llm_json(raw, expect="object")
            if data is None:
                return None
            positive = [str(g).strip() for g in data.get("positive", []) if str(g).strip()][:5]
            negative = [str(g).strip() for g in data.get("negative", []) if str(g).strip()][:3]
            if not positive and not negative:
                return None
            return {"positive": positive, "negative": negative}
        except Exception as e:
            logger.debug("skill_eval_tasks_failed", error=str(e))
            return None

    async def generate_variants(
        self,
        skill: Skill,
        n: int = EVOLVE_DEFAULT_VARIANTS,
        llm: Any | None = None,
    ) -> list[dict[str, Any]]:
        """由 LLM 对一个已有技能生成 N 个改进变体（不入库）。无 LLM 时返回空列表。"""
        llm = self._resolve_llm(llm)
        if llm is None:
            logger.debug("skill_variants_skip", reason="no_llm", skill_id=skill.skill_id)
            return []
        prompt = (
            "你是一个技能进化专家。针对以下技能，生成 "
            f"{n} 个改进变体（如：优化触发关键词提高命中精度/补充执行步骤/优化提示词）。\n"
            "输出严格 JSON 数组（无其他文字），每个元素：\n"
            '{"description": "改进后描述", "trigger_pattern": "触发关键词(|分隔)", '
            '"system_prompt_hint": "执行提示", "steps": [{"tool": "工具名", "order": 0}]}\n'
            "变体之间要有差异化改进方向。\n\n"
            f"技能名称: {skill.name}\n"
            f"当前描述: {skill.description[:300]}\n"
            f"当前触发: {skill.trigger_pattern}\n"
            f"当前提示: {skill.system_prompt_hint[:200]}\n"
            f"当前步骤: {json.dumps(skill.steps, ensure_ascii=False)[:300]}"
        )
        try:
            from xagent.adapters.llm import Message as LLMMessage
            resp = await llm.complete([LLMMessage(role="user", content=prompt)])
            raw = (resp.content or "").strip()
            data = _parse_llm_json(raw, expect="array")
            if data is None:
                logger.debug("skill_variants_skip", reason="llm_no_json", skill_id=skill.skill_id)
                return []
        except Exception as e:
            logger.debug("skill_variants_skip", reason="llm_failed", error=str(e))
            return []
        variants: list[dict[str, Any]] = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            variant = {
                "name": skill.name,
                "description": str(item.get("description", "")).strip() or skill.description,
                "trigger_pattern": str(item.get("trigger_pattern", "")).strip(),
                "system_prompt_hint": str(item.get("system_prompt_hint", "")).strip()
                    or skill.system_prompt_hint,
                "steps": item.get("steps") if isinstance(item.get("steps"), list) else skill.steps,
                "source_task": skill.source_task,
            }
            if variant["trigger_pattern"]:
                variants.append(variant)
        return variants[:n]

    async def evolve_auto(
        self,
        skill_id: str,
        n_variants: int = EVOLVE_DEFAULT_VARIANTS,
        threshold: float = EVOLVE_ACCEPT_THRESHOLD,
        llm: Any | None = None,
        require_review: bool = False,
    ) -> dict[str, Any] | None:
        """自动进化闭环：变体生成 → 评测打分 → 显著优胜才通过 evolve 替换入库。

        对标 Hermes GEPA：变体得分 >= 父代 + threshold 才采纳（走 evolve_skill 版本化，
        history 记录进化原因与得分），否则丢弃并记日志。无 LLM 时跳过。
        返回 None 表示技能不存在。"""
        skill = self._cache.get(skill_id)
        if not skill:
            return None
        result: dict[str, Any] = {
            "skill_id": skill_id,
            "adopted": False,
            "reason": "",
            "parent_score": None,
            "variants": [],
        }
        llm = self._resolve_llm(llm)
        if llm is None:
            result["reason"] = "no_llm"
            logger.info("skill_evolve_auto_skip", skill_id=skill_id, reason="no_llm")
            return result

        # 1. 合成评测任务（父代与变体共用，保证公平比较）；失败则降级纯匹配器
        eval_tasks = await self.generate_eval_tasks(skill, llm)
        has_history = skill.use_count > 0
        parent_eval = self.evaluate_fields(
            self._fields_of(skill), eval_tasks,
            success_rate=skill.success_rate, has_history=has_history,
        )
        result["parent_score"] = parent_eval["score"]
        result["parent_eval"] = parent_eval

        # 2. 生成变体
        variants = await self.generate_variants(skill, n=n_variants, llm=llm)
        if not variants:
            result["reason"] = "no_variants"
            logger.info("skill_evolve_auto_skip", skill_id=skill_id, reason="no_variants")
            return result

        # 3. 评测打分（变体继承父代历史分量，差异只来自匹配准确率与完整度）
        scored = []
        for v in variants:
            ev = self.evaluate_fields(
                v, eval_tasks, success_rate=skill.success_rate, has_history=has_history,
            )
            scored.append({"variant": v, "eval": ev, "score": ev["score"]})
        result["variants"] = scored
        best = max(scored, key=lambda x: x["score"])
        result["best_score"] = best["score"]

        # 4. 优胜判定：显著优于父代才准许入库
        if best["score"] - parent_eval["score"] >= threshold:
            v = best["variant"]
            reason = (
                f"auto_evolve: score {parent_eval['score']:.2f} -> {best['score']:.2f} "
                f"(threshold +{threshold:.2f}, eval={parent_eval['eval_mode']})"
            )
            # 人工审核模式（对标 Hermes GEPA 人工 PR 门禁）：评测通过不直接替换，
            # 挂起为待审核条目，由 approve_evolution 人工批准后才走 evolve 版本化。
            if require_review:
                pending_id = self._add_pending_evolution(
                    skill_id=skill_id, variant=v,
                    parent_eval=parent_eval, best_eval=best["eval"],
                    threshold=threshold, reason=reason,
                )
                result["adopted"] = False
                result["reason"] = f"pending_review:{pending_id}"
                result["pending_id"] = pending_id
                logger.info(
                    "skill_evolve_pending_review", skill_id=skill_id,
                    pending_id=pending_id, best_score=best["score"],
                )
                return result
            self.evolve_skill(
                skill_id,
                description=v["description"],
                system_prompt_hint=v["system_prompt_hint"],
                steps=v["steps"],
                trigger_pattern=v["trigger_pattern"],
                change_reason=reason,
            )
            result["adopted"] = True
            result["reason"] = reason
            result["skill"] = self._cache[skill_id].to_dict()
            logger.info(
                "skill_evolve_auto_adopted", skill_id=skill_id,
                parent_score=parent_eval["score"], best_score=best["score"],
            )
        else:
            result["reason"] = (
                f"below_threshold: best {best['score']:.2f} vs parent "
                f"{parent_eval['score']:.2f} (need +{threshold:.2f})"
            )
            logger.info(
                "skill_evolve_auto_rejected", skill_id=skill_id,
                parent_score=parent_eval["score"], best_score=best["score"],
                threshold=threshold,
            )
        return result

    # ─── 自进化：人工审核队列（pending evolution） ───

    @property
    def _pending_path(self) -> Path:
        return self._dir / "_pending_evolutions.json"

    def _load_pending(self) -> dict[str, Any]:
        try:
            return json.loads(self._pending_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 文件不存在/损坏按空队列处理
            return {}

    def _save_pending(self, pending: dict[str, Any]) -> None:
        self._pending_path.write_text(
            json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _add_pending_evolution(
        self,
        *,
        skill_id: str,
        variant: dict[str, Any],
        parent_eval: dict[str, Any],
        best_eval: dict[str, Any],
        threshold: float,
        reason: str,
    ) -> str:
        pending = self._load_pending()
        pending_id = uuid.uuid4().hex[:12]
        pending[pending_id] = {
            "pending_id": pending_id,
            "skill_id": skill_id,
            "variant": variant,
            "parent_eval": parent_eval,
            "best_eval": best_eval,
            "threshold": threshold,
            "reason": reason,
            "created_at": time.time(),
        }
        self._save_pending(pending)
        return pending_id

    def list_pending_evolutions(self) -> list[dict[str, Any]]:
        """列出待人工审核的进化条目（按创建时间倒序）。"""
        items = list(self._load_pending().values())
        return sorted(items, key=lambda x: -x.get("created_at", 0))

    def approve_evolution(self, pending_id: str) -> dict[str, Any] | None:
        """人工批准：把挂起的优胜变体走 evolve_skill 版本化入库。"""
        pending = self._load_pending()
        entry = pending.pop(pending_id, None)
        if entry is None:
            return None
        v = entry["variant"]
        evolved = self.evolve_skill(
            entry["skill_id"],
            description=v["description"],
            system_prompt_hint=v["system_prompt_hint"],
            steps=v["steps"],
            trigger_pattern=v["trigger_pattern"],
            change_reason=f"approved: {entry['reason']}",
        )
        self._save_pending(pending)
        if evolved is None:
            return None
        logger.info(
            "skill_evolve_approved", skill_id=entry["skill_id"], pending_id=pending_id
        )
        return {"approved": True, "skill_id": entry["skill_id"],
                "skill": evolved.to_dict()}

    def reject_evolution(self, pending_id: str) -> bool:
        """人工拒绝：丢弃挂起变体（技能不变）。"""
        pending = self._load_pending()
        if pending.pop(pending_id, None) is None:
            return False
        self._save_pending(pending)
        logger.info("skill_evolve_rejected", pending_id=pending_id)
        return True

    # ─── 自进化：失败反思提炼（从失败学习） ───

    async def distill_from_failure(
        self,
        goal: str,
        error: str,
        tools_used: list[str] | None = None,
        llm: Any | None = None,
    ) -> Skill | None:
        """失败任务反思提炼（对标 GEPA 反思式失败分析的轻量版）。

        从失败目标 + 错误信息提炼"如何避免该类失败"的技能候选，
        过同一 gate_candidate 门禁后入库（source=failure_distilled）。
        无 LLM / 提炼失败 / 不过门禁均返回 None（记日志，绝不污染技能库）。
        """
        llm = self._resolve_llm(llm)
        if llm is None:
            return None
        prompt = (
            "你是一个失败分析专家。以下任务执行失败，分析失败根因并提炼一个"
            "\"如何避免该类失败\"的技能（面向未来同类任务的避坑规程）。\n"
            "输出严格 JSON（无其他文字）：\n"
            '{"name": "技能名(体现避坑主题)", "description": "何时使用+避免什么失败", '
            '"trigger_pattern": "触发关键词(|分隔)", '
            '"system_prompt_hint": "避坑执行规程", "steps": []}\n'
            "注意：trigger_pattern 必须从下方任务目标原文中选取 2-4 个关键词"
            "（中文 2-4 字词或英文单词），确保同类目标再次出现时能被子串匹配命中。\n\n"
            f"失败任务目标: {goal[:300]}\n"
            f"失败信息: {error[:500]}\n"
            f"涉及工具: {', '.join(tools_used or [])[:200]}"
        )
        try:
            from xagent.adapters.llm import Message as LLMMessage
            resp = await llm.complete([LLMMessage(role="user", content=prompt)])
            raw = (resp.content or "").strip()
            data = _parse_llm_json(raw, expect="object")
            if data is None or not isinstance(data, dict):
                return None
        except Exception as e:
            logger.debug("skill_failure_distill_failed", error=str(e))
            return None
        candidate: dict[str, Any] = {
            "name": str(data.get("name", "")).strip(),
            "description": str(data.get("description", "")).strip(),
            "trigger_pattern": str(data.get("trigger_pattern", "")).strip(),
            "system_prompt_hint": str(data.get("system_prompt_hint", "")).strip(),
            "steps": data.get("steps") if isinstance(data.get("steps"), list) else [],
            "source_task": f"failure: {goal[:200]}",
        }
        # 触发词可命中性兜底（真实模型常无视 prompt 约束自选触发词）：
        # 从目标原文派生关键词并入 trigger_pattern——避坑技能必须在同类目标
        # 再次出现时能被命中，同时保证门禁 trigger_not_matchable 不误杀。
        goal_kws = sorted(_tokenize(goal))[:4]
        existing = [k for k in candidate["trigger_pattern"].split("|") if k.strip()]
        merged = existing + [k for k in goal_kws if k not in {e.lower() for e in existing}]
        candidate["trigger_pattern"] = "|".join(merged)
        ok, reason = self.gate_candidate(candidate, goal)
        if not ok:
            logger.info(
                "skill_gate_reject", reason=reason,
                name=candidate.get("name", ""), source="failure_distilled",
            )
            return None
        skill = self.create_skill(
            name=candidate["name"],
            description=candidate["description"],
            trigger_pattern=candidate["trigger_pattern"],
            steps=candidate["steps"],
            system_prompt_hint=candidate["system_prompt_hint"],
            tags=["failure_distilled"],
            source="failure_distilled",
            source_task=candidate["source_task"],
        )
        logger.info("skill_failure_distilled", skill_id=skill.skill_id, name=skill.name)
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

    def retire_low_performers(self, tenant_id: str | None = None) -> list[str]:
        """批量检查并淘汰低效技能，返回被淘汰的 ID 列表。"""
        retired = []
        for skill in self._cache.values():
            if tenant_id is not None and skill.tenant_id not in {"", tenant_id}:
                continue
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

    def build_prompt_injection(self, goal: str, tenant_id: str | None = None) -> str:
        """为匹配的技能生成 system prompt 注入段。"""
        matched = self.match(goal, tenant_id=tenant_id)
        if not matched:
            return ""
        parts = ["## 可用技能（历史成功经验）"]
        for s in matched:
            parts.append(
                f"- **{s.name}** (v{s.version}, 成功率{s.success_rate:.0%}): "
                f"{s.description}"
            )
            if s.system_prompt_hint:
                parts.append(f"  提示: {s.system_prompt_hint}")
            if s.steps:
                tools_str = " → ".join(st.get("tool", "?") for st in s.steps[:5])
                parts.append(f"  工具链: {tools_str}")
        return "\n".join(parts)

    # ─── 统计 ───

    def stats(self, tenant_id: str | None = None) -> dict[str, Any]:
        """技能库统计信息。"""
        visible = [
            skill
            for skill in self._cache.values()
            if tenant_id is None or skill.tenant_id in {"", tenant_id}
        ]
        active = [s for s in visible if not s.retired]
        retired = [s for s in visible if s.retired]
        return {
            "total": len(visible),
            "active": len(active),
            "retired": len(retired),
            "auto_extracted": len([s for s in active if s.source == "auto_extracted"]),
            "auto_distilled": len([s for s in active if s.source == "auto_distilled"]),
            "evolved": len([s for s in active if s.source == "evolved"]),
            "total_uses": sum(s.use_count for s in visible),
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
