"""开发任务受控 Git worktree 生命周期。"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class RepositoryBaseline:
    root: Path
    commit: str
    branch: str


@dataclass(frozen=True)
class DevelopmentTaskPaths:
    worktree_root: Path
    worktree: Path
    patch_root: Path
    patch: Path


@dataclass(frozen=True)
class WorktreeResult:
    result_commit: str
    diff_stat: str
    patch_text: str


@dataclass(frozen=True)
class ApplyResult:
    applied_commit: str = ""
    conflict_files: tuple[str, ...] = ()
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return bool(self.applied_commit)


async def run_git(cwd: Path, *args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await proc.communicate()
    return proc.returncode or 0, output.decode("utf-8", errors="replace")


async def inspect_repository(workspace: Path) -> RepositoryBaseline | None:
    rc, root_text = await run_git(workspace, "rev-parse", "--show-toplevel")
    if rc != 0:
        return None
    root = await asyncio.to_thread(Path(root_text.strip()).resolve)
    rc, commit = await run_git(root, "rev-parse", "HEAD")
    if rc != 0:
        return None
    rc, branch = await run_git(root, "branch", "--show-current")
    if rc != 0:
        return None
    return RepositoryBaseline(root=root, commit=commit.strip(), branch=branch.strip() or "HEAD")


def development_task_paths(repo_root: Path, task_id: str) -> DevelopmentTaskPaths:
    if _SAFE_TASK_ID.fullmatch(task_id) is None:
        raise ValueError("开发任务 ID 含不安全字符")
    resolved_repo = repo_root.resolve()
    worktree_root = (resolved_repo.parent / ".xagent-worktrees").resolve()
    patch_root = (resolved_repo.parent / ".xagent-development-tasks").resolve()
    worktree = (worktree_root / task_id).resolve()
    patch = (patch_root / f"{task_id}.patch").resolve()
    if not worktree.is_relative_to(worktree_root):
        raise ValueError("worktree 路径逃逸受控根")
    if not patch.is_relative_to(patch_root):
        raise ValueError("patch 路径逃逸受控根")
    return DevelopmentTaskPaths(
        worktree_root=worktree_root,
        worktree=worktree,
        patch_root=patch_root,
        patch=patch,
    )


async def create_task_worktree(
    baseline: RepositoryBaseline,
    paths: DevelopmentTaskPaths,
    branch: str,
) -> None:
    await asyncio.to_thread(paths.worktree_root.mkdir, parents=True, exist_ok=True)
    rc, output = await run_git(
        baseline.root,
        "worktree",
        "add",
        "-b",
        branch,
        str(paths.worktree),
        baseline.commit,
    )
    if rc != 0:
        raise RuntimeError(f"git worktree add 失败: {output.strip()[:300]}")


async def finalize_task_worktree(
    baseline: RepositoryBaseline,
    paths: DevelopmentTaskPaths,
    task_id: str,
) -> WorktreeResult:
    rc, output = await run_git(paths.worktree, "add", "-A")
    if rc != 0:
        raise RuntimeError(f"git add 失败: {output.strip()[:300]}")
    rc, output = await run_git(
        paths.worktree,
        "-c",
        "user.name=X-Agent",
        "-c",
        "user.email=xagent@local",
        "commit",
        "--no-gpg-sign",
        "--allow-empty",
        "-m",
        f"xagent: development task {task_id}",
    )
    if rc != 0:
        raise RuntimeError(f"git commit 失败: {output.strip()[:300]}")
    rc, result_commit = await run_git(paths.worktree, "rev-parse", "HEAD")
    if rc != 0:
        raise RuntimeError(f"读取结果 commit 失败: {result_commit.strip()[:300]}")
    result_commit = result_commit.strip()
    rc, diff_stat = await run_git(
        paths.worktree, "diff", "--stat", baseline.commit, result_commit
    )
    if rc != 0:
        raise RuntimeError(f"读取 diff stat 失败: {diff_stat.strip()[:300]}")
    rc, patch_text = await run_git(
        paths.worktree, "diff", "--binary", baseline.commit, result_commit
    )
    if rc != 0:
        raise RuntimeError(f"生成 patch 失败: {patch_text.strip()[:300]}")
    await asyncio.to_thread(paths.patch_root.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(paths.patch.write_text, patch_text, encoding="utf-8")
    return WorktreeResult(
        result_commit=result_commit,
        diff_stat=diff_stat.strip(),
        patch_text=patch_text,
    )


async def cleanup_task_worktree(
    repo_root: Path,
    paths: DevelopmentTaskPaths,
    branch: str,
    *,
    strict: bool = True,
) -> None:
    rc, output = await run_git(
        repo_root, "worktree", "remove", "--force", str(paths.worktree)
    )
    if rc != 0 and await asyncio.to_thread(paths.worktree.exists) and strict:
        raise RuntimeError(f"清理 worktree 失败: {output.strip()[:300]}")
    await run_git(repo_root, "worktree", "prune")
    rc, output = await run_git(repo_root, "branch", "-D", branch)
    if rc != 0 and strict:
        _, existing = await run_git(repo_root, "branch", "--list", branch)
        if existing.strip():
            raise RuntimeError(f"清理临时分支失败: {output.strip()[:300]}")


def validate_record_paths(
    repo_root: Path,
    task_id: str,
    worktree_path: str,
    patch_path: str,
) -> DevelopmentTaskPaths:
    expected = development_task_paths(repo_root, task_id)
    if Path(worktree_path).resolve() != expected.worktree:
        raise ValueError("持久记录 worktree 路径不在受控位置")
    if Path(patch_path).resolve() != expected.patch:
        raise ValueError("持久记录 patch 路径不在受控位置")
    return expected


async def apply_result_commit(
    repo_root: Path,
    target_branch: str,
    result_commit: str,
) -> ApplyResult:
    rc, branch = await run_git(repo_root, "branch", "--show-current")
    if rc != 0 or branch.strip() != target_branch:
        raise RuntimeError(
            f"主工作区分支不匹配: current={branch.strip() or 'HEAD'}, target={target_branch}"
        )
    rc, status = await run_git(repo_root, "status", "--porcelain")
    if rc != 0:
        raise RuntimeError(f"读取主工作区状态失败: {status.strip()[:300]}")
    if status.strip():
        raise RuntimeError("主工作区存在未提交改动，拒绝 apply")

    rc, output = await run_git(repo_root, "cherry-pick", result_commit)
    if rc != 0:
        _, conflicts = await run_git(
            repo_root, "diff", "--name-only", "--diff-filter=U"
        )
        await run_git(repo_root, "cherry-pick", "--abort")
        return ApplyResult(
            conflict_files=tuple(
                line.strip() for line in conflicts.splitlines() if line.strip()
            ),
            error=output.strip()[:1000],
        )
    rc, applied_commit = await run_git(repo_root, "rev-parse", "HEAD")
    if rc != 0:
        raise RuntimeError(f"读取 applied commit 失败: {applied_commit.strip()[:300]}")
    return ApplyResult(applied_commit=applied_commit.strip())
