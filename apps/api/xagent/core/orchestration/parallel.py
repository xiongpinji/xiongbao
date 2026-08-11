"""多 Agent 并行执行引擎。

对标 Codex multi-agent worktrees / Hermes subagent delegation：
- 接收多个子任务，并行调度多个 Agent 实例
- 每个子 Agent 独立上下文、独立 run_id
- 汇总结果后由 coordinator 综合输出
"""

from __future__ import annotations

import asyncio
import json
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
# 严格隔离 file_write 需覆盖 240 秒 SLO，并为 Git finalize/HTTP 返回留余量。
STRICT_FILE_WRITE_TIMEOUT = 270
_RUNNING_DEVELOPMENT_TASKS: dict[str, asyncio.Task[Any]] = {}


def cancel_running_development_task(task_id: str) -> bool:
    task = _RUNNING_DEVELOPMENT_TASKS.get(task_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


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
    # ── V3-3 worktree 隔离字段 ──
    isolated: bool = False       # 是否在独立 git worktree 中执行
    worktree_path: str = ""      # 执行用 worktree（成功时保留到审查动作）
    diff_stat: str = ""          # 该子代理的改动统计（git diff --stat）
    diff: str = ""               # 改动全文（截断 4000 字符）
    development_task_id: str = ""
    development_task_status: str = ""


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
                    "isolated": r.isolated,
                    "diff_stat": r.diff_stat,
                    "diff": r.diff,
                    "development_task_id": r.development_task_id,
                    "development_task_status": r.development_task_status,
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
    use_worktrees: bool = False,
) -> ParallelRunResult:
    """并行执行多个子 Agent 任务，汇总结果。

    use_worktrees=True 时每个子代理从固定基线建立独立 git worktree；
    成功结果提交并保留等待审查，失败结果记录后清理。
    当前工作区不是 git 仓库时降级为非隔离执行（记日志，诚实标记 isolated=False）。
    """
    run_id = uuid.uuid4().hex
    start = datetime.now(UTC)

    if len(sub_tasks) > MAX_PARALLEL_AGENTS:
        sub_tasks = sub_tasks[:MAX_PARALLEL_AGENTS]
        logger.warning("parallel_truncated", max=MAX_PARALLEL_AGENTS)

    repository_baseline = None
    if use_worktrees:
        from xagent.core.workspace import get_workspace
        from xagent.domains.development_tasks.git_lifecycle import inspect_repository

        repository_baseline = await inspect_repository(get_workspace())
        if repository_baseline is None:
            logger.warning(
                "parallel_worktree_degraded",
                reason="workspace_not_git_repo",
                workspace=str(get_workspace()),
            )

    async def _run_one(idx: int, task: SubTask) -> SubTaskResult:
        sub_run_id = f"{run_id}_sub{idx}"
        t0 = datetime.now(UTC)
        development_task_id = uuid.uuid4().hex
        branch = f"agent/{development_task_id}"
        task_paths = None
        task_persisted = False
        keep_worktree = False
        wt_token = None
        task_timeout = SUB_TASK_TIMEOUT
        try:
            if repository_baseline is not None:
                from datetime import timedelta

                from xagent.core.workspace import set_workspace
                from xagent.domains.development_tasks import (
                    DevelopmentTaskCreate,
                    create_development_task,
                )
                from xagent.domains.development_tasks.git_lifecycle import (
                    create_task_worktree,
                    development_task_paths,
                )
                from xagent.infra.db import get_sessionmaker

                task_paths = development_task_paths(
                    repository_baseline.root, development_task_id
                )
                await create_task_worktree(repository_baseline, task_paths, branch)
                async with get_sessionmaker()() as session:
                    await create_development_task(
                        session,
                        DevelopmentTaskCreate(
                            task_id=development_task_id,
                            parent_run_id=run_id,
                            sub_run_id=sub_run_id,
                            tenant_id=principal.tenant_id,
                            owner_id=principal.user_id,
                            goal=task.goal,
                            main_workspace=str(repository_baseline.root),
                            base_commit=repository_baseline.commit,
                            target_branch=repository_baseline.branch,
                            work_branch=branch,
                            worktree_path=str(task_paths.worktree),
                            patch_path=str(task_paths.patch),
                            expires_at=datetime.now(UTC) + timedelta(days=7),
                        ),
                    )
                    await session.commit()
                task_persisted = True
                current_task = asyncio.current_task()
                if current_task is not None:
                    _RUNNING_DEVELOPMENT_TASKS[development_task_id] = current_task
                wt_token = set_workspace(task_paths.worktree)
            try:
                required_first_tool = (
                    "file_write"
                    if repository_baseline is not None
                    and set(task.capabilities) == {"file_write"}
                    else None
                )
                agent_kwargs: dict[str, Any] = {}
                if required_first_tool is not None:
                    agent_kwargs["required_first_tool"] = required_first_tool
                    task_timeout = STRICT_FILE_WRITE_TIMEOUT
                result = await asyncio.wait_for(
                    run_agent(
                        task.goal,
                        principal=principal,
                        role_name=task.role,
                        capabilities=set(task.capabilities) or None,
                        run_id=sub_run_id,
                        **agent_kwargs,
                    ),
                    timeout=task_timeout,
                )
            finally:
                if wt_token is not None:
                    from xagent.core.workspace import reset_workspace

                    reset_workspace(wt_token)
            elapsed = (datetime.now(UTC) - t0).total_seconds() * 1000
            rd = result.to_dict()
            if task_paths is not None and rd.get("status") != "succeeded":
                raise RuntimeError(
                    str(rd.get("error") or "isolated_agent_run_failed")[:500]
                )
            if required_first_tool is not None and not any(
                event.get("kind") == "tool_call"
                and event.get("tool") == required_first_tool
                for event in rd.get("events", [])
            ):
                raise RuntimeError(
                    f"隔离开发任务未调用必需工具 {required_first_tool}"
                    "（已执行一次受控纠偏重试）"
                )
            diff_stat, diff_text = "", ""
            if task_paths is not None and repository_baseline is not None:
                from xagent.domains.development_tasks import (
                    DevelopmentTaskStatus,
                    update_development_task,
                )
                from xagent.domains.development_tasks.git_lifecycle import (
                    finalize_task_worktree,
                )
                from xagent.infra.db import get_sessionmaker

                finalized = await finalize_task_worktree(
                    repository_baseline, task_paths, development_task_id
                )
                diff_stat = finalized.diff_stat
                diff_text = finalized.patch_text[:_DIFF_MAX_CHARS]
                async with get_sessionmaker()() as session:
                    await update_development_task(
                        session,
                        principal.tenant_id,
                        development_task_id,
                        status=DevelopmentTaskStatus.awaiting_review,
                        result_commit=finalized.result_commit,
                        diff_stat=diff_stat,
                        test_summary=json.dumps(
                            {
                                "agent_status": rd.get("status", "succeeded"),
                                "steps": rd.get("steps", 0),
                            }
                        ),
                    )
                    await session.commit()
                keep_worktree = True
            return SubTaskResult(
                goal=task.goal,
                run_id=sub_run_id,
                status="succeeded",
                final_answer=str(rd.get("final_answer") or ""),
                steps=rd.get("steps", 0)
                if isinstance(rd.get("steps"), int)
                else len(rd.get("steps") or []),
                duration_ms=elapsed,
                isolated=task_paths is not None,
                worktree_path=str(task_paths.worktree) if task_paths else "",
                diff_stat=diff_stat,
                diff=diff_text,
                development_task_id=development_task_id if task_persisted else "",
                development_task_status="awaiting_review" if task_persisted else "",
            )
        except asyncio.CancelledError:
            elapsed = (datetime.now(UTC) - t0).total_seconds() * 1000
            if task_persisted:
                await _mark_development_task(
                    principal.tenant_id,
                    development_task_id,
                    "cancelled",
                    "任务已由用户取消",
                )
            return SubTaskResult(
                goal=task.goal,
                run_id=sub_run_id,
                status="cancelled",
                error="任务已由用户取消",
                duration_ms=elapsed,
                isolated=task_paths is not None,
                worktree_path=str(task_paths.worktree) if task_paths else "",
                development_task_id=development_task_id if task_persisted else "",
                development_task_status="cancelled" if task_persisted else "",
            )
        except TimeoutError:
            elapsed = (datetime.now(UTC) - t0).total_seconds() * 1000
            if task_persisted:
                await _mark_development_task(
                    principal.tenant_id,
                    development_task_id,
                    "timeout",
                    f"超时(>{task_timeout}s)",
                )
            return SubTaskResult(
                goal=task.goal,
                run_id=sub_run_id,
                status="timeout",
                error=f"超时(>{task_timeout}s)",
                duration_ms=elapsed,
                isolated=task_paths is not None,
                worktree_path=str(task_paths.worktree) if task_paths else "",
                development_task_id=development_task_id if task_persisted else "",
                development_task_status="timeout" if task_persisted else "",
            )
        except Exception as exc:
            elapsed = (datetime.now(UTC) - t0).total_seconds() * 1000
            if task_persisted:
                await _mark_development_task(
                    principal.tenant_id,
                    development_task_id,
                    "failed",
                    str(exc)[:500],
                )
            return SubTaskResult(
                goal=task.goal,
                run_id=sub_run_id,
                status="failed",
                error=str(exc)[:500],
                duration_ms=elapsed,
                isolated=task_paths is not None,
                worktree_path=str(task_paths.worktree) if task_paths else "",
                development_task_id=development_task_id if task_persisted else "",
                development_task_status="failed" if task_persisted else "",
            )
        finally:
            _RUNNING_DEVELOPMENT_TASKS.pop(development_task_id, None)
            if (
                task_paths is not None
                and repository_baseline is not None
                and not keep_worktree
            ):
                from xagent.domains.development_tasks.git_lifecycle import (
                    cleanup_task_worktree,
                )

                await cleanup_task_worktree(
                    repository_baseline.root, task_paths, branch, strict=False
                )
                try:
                    await asyncio.to_thread(
                        task_paths.patch.unlink, missing_ok=True
                    )
                except OSError as exc:
                    logger.warning(
                        "parallel_patch_cleanup_failed",
                        task_id=development_task_id,
                        error=str(exc),
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


_DIFF_MAX_CHARS = 4000


async def _mark_development_task(
    tenant_id: str, task_id: str, status: str, error: str
) -> None:
    from xagent.domains.development_tasks import (
        DevelopmentTaskStatus,
        update_development_task,
    )
    from xagent.infra.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        await update_development_task(
            session,
            tenant_id,
            task_id,
            status=DevelopmentTaskStatus(status),
            error=error,
        )
        await session.commit()


# ═══════════════════════════════════════════════════════════
#  自动任务分解（对标 Codex 多文件并行编辑）
# ═══════════════════════════════════════════════════════════


async def auto_decompose_and_run(
    goal: str,
    principal: Principal,
    *,
    on_event=None,
) -> ParallelRunResult | None:
    """智能判断是否应并行执行，如果是则自动分解并并行执行。

    返回 None 表示不适合并行（应由单 Agent 顺序执行）。
    """
    import re as _re

    # 判断是否含多个独立子任务
    # 信号：数字列表、1) 2) 3)、多个“并”“同时”“分别”
    has_numbered = bool(_re.search(r'[1-9][)\.]\s', goal))
    has_parallel_words = any(w in goal for w in ("分别", "并行", "同时", "各自"))
    has_multi_sep = goal.count("、") >= 3 or goal.count("；") >= 2

    if not (has_numbered or has_parallel_words or has_multi_sep):
        return None  # 不适合并行

    # 用 LLM 分解任务
    from xagent.adapters.llm import Message, get_llm_client

    llm = get_llm_client()
    decompose_prompt = (
        "将以下任务分解为 2-5 个可以独立并行执行的子任务。"
        "每个子任务必须是完整的、可独立执行的。"
        "输出格式：每行一个子任务，不要编号。\n\n"
        f"任务：{goal}"
    )
    try:
        resp = await llm.complete([Message(role="user", content=decompose_prompt)])
        lines = [
            line.strip().lstrip("0123456789.-) ")
            for line in (resp.content or "").splitlines()
            if line.strip() and len(line.strip()) > 5
        ]
        if len(lines) < 2:
            return None  # 分解失败，回退单 Agent
        sub_tasks = [SubTask(goal=line) for line in lines[:MAX_PARALLEL_AGENTS]]
    except Exception:
        return None

    logger.info("auto_decompose", count=len(sub_tasks), goal=goal[:80])
    return await run_parallel_agents(
        sub_tasks, principal, coordinator_goal=goal, on_event=on_event
    )
