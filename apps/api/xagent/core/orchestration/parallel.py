"""多 Agent 并行执行引擎。

对标 Codex multi-agent worktrees / Hermes subagent delegation：
- 接收多个子任务，并行调度多个 Agent 实例
- 每个子 Agent 独立上下文、独立 run_id
- 汇总结果后由 coordinator 综合输出
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from xagent.core.orchestration import run_agent
from xagent.enterprise.auth.principal import Principal
from xagent.infra.logging import get_logger

logger = get_logger("xagent.parallel")

# 最大并行 Agent 数（防资源耗尽）
MAX_PARALLEL_AGENTS = 5
# 单个子任务超时
SUB_TASK_TIMEOUT = 180


@dataclass
class SubTask:
    goal: str
    role: str | None = None
    capabilities: list[str] = field(default_factory=list)


@dataclass
class SubTaskResult:
    goal: str
    run_id: str
    status: str  # succeeded | failed | timeout
    final_answer: str = ""
    steps: int = 0
    error: str = ""
    duration_ms: float = 0


@dataclass
class ParallelRunResult:
    run_id: str
    status: str
    sub_results: list[SubTaskResult] = field(default_factory=list)
    summary: str = ""
    total_duration_ms: float = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "sub_results": [
                {
                    "goal": r.goal,
                    "run_id": r.run_id,
                    "status": r.status,
                    "final_answer": r.final_answer[:2000],
                    "steps": r.steps,
                    "error": r.error,
                    "duration_ms": round(r.duration_ms, 1),
                }
                for r in self.sub_results
            ],
            "summary": self.summary,
            "total_duration_ms": round(self.total_duration_ms, 1),
        }


async def run_parallel_agents(
    sub_tasks: list[SubTask],
    principal: Principal,
    *,
    coordinator_goal: str = "",
    on_event=None,
) -> ParallelRunResult:
    """并行执行多个子 Agent 任务，汇总结果。"""
    run_id = uuid.uuid4().hex
    start = datetime.now(UTC)

    if len(sub_tasks) > MAX_PARALLEL_AGENTS:
        sub_tasks = sub_tasks[:MAX_PARALLEL_AGENTS]
        logger.warning("parallel_truncated", max=MAX_PARALLEL_AGENTS)

    async def _run_one(idx: int, task: SubTask) -> SubTaskResult:
        sub_run_id = f"{run_id}_sub{idx}"
        t0 = datetime.now(UTC)
        try:
            result = await asyncio.wait_for(
                run_agent(
                    task.goal,
                    principal=principal,
                    role_name=task.role,
                    capabilities=set(task.capabilities) or None,
                    run_id=sub_run_id,
                ),
                timeout=SUB_TASK_TIMEOUT,
            )
            elapsed = (datetime.now(UTC) - t0).total_seconds() * 1000
            rd = result.to_dict()
            return SubTaskResult(
                goal=task.goal,
                run_id=sub_run_id,
                status="succeeded",
                final_answer=str(rd.get("final_answer") or ""),
                steps=rd.get("steps", 0) if isinstance(rd.get("steps"), int) else len(rd.get("steps") or []),
                duration_ms=elapsed,
            )
        except asyncio.TimeoutError:
            elapsed = (datetime.now(UTC) - t0).total_seconds() * 1000
            return SubTaskResult(
                goal=task.goal, run_id=sub_run_id, status="timeout",
                error=f"超时(>{SUB_TASK_TIMEOUT}s)", duration_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (datetime.now(UTC) - t0).total_seconds() * 1000
            return SubTaskResult(
                goal=task.goal, run_id=sub_run_id, status="failed",
                error=str(exc)[:500], duration_ms=elapsed,
            )

    # 并行调度所有子任务
    results = await asyncio.gather(
        *[_run_one(i, t) for i, t in enumerate(sub_tasks)],
        return_exceptions=False,
    )

    total_ms = (datetime.now(UTC) - start).total_seconds() * 1000
    succeeded = sum(1 for r in results if r.status == "succeeded")
    overall_status = "succeeded" if succeeded == len(results) else (
        "partial" if succeeded > 0 else "failed"
    )

    # 生成汇总
    summary_parts = []
    for r in results:
        if r.status == "succeeded":
            summary_parts.append(f"✓ {r.goal[:60]}: {r.final_answer[:200]}")
        else:
            summary_parts.append(f"✗ {r.goal[:60]}: {r.error[:100]}")
    summary = f"并行完成 {succeeded}/{len(results)} 个子任务。\n" + "\n".join(summary_parts)

    return ParallelRunResult(
        run_id=run_id,
        status=overall_status,
        sub_results=list(results),
        summary=summary,
        total_duration_ms=total_ms,
    )
