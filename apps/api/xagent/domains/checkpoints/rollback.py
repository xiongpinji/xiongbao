"""Checkpoint 的受控 Git commit/patch 回滚。"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.domains.checkpoints.models import CheckpointRecord
from xagent.domains.checkpoints.service import _record
from xagent.domains.development_tasks.git_lifecycle import (
    run_git,
    validate_record_paths,
)
from xagent.domains.development_tasks.models import DevelopmentTaskStatus
from xagent.domains.development_tasks.service import get_development_task
from xagent.infra.models.checkpoint import CheckpointORM


class CheckpointRollbackError(RuntimeError):
    pass


def _normalize_git_paths(paths: list[str]) -> set[str]:
    normalized: set[str] = set()
    for raw in paths:
        value = raw.strip().replace("\\", "/")
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts:
            raise CheckpointRollbackError("Git artifact 包含路径逃逸")
        normalized.add(path.as_posix())
    return normalized


async def _require_clean_target(repo: Path, target_branch: str) -> None:
    rc, branch = await run_git(repo, "branch", "--show-current")
    if rc != 0 or branch.strip() != target_branch:
        raise CheckpointRollbackError("目标分支不匹配")
    rc, status = await run_git(repo, "status", "--porcelain")
    if rc != 0:
        raise CheckpointRollbackError("无法读取 Git 工作区状态")
    if status.strip():
        raise CheckpointRollbackError("工作区存在未提交改动，拒绝 rollback")


async def _rollback_commit(repo: Path, commit: str, allowed: set[str]) -> str:
    rc, _ = await run_git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    if rc != 0:
        raise CheckpointRollbackError("已验证 applied commit 不存在")
    rc, ancestor = await run_git(repo, "merge-base", "--is-ancestor", commit, "HEAD")
    if rc != 0:
        raise CheckpointRollbackError(f"applied commit 不在当前分支: {ancestor[:200]}")
    rc, changed = await run_git(
        repo, "diff-tree", "--no-commit-id", "--name-only", "-r", commit
    )
    if rc != 0:
        raise CheckpointRollbackError("无法读取 applied commit 文件清单")
    paths = _normalize_git_paths(changed.splitlines())
    if not paths or not paths.issubset(allowed):
        raise CheckpointRollbackError("Git artifact 文件超出 checkpoint 记录")
    rc, output = await run_git(repo, "revert", "--no-edit", commit)
    if rc != 0:
        await run_git(repo, "revert", "--abort")
        raise CheckpointRollbackError(f"git revert 失败: {output[:300]}")
    rc, head = await run_git(repo, "rev-parse", "HEAD")
    if rc != 0:
        raise CheckpointRollbackError("无法读取 rollback commit")
    return head.strip()


async def _rollback_patch(repo: Path, patch: Path, allowed: set[str]) -> str:
    rc, numstat = await run_git(repo, "apply", "--numstat", str(patch))
    if rc != 0:
        raise CheckpointRollbackError("无法读取受控 patch 文件清单")
    paths = _normalize_git_paths(
        [line.split("\t", 2)[-1] for line in numstat.splitlines() if line.strip()]
    )
    if not paths or not paths.issubset(allowed):
        raise CheckpointRollbackError("Git artifact 文件超出 checkpoint 记录")
    rc, output = await run_git(repo, "apply", "--check", "--reverse", str(patch))
    if rc != 0:
        raise CheckpointRollbackError(f"patch 无法安全反向应用: {output[:300]}")
    rc, output = await run_git(repo, "apply", "--reverse", str(patch))
    if rc != 0:
        raise CheckpointRollbackError(f"反向应用 patch 失败: {output[:300]}")
    rc, output = await run_git(repo, "add", "--", *sorted(paths))
    if rc != 0:
        await run_git(repo, "apply", str(patch))
        raise CheckpointRollbackError(f"暂存 rollback patch 失败: {output[:300]}")
    rc, output = await run_git(
        repo,
        "-c",
        "user.name=X-Agent",
        "-c",
        "user.email=xagent@local",
        "commit",
        "--no-gpg-sign",
        "-m",
        "xagent: rollback checkpoint",
    )
    if rc != 0:
        await run_git(repo, "apply", str(patch))
        await run_git(repo, "add", "--", *sorted(paths))
        raise CheckpointRollbackError(f"提交 rollback patch 失败: {output[:300]}")
    rc, head = await run_git(repo, "rev-parse", "HEAD")
    if rc != 0:
        raise CheckpointRollbackError("无法读取 rollback commit")
    return head.strip()


async def rollback_checkpoint(
    session: AsyncSession,
    *,
    tenant_id: str,
    checkpoint_id: str,
    task_id: str,
    source: str,
) -> CheckpointRecord:
    row = await session.scalar(
        select(CheckpointORM).where(
            CheckpointORM.tenant_id == tenant_id,
            CheckpointORM.checkpoint_id == checkpoint_id,
        )
    )
    if row is None:
        raise LookupError(checkpoint_id)
    task = await get_development_task(session, tenant_id, task_id)
    if task is None:
        raise LookupError(task_id)
    if task.status is not DevelopmentTaskStatus.applied:
        raise CheckpointRollbackError("开发任务尚未形成已应用的 Git artifact")
    if row.run_id not in {task.parent_run_id, task.sub_run_id}:
        raise CheckpointRollbackError("开发任务与 checkpoint run 不匹配")

    repo = Path(task.main_workspace)
    allowed = _normalize_git_paths(_record(row).changed_files)
    try:
        await _require_clean_target(repo, task.target_branch)
        if source == "commit":
            rollback_commit = await _rollback_commit(repo, task.applied_commit, allowed)
        elif source == "patch":
            paths = validate_record_paths(
                repo, task.task_id, task.worktree_path, task.patch_path
            )
            rollback_commit = await _rollback_patch(repo, paths.patch, allowed)
        else:
            raise CheckpointRollbackError("rollback source 必须是 commit 或 patch")
    except Exception as exc:
        error = (
            exc
            if isinstance(exc, CheckpointRollbackError)
            else CheckpointRollbackError(str(exc))
        )
        row.status = "rollback_failed"
        row.rollback_source = source
        row.rollback_error = str(error)[:1000]
        await session.flush()
        if error is exc:
            raise
        raise error from exc

    row.status = "rolled_back"
    row.rollback_source = source
    row.rollback_commit = rollback_commit
    row.rollback_error = ""
    await session.flush()
    return _record(row)
