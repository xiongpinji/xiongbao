"""Plan-and-Execute 编排模式。

与 ReAct（逐步思考-行动）不同，Plan-and-Execute：
1. 先让 LLM 生成完整执行计划（步骤列表）
2. 逐步执行计划中的每个步骤
3. 每步执行后可修正后续计划（replan）
4. 全部完成后汇总

优势：
- 对复杂多步任务更有条理
- 减少 LLM 往返（规划一次，执行多次）
- 支持步骤间并行（无依赖的步骤可同时执行）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.plan_execute")


@dataclass
class PlanStep:
    """计划中的单个步骤。"""
    id: int
    description: str
    tool_hint: str = ""  # 建议使用的工具
    depends_on: list[int] = field(default_factory=list)
    status: str = "pending"  # pending | running | done | failed
    result: str = ""


@dataclass
class ExecutionPlan:
    """完整执行计划。"""
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    revision: int = 0

    @property
    def pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "pending"]

    @property
    def ready_steps(self) -> list[PlanStep]:
        """可立即执行的步骤（依赖已完成）。"""
        done_ids = {s.id for s in self.steps if s.status == "done"}
        return [
            s for s in self.steps
            if s.status == "pending" and all(d in done_ids for d in s.depends_on)
        ]

    @property
    def is_complete(self) -> bool:
        return all(s.status in ("done", "failed") for s in self.steps)

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status in ("done", "failed"))
        return done / len(self.steps)


# ─── 计划生成 Prompt ───
PLAN_SYSTEM_PROMPT = """\
你是一个任务规划专家。给定用户目标，生成一个结构化的执行计划。

输出严格 JSON 格式（无其他文字）：
{"steps": [{"id": 1, "description": "步骤描述", "tool_hint": "建议工具", "depends_on": []}]}

规则：
- 步骤数 3-8 个，每步明确可执行
- depends_on 引用前置步骤 id（无依赖则为空数组）
- tool_hint 从可用工具中选择（可为空表示纯推理）
- 可并行的步骤不要设置依赖
"""

REPLAN_SYSTEM_PROMPT = """\
你是一个任务规划专家。根据当前执行进度，决定是否需要调整后续计划。

当前目标: {goal}
已完成步骤:
{completed}
剩余步骤:
{remaining}

如果计划仍然有效，输出: {"action": "continue"}
如果需要调整，输出: {"action": "revise", "steps": [...新步骤...]}
如果目标已达成，输出: {"action": "finish", "summary": "完成摘要"}
"""


async def generate_plan(
    goal: str,
    available_tools: list[str],
    llm_client: Any,
) -> ExecutionPlan:
    """使用 LLM 生成执行计划。"""
    from xagent.adapters.llm import Message

    tools_str = ", ".join(available_tools) if available_tools else "无特定工具"
    user_msg = f"目标: {goal}\n可用工具: {tools_str}"

    resp = await llm_client.complete(
        [
            Message(role="system", content=PLAN_SYSTEM_PROMPT),
            Message(role="user", content=user_msg),
        ],
        temperature=0.3,
    )

    plan = ExecutionPlan(goal=goal)
    try:
        import re
        raw = resp.content or ""
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            data = json.loads(m.group())
            for item in data.get("steps", []):
                plan.steps.append(PlanStep(
                    id=item.get("id", len(plan.steps) + 1),
                    description=item.get("description", ""),
                    tool_hint=item.get("tool_hint", ""),
                    depends_on=item.get("depends_on", []),
                ))
    except Exception as exc:
        logger.warning("plan_parse_failed", error=str(exc))
        # 兜底：单步计划
        plan.steps = [PlanStep(id=1, description=goal)]

    logger.info("plan_generated", goal=goal[:80], steps=len(plan.steps))
    return plan


async def replan(
    plan: ExecutionPlan,
    llm_client: Any,
) -> str:
    """执行过程中检查是否需要修正计划。返回 action: continue/revise/finish。"""
    from xagent.adapters.llm import Message

    completed = "\n".join(
        f"  [{s.id}] {s.description} → {s.result[:100]}"
        for s in plan.steps if s.status == "done"
    ) or "  (无)"
    remaining = "\n".join(
        f"  [{s.id}] {s.description}"
        for s in plan.steps if s.status == "pending"
    ) or "  (无)"

    prompt = REPLAN_SYSTEM_PROMPT.format(
        goal=plan.goal, completed=completed, remaining=remaining
    )

    try:
        resp = await llm_client.complete(
            [Message(role="user", content=prompt)],
            temperature=0.2,
        )
        import re
        raw = resp.content or ""
        m = re.search(r'\{[\s\S]*?\}', raw)
        if m:
            data = json.loads(m.group())
            action = data.get("action", "continue")
            if action == "revise":
                plan.revision += 1
                # 替换剩余步骤
                plan.steps = [s for s in plan.steps if s.status == "done"]
                for item in data.get("steps", []):
                    plan.steps.append(PlanStep(
                        id=item.get("id", len(plan.steps) + 1),
                        description=item.get("description", ""),
                        tool_hint=item.get("tool_hint", ""),
                        depends_on=item.get("depends_on", []),
                    ))
                logger.info("plan_revised", revision=plan.revision, new_steps=len(plan.steps))
            return action
    except Exception as exc:
        logger.debug("replan_failed", error=str(exc))

    return "continue"
