"""Supervisor 多 Agent 协作模式。

架构：
    Supervisor（规划 + 分发 + 汇总）
        ├── Worker Agent A（子任务1）
        ├── Worker Agent B（子任务2）
        └── Worker Agent C（子任务3）

流程：
    1. Supervisor 接收用户目标
    2. LLM 分解为子任务列表（含角色/依赖）
    3. 按依赖拓扑并行分发给 Worker
    4. 收集结果 → Supervisor 综合为最终答案
    5. 若有失败子任务 → 决策重试/跳过/中止
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.supervisor")

MAX_WORKERS = 5
WORKER_TIMEOUT = 180


@dataclass
class WorkerTask:
    """Supervisor 分配给 Worker 的子任务。"""
    task_id: str
    goal: str
    role: str = "general"
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | running | done | failed
    result: str = ""
    error: str = ""


@dataclass
class SupervisorResult:
    """Supervisor 协作最终结果。"""
    run_id: str
    goal: str
    status: str  # succeeded | partial | failed
    plan: list[dict] = field(default_factory=list)
    worker_results: list[dict] = field(default_factory=list)
    final_answer: str = ""
    duration_ms: float = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "status": self.status,
            "plan": self.plan,
            "worker_results": self.worker_results,
            "final_answer": self.final_answer,
            "duration_ms": round(self.duration_ms, 1),
        }


DECOMPOSE_PROMPT = """\
你是一个任务规划 Supervisor。将用户目标分解为 2-5 个可并行执行的子任务。

用户目标：{goal}

可用角色：{roles}

输出 JSON 数组，每项包含：
- "goal": 子任务目标（清晰具体）
- "role": 建议角色
- "depends_on": 依赖的子任务索引列表（0-based，空=无依赖可并行）

仅输出 JSON，不要其他文字。
"""

SYNTHESIZE_PROMPT = """\
你是 Supervisor，需要综合所有 Worker 的执行结果，给出最终答案。

原始目标：{goal}

各 Worker 结果：
{results}

请综合以上结果，给出完整、连贯的最终答案。如有失败任务请说明影响。
"""


async def decompose_task(
    goal: str,
    roles: list[str],
    llm_client: Any,
) -> list[WorkerTask]:
    """用 LLM 将目标分解为子任务。"""
    prompt = DECOMPOSE_PROMPT.format(goal=goal, roles=", ".join(roles))
    try:
        from xagent.adapters.llm import Message
        resp = await llm_client.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.3,
        )
        text = resp.content if hasattr(resp, "content") else str(resp)
        # 提取 JSON
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        items = json.loads(text)
        tasks = []
        for i, item in enumerate(items[:MAX_WORKERS]):
            tasks.append(WorkerTask(
                task_id=f"task_{i}",
                goal=item.get("goal", f"子任务{i}"),
                role=item.get("role", "general"),
                depends_on=item.get("depends_on", []),
            ))
        return tasks
    except Exception as exc:
        logger.warning("decompose_fallback", error=str(exc))
        # 降级：单任务
        return [WorkerTask(task_id="task_0", goal=goal)]


async def synthesize_results(
    goal: str,
    results: list[dict],
    llm_client: Any,
) -> str:
    """综合 Worker 结果生成最终答案。"""
    results_text = "\n".join(
        f"- [{r['status']}] {r['goal']}: {r.get('result', r.get('error', ''))[:300]}"
        for r in results
    )
    prompt = SYNTHESIZE_PROMPT.format(goal=goal, results=results_text)
    try:
        from xagent.adapters.llm import Message
        resp = await llm_client.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.4,
        )
        return resp.content if hasattr(resp, "content") else str(resp)
    except Exception:
        # 降级：拼接
        return "\n".join(
            f"• {r['goal']}: {r.get('result', r.get('error', 'N/A'))[:200]}"
            for r in results
        )


async def run_supervisor(
    goal: str,
    principal: Any,
    *,
    roles: list[str] | None = None,
    on_event: Any = None,
) -> SupervisorResult:
    """执行 Supervisor 多 Agent 协作。"""
    from xagent.adapters.llm import get_llm_client
    from xagent.core.orchestration import run_agent

    run_id = uuid.uuid4().hex
    t0 = time.time()
    llm = get_llm_client()
    available_roles = roles or ["general", "coder", "researcher", "writer"]

    # 1. 分解任务
    if on_event:
        await on_event({"event": "supervisor_plan", "data": {"goal": goal}})
    tasks = await decompose_task(goal, available_roles, llm)
    plan = [
        {"task_id": t.task_id, "goal": t.goal, "role": t.role, "depends_on": t.depends_on}
        for t in tasks
    ]
    if on_event:
        await on_event({"event": "supervisor_tasks", "data": {"tasks": plan}})

    # 2. 按依赖拓扑执行
    completed: dict[str, str] = {}  # task_id → result

    async def _run_worker(task: WorkerTask) -> None:
        task.status = "running"
        try:
            result = await asyncio.wait_for(
                run_agent(
                    task.goal,
                    principal=principal,
                    role_name=task.role,
                    run_id=f"{run_id}_{task.task_id}",
                ),
                timeout=WORKER_TIMEOUT,
            )
            rd = result.to_dict()
            task.result = str(rd.get("final_answer", ""))[:2000]
            task.status = "done"
            completed[task.task_id] = task.result
        except TimeoutError:
            task.status = "failed"
            task.error = f"超时(>{WORKER_TIMEOUT}s)"
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)[:500]

    # 简单拓扑：先执行无依赖的，再执行有依赖的
    no_deps = [t for t in tasks if not t.depends_on]
    has_deps = [t for t in tasks if t.depends_on]

    await asyncio.gather(*[_run_worker(t) for t in no_deps])
    if has_deps:
        await asyncio.gather(*[_run_worker(t) for t in has_deps])

    # 3. 综合结果
    worker_results = [
        {"task_id": t.task_id, "goal": t.goal, "role": t.role,
         "status": t.status, "result": t.result, "error": t.error}
        for t in tasks
    ]
    final_answer = await synthesize_results(goal, worker_results, llm)

    succeeded = sum(1 for t in tasks if t.status == "done")
    status = "succeeded" if succeeded == len(tasks) else (
        "partial" if succeeded > 0 else "failed"
    )
    duration_ms = (time.time() - t0) * 1000

    result = SupervisorResult(
        run_id=run_id,
        goal=goal,
        status=status,
        plan=plan,
        worker_results=worker_results,
        final_answer=final_answer,
        duration_ms=duration_ms,
    )
    logger.info(
        "supervisor_done", run_id=run_id, status=status,
        workers=len(tasks), succeeded=succeeded, duration_ms=round(duration_ms),
    )
    return result
