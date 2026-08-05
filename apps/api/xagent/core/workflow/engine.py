"""工作流执行引擎。

执行模型（saga 风格）：
1. 拓扑排序步骤（按 depends_on）。
2. 同层无依赖且无审批门的步骤并行执行（asyncio.gather）。
3. 遇审批门：暂停为 awaiting_approval，等 approve()/deny() 信号。
4. 步骤失败且有补偿：回滚已成功的步骤（逆序执行 compensation），最终 rolled_back。
5. 步骤失败无补偿：failed，不回滚（人工介入）。
6. 全程写 timeline 事件；可 replay(run_id) 重放事件序列恢复视图。

lite：进程内执行；full 目标 Temporal（同接口，活动 = step）。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from xagent.core.orchestration import run_agent
from xagent.core.workflow.models import (
    StepStatus,
    WorkflowRun,
    WorkflowSpec,
    WorkflowStatus,
    WorkflowStep,
)
from xagent.enterprise.auth.principal import Principal
from xagent.infra.logging import get_logger
from xagent.infra.settings import get_settings

logger = get_logger("xagent.workflow")


def _hatchet_available() -> bool:
    try:
        from xagent.adapters.workflow import get_hatchet_backend
        backend = get_hatchet_backend()
        return backend._has_hatchet and get_settings().is_production
    except Exception:
        return False


def _topo_order(steps: list[WorkflowStep]) -> list[WorkflowStep]:
    """简单拓扑排序；忽略环检测（spec 由可信方定义）。"""
    by_id = {s.id: s for s in steps}
    done: set[str] = set()
    ordered: list[WorkflowStep] = []

    def visit(s: WorkflowStep) -> None:
        if s.id in done:
            return
        for dep in s.depends_on:
            if dep in by_id:
                visit(by_id[dep])
        done.add(s.id)
        ordered.append(s)

    for s in steps:
        visit(s)
    return ordered


class WorkflowEngine:
    """进程内工作流引擎。运行状态按 run_id 保存，支持信号驱动审批与回放。"""

    def __init__(self) -> None:
        self._runs: dict[str, WorkflowRun] = {}

    def create_run(
        self,
        spec: WorkflowSpec,
        principal: Principal,
        run_id: str | None = None,
    ) -> WorkflowRun:
        from uuid import uuid4

        run = WorkflowRun(
            run_id=run_id or uuid4().hex,
            spec_name=spec.name,
            tenant_id=principal.tenant_id,
            steps=[_clone_step(s) for s in spec.steps],
        )
        self._runs[run.run_id] = run
        return run

    def get_run(self, run_id: str) -> WorkflowRun | None:
        return self._runs.get(run_id)

    def list_runs(self, tenant_id: str) -> list[WorkflowRun]:
        return [r for r in self._runs.values() if r.tenant_id == tenant_id]

    async def execute(self, run_id: str, principal: Principal) -> WorkflowRun:
        run = self._require(run_id, principal)
        if run.status not in (WorkflowStatus.pending, WorkflowStatus.awaiting_approval):
            raise RuntimeError(f"工作流 {run_id} 当前状态 {run.status.value} 不可执行")
        run.status = WorkflowStatus.running
        run.started_at = run.started_at or datetime.now(UTC)

        ordered = _topo_order(run.steps)
        completed: set[str] = {
            s.id for s in run.steps if s.status in (StepStatus.succeeded, StepStatus.skipped)
        }

        idx = 0
        while idx < len(ordered):
            # 收集本批次可并行的 step：依赖已完成、无审批门、尚未成功
            batch: list[WorkflowStep] = []
            scan = idx
            while scan < len(ordered):
                step = ordered[scan]
                if step.status in (StepStatus.succeeded, StepStatus.skipped):
                    completed.add(step.id)
                    scan += 1
                    continue
                deps_ok = all(d in completed for d in step.depends_on)
                if not deps_ok:
                    break  # 后续依赖未满足，停止本批
                if step.approval and step.status == StepStatus.pending:
                    if batch:
                        break  # 先把当前批跑完
                    # 审批门：单独处理
                    step.status = StepStatus.awaiting_approval
                    run.status = WorkflowStatus.awaiting_approval
                    run.add_event(step.id, "approval_requested", step.approval.message)
                    return run
                batch.append(step)
                scan += 1

            if not batch:
                # 没有可执行 step（被审批门挡住或异常），退出循环
                break

            # 标记并发起
            for step in batch:
                step.status = StepStatus.running
                step.started_at = datetime.now(UTC)
                run.add_event(step.id, "started")

            results = await asyncio.gather(
                *[
                    run_agent(step.goal, principal=principal, role_name=step.role)
                    for step in batch
                ],
                return_exceptions=True,
            )

            failed_step: WorkflowStep | None = None
            for step, result in zip(batch, results, strict=True):
                if isinstance(result, Exception):
                    step.error = str(result)
                    step.status = StepStatus.failed
                    step.finished_at = datetime.now(UTC)
                    run.add_event(step.id, "failed", step.error)
                    if failed_step is None:
                        failed_step = step
                else:
                    step.result = result.to_dict()
                    step.status = StepStatus.succeeded
                    step.finished_at = datetime.now(UTC)
                    run.add_event(step.id, "succeeded", result.final_answer[:200])
                    completed.add(step.id)

            if failed_step is not None:
                await self._compensate(run, failed_step, principal)
                run.finished_at = datetime.now(UTC)
                return run

            idx = scan

        # 全部完成
        if all(s.status in (StepStatus.succeeded, StepStatus.skipped) for s in run.steps):
            run.status = WorkflowStatus.completed
            run.finished_at = datetime.now(UTC)
            run.add_event("__root__", "completed")
        return run

    async def approve(self, run_id: str, step_id: str, principal: Principal) -> WorkflowRun:
        run = self._require(run_id, principal)
        step = run.step(step_id)
        step.status = StepStatus.running
        run.add_event(step_id, "approved", principal.user_id)
        return await self.execute(run_id, principal)

    async def deny(self, run_id: str, step_id: str, principal: Principal) -> WorkflowRun:
        run = self._require(run_id, principal)
        step = run.step(step_id)
        step.status = StepStatus.skipped
        step.error = "审批被拒绝"
        run.add_event(step_id, "denied", principal.user_id)
        run.status = WorkflowStatus.cancelled
        run.finished_at = datetime.now(UTC)
        return run

    async def _compensate(
        self, run: WorkflowRun, failed: WorkflowStep, principal: Principal
    ) -> None:
        """逆序补偿已成功步骤中带 compensation 的。"""
        compensated = False
        for step in reversed(run.steps):
            if step.id == failed.id:
                break
            if step.status == StepStatus.succeeded and step.compensation_goal:
                try:
                    await run_agent(
                        step.compensation_goal,
                        principal=principal,
                        role_name=step.compensation_role or "general",
                    )
                    step.status = StepStatus.compensated
                    run.add_event(step.id, "compensated")
                    compensated = True
                except Exception as exc:
                    run.add_event(step.id, "compensation_failed", str(exc))
        run.status = WorkflowStatus.rolled_back if compensated else WorkflowStatus.failed

    def replay(self, run_id: str, principal: Principal) -> dict[str, Any]:
        """重放事件序列恢复视图（回放）。"""
        run = self._require(run_id, principal)
        return run.to_view()

    def _require(self, run_id: str, principal: Principal) -> WorkflowRun:
        run = self._runs.get(run_id)
        if run is None or run.tenant_id != principal.tenant_id:
            raise KeyError("工作流不存在或无权访问")
        return run


def _clone_step(s: WorkflowStep) -> WorkflowStep:
    return WorkflowStep(
        id=s.id,
        name=s.name,
        role=s.role,
        goal=s.goal,
        depends_on=list(s.depends_on),
        compensation_role=s.compensation_role,
        compensation_goal=s.compensation_goal,
        approval=s.approval,
    )


@lru_cache
def get_engine() -> WorkflowEngine:
    return WorkflowEngine()


def reset_engine() -> None:
    get_engine.cache_clear()
