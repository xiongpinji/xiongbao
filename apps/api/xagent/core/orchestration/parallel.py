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
from pathlib import Path
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
    # ── V3-3 worktree 隔离字段 ──
    isolated: bool = False       # 是否在独立 git worktree 中执行
    worktree_path: str = ""      # 执行用 worktree（已清理，仅留记录）
    diff_stat: str = ""          # 该子代理的改动统计（git diff --stat）
    diff: str = ""               # 改动全文（截断 4000 字符）


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
                    "worktree_path": r.worktree_path,
                    "diff_stat": r.diff_stat,
                    "diff": r.diff,
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

    use_worktrees=True（V3-3，对标 Codex multi-agent worktrees）：
    每个子代理在当前工作区的独立 git worktree 中执行（独立分支），
    结束后采集各自 diff 并清理 worktree；主工作区不被并行写入污染。
    当前工作区不是 git 仓库时降级为非隔离执行（记日志，诚实标记 isolated=False）。
    """
    run_id = uuid.uuid4().hex
    start = datetime.now(UTC)

    if len(sub_tasks) > MAX_PARALLEL_AGENTS:
        sub_tasks = sub_tasks[:MAX_PARALLEL_AGENTS]
        logger.warning("parallel_truncated", max=MAX_PARALLEL_AGENTS)

    # worktree 隔离前置：当前工作区必须是 git 仓库
    main_ws: Path | None = None
    worktree_base: Path | None = None
    if use_worktrees:
        from xagent.core.workspace import get_workspace

        main_ws = get_workspace()
        rc, _ = await _git(main_ws, "rev-parse", "--is-inside-work-tree")
        if rc == 0:
            worktree_base = main_ws.parent / ".xagent-worktrees"
        else:
            logger.warning(
                "parallel_worktree_degraded",
                reason="workspace_not_git_repo", workspace=str(main_ws),
            )

    async def _run_one(idx: int, task: SubTask) -> SubTaskResult:
        sub_run_id = f"{run_id}_sub{idx}"
        t0 = datetime.now(UTC)
        wt_path: Path | None = None
        branch = f"agent/{run_id[:8]}-sub{idx}"
        wt_token = None
        try:
            # V3-3：建独立 worktree 并切换本任务工作区（contextvar 任务级隔离）
            if worktree_base is not None:
                from xagent.core.workspace import get_workspace, set_workspace

                wt_path = worktree_base / f"{run_id[:8]}-sub{idx}"
                rc, out = await _git(
                    get_workspace(), "worktree", "add", "-b", branch, str(wt_path), "HEAD"
                )
                if rc == 0:
                    wt_token = set_workspace(wt_path)
                else:
                    logger.warning(
                        "parallel_worktree_add_failed", sub_run_id=sub_run_id, detail=out[:200]
                    )
                    wt_path = None
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
            finally:
                if wt_token is not None:
                    from xagent.core.workspace import reset_workspace

                    reset_workspace(wt_token)
            elapsed = (datetime.now(UTC) - t0).total_seconds() * 1000
            rd = result.to_dict()
            # 采集该子代理 worktree 的改动（先 add -A 让未跟踪文件也进 diff）
            diff_stat, diff_text = "", ""
            if wt_path is not None:
                diff_stat, diff_text = await _collect_worktree_diff(wt_path)
            return SubTaskResult(
                goal=task.goal,
                run_id=sub_run_id,
                status="succeeded",
                final_answer=str(rd.get("final_answer") or ""),
                steps=rd.get("steps", 0)
                if isinstance(rd.get("steps"), int)
                else len(rd.get("steps") or []),
                duration_ms=elapsed,
                isolated=wt_path is not None,
                worktree_path=str(wt_path) if wt_path else "",
                diff_stat=diff_stat,
                diff=diff_text,
            )
        except TimeoutError:
            elapsed = (datetime.now(UTC) - t0).total_seconds() * 1000
            return SubTaskResult(
                goal=task.goal, run_id=sub_run_id, status="timeout",
                error=f"超时(>{SUB_TASK_TIMEOUT}s)", duration_ms=elapsed,
                isolated=wt_path is not None,
                worktree_path=str(wt_path) if wt_path else "",
            )
        except Exception as exc:
            elapsed = (datetime.now(UTC) - t0).total_seconds() * 1000
            return SubTaskResult(
                goal=task.goal, run_id=sub_run_id, status="failed",
                error=str(exc)[:500], duration_ms=elapsed,
                isolated=wt_path is not None,
                worktree_path=str(wt_path) if wt_path else "",
            )
        finally:
            if wt_path is not None and main_ws is not None:
                await _cleanup_worktree(main_ws, wt_path, branch)

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


# ═══════════════════════════════════════════════════════════
#  worktree 隔离的 git 助手（V3-3）
# ═══════════════════════════════════════════════════════════

_DIFF_MAX_CHARS = 4000


async def _git(cwd: Path, *args: str) -> tuple[int, str]:
    """异步执行 git 命令，返回 (returncode, stdout+stderr)。"""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace")


async def _collect_worktree_diff(wt_path: Path) -> tuple[str, str]:
    """采集 worktree 内的全部改动（add -A 后 vs HEAD），返回 (stat, diff 截断)。"""
    rc, _ = await _git(wt_path, "add", "-A")
    if rc != 0:
        return "", ""
    _, stat = await _git(wt_path, "diff", "--cached", "--stat", "HEAD")
    _, full = await _git(wt_path, "diff", "--cached", "HEAD")
    return stat.strip(), full[:_DIFF_MAX_CHARS]


async def _cleanup_worktree(main_ws: Path, wt_path: Path, branch: str) -> None:
    """清理 worktree 与临时分支（best-effort，一律从主仓库执行 git）。"""
    try:
        await _git(main_ws, "worktree", "remove", "--force", str(wt_path))
        if await asyncio.to_thread(wt_path.exists):
            import shutil

            shutil.rmtree(wt_path, ignore_errors=True)
            await _git(main_ws, "worktree", "prune")
        await _git(main_ws, "branch", "-D", branch)
    except Exception as exc:  # noqa: BLE001
        logger.warning("parallel_worktree_cleanup_failed", detail=str(exc)[:200])


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
            l.strip().lstrip("0123456789.-) ")
            for l in (resp.content or "").splitlines()
            if l.strip() and len(l.strip()) > 5
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
