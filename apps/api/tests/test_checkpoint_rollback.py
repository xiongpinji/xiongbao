"""Checkpoint 只通过已验证开发任务 commit/patch 执行 Git 回滚。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from xagent.domains.checkpoints import create_checkpoint, rollback_checkpoint
from xagent.domains.checkpoints.rollback import CheckpointRollbackError
from xagent.domains.development_tasks.git_lifecycle import (
    create_task_worktree,
    development_task_paths,
    finalize_task_worktree,
    inspect_repository,
)
from xagent.domains.development_tasks.models import (
    DevelopmentTaskCreate,
    DevelopmentTaskStatus,
)
from xagent.domains.development_tasks.service import (
    apply_development_task,
    approve_development_task,
    create_development_task,
    update_development_task,
)
from xagent.infra.db import Base


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
async def rollback_store(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rollback.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


async def _prepare_applied_task(maker, repo: Path, task_id: str) -> tuple[str, str]:
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    changed = repo / "result.txt"
    changed.write_text("base\n", encoding="utf-8")
    _git(repo, "add", "result.txt")
    _git(repo, "commit", "-m", "base")
    baseline = await inspect_repository(repo)
    assert baseline is not None
    paths = development_task_paths(repo, task_id)
    branch = f"agent/{task_id}"
    await create_task_worktree(baseline, paths, branch)
    (paths.worktree / "result.txt").write_text("changed\n", encoding="utf-8")
    finalized = await finalize_task_worktree(baseline, paths, task_id)

    async with maker() as session:
        await create_development_task(
            session,
            DevelopmentTaskCreate(
                task_id=task_id,
                parent_run_id="parent-run",
                sub_run_id="checkpoint-run",
                tenant_id="tenant-a",
                owner_id="owner-a",
                goal="change result",
                main_workspace=str(repo),
                base_commit=baseline.commit,
                target_branch=baseline.branch,
                work_branch=branch,
                worktree_path=str(paths.worktree),
                patch_path=str(paths.patch),
                status=DevelopmentTaskStatus.awaiting_review,
            ),
        )
        await update_development_task(
            session,
            "tenant-a",
            task_id,
            result_commit=finalized.result_commit,
            diff_stat=finalized.diff_stat,
        )
        await approve_development_task(
            session, "tenant-a", task_id, reviewer_id="reviewer-a"
        )
        applied = await apply_development_task(
            session, "tenant-a", task_id, actor_id="reviewer-a"
        )
        checkpoint = await create_checkpoint(
            session,
            tenant_id="tenant-a",
            conversation_id="conversation-a",
            run_id="checkpoint-run",
            step=5,
            goal="change result",
            messages=[],
            changed_files=["result.txt"],
            workspace=repo,
        )
        await session.commit()
    return checkpoint.checkpoint_id, applied.applied_commit


@pytest.mark.parametrize("source", ["commit", "patch"])
async def test_rollback_creates_a_new_commit_from_verified_artifact(
    rollback_store, tmp_path, source
) -> None:
    repo = tmp_path / source
    task_id = f"rollback-{source}"
    checkpoint_id, applied_commit = await _prepare_applied_task(
        rollback_store, repo, task_id
    )

    async with rollback_store() as session:
        result = await rollback_checkpoint(
            session,
            tenant_id="tenant-a",
            checkpoint_id=checkpoint_id,
            task_id=task_id,
            source=source,
        )
        await session.commit()

    assert (repo / "result.txt").read_text(encoding="utf-8") == "base\n"
    assert result.status == "rolled_back"
    assert result.rollback_source == source
    assert result.rollback_commit and result.rollback_commit != applied_commit
    assert _git(repo, "status", "--porcelain") == ""


async def test_rollback_rejects_dirty_workspace_without_changing_files(
    rollback_store, tmp_path
) -> None:
    repo = tmp_path / "dirty"
    task_id = "rollback-dirty"
    checkpoint_id, _ = await _prepare_applied_task(rollback_store, repo, task_id)
    (repo / "uncommitted.txt").write_text("keep me\n", encoding="utf-8")

    async with rollback_store() as session:
        with pytest.raises(CheckpointRollbackError, match="未提交改动"):
            await rollback_checkpoint(
                session,
                tenant_id="tenant-a",
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                source="commit",
            )
        await session.commit()

    assert (repo / "uncommitted.txt").read_text(encoding="utf-8") == "keep me\n"
    assert (repo / "result.txt").read_text(encoding="utf-8") == "changed\n"
