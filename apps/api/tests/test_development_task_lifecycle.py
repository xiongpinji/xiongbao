"""开发任务 approve/reject/apply Git 状态机测试。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
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
    DevelopmentTaskApplyError,
    DevelopmentTaskTransitionError,
    apply_development_task,
    approve_development_task,
    create_development_task,
    expire_development_task,
    get_development_task,
    reject_development_task,
    update_development_task,
)
from xagent.infra.db import Base


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")


async def _prepare_review_task(
    sessions,
    repo: Path,
    task_id: str,
    *,
    filename: str = "result.txt",
    content: str = "result\n",
) -> None:
    baseline = await inspect_repository(repo)
    assert baseline is not None
    paths = development_task_paths(repo, task_id)
    branch = f"agent/{task_id}"
    await create_task_worktree(baseline, paths, branch)
    (paths.worktree / filename).write_text(content, encoding="utf-8")
    finalized = await finalize_task_worktree(baseline, paths, task_id)
    async with sessions() as session:
        await create_development_task(
            session,
            DevelopmentTaskCreate(
                task_id=task_id,
                parent_run_id="parallel-1",
                sub_run_id=f"parallel-1_{task_id}",
                tenant_id="tenant-a",
                owner_id="owner-a",
                goal=f"task {task_id}",
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
        await session.commit()


@pytest.fixture
async def lifecycle_store(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lifecycle.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield sessions
    finally:
        await engine.dispose()


async def test_approve_does_not_modify_main_and_apply_cherry_picks(
    tmp_path: Path, lifecycle_store
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    await _prepare_review_task(lifecycle_store, repo, "dev-apply")
    base_head = _git(repo, "rev-parse", "HEAD")

    async with lifecycle_store() as session:
        approved = await approve_development_task(
            session, "tenant-a", "dev-apply", reviewer_id="reviewer-a"
        )
        await session.commit()
    assert approved.status == DevelopmentTaskStatus.approved
    assert _git(repo, "rev-parse", "HEAD") == base_head
    assert not (repo / "result.txt").exists()

    async with lifecycle_store() as session:
        applied = await apply_development_task(
            session, "tenant-a", "dev-apply", actor_id="owner-a"
        )
        await session.commit()
    assert applied.status == DevelopmentTaskStatus.applied
    assert applied.applied_commit == _git(repo, "rev-parse", "HEAD")
    assert (repo / "result.txt").read_text(encoding="utf-8") == "result\n"
    assert not Path(applied.worktree_path).exists()
    assert _git(repo, "branch", "--list", applied.work_branch) == ""


async def test_reject_cleans_git_assets_and_blocks_later_approve(
    tmp_path: Path, lifecycle_store
) -> None:
    repo = tmp_path / "repo-reject"
    _init_repo(repo)
    await _prepare_review_task(lifecycle_store, repo, "dev-reject")

    async with lifecycle_store() as session:
        rejected = await reject_development_task(
            session, "tenant-a", "dev-reject", actor_id="owner-a"
        )
        await session.commit()
    assert rejected.status == DevelopmentTaskStatus.rejected
    assert not Path(rejected.worktree_path).exists()
    assert Path(rejected.patch_path).is_file()

    async with lifecycle_store() as session:
        with pytest.raises(DevelopmentTaskTransitionError):
            await approve_development_task(
                session, "tenant-a", "dev-reject", reviewer_id="reviewer-a"
            )


async def test_apply_conflict_aborts_and_preserves_review_assets(
    tmp_path: Path, lifecycle_store
) -> None:
    repo = tmp_path / "repo-conflict"
    _init_repo(repo)
    await _prepare_review_task(
        lifecycle_store,
        repo,
        "dev-conflict",
        filename="README.md",
        content="worktree change\n",
    )
    (repo / "README.md").write_text("main change\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "main change")

    async with lifecycle_store() as session:
        await approve_development_task(
            session, "tenant-a", "dev-conflict", reviewer_id="reviewer-a"
        )
        await session.commit()
    async with lifecycle_store() as session:
        conflicted = await apply_development_task(
            session, "tenant-a", "dev-conflict", actor_id="owner-a"
        )
        await session.commit()

    assert conflicted.status == DevelopmentTaskStatus.conflict
    assert json.loads(conflicted.conflict_files) == ["README.md"]
    assert (repo / "README.md").read_text(encoding="utf-8") == "main change\n"
    assert _git(repo, "status", "--porcelain") == ""
    assert Path(conflicted.worktree_path).exists()
    assert _git(repo, "branch", "--list", conflicted.work_branch)


async def test_expire_cleans_review_assets(tmp_path: Path, lifecycle_store) -> None:
    repo = tmp_path / "repo-expire"
    _init_repo(repo)
    await _prepare_review_task(lifecycle_store, repo, "dev-expire")

    async with lifecycle_store() as session:
        expired = await expire_development_task(session, "tenant-a", "dev-expire")
        await session.commit()

    assert expired.status == DevelopmentTaskStatus.expired
    assert not Path(expired.worktree_path).exists()
    assert Path(expired.patch_path).is_file()


async def test_apply_refuses_dirty_main_workspace(
    tmp_path: Path, lifecycle_store
) -> None:
    repo = tmp_path / "repo-dirty"
    _init_repo(repo)
    await _prepare_review_task(lifecycle_store, repo, "dev-dirty")
    async with lifecycle_store() as session:
        await approve_development_task(
            session, "tenant-a", "dev-dirty", reviewer_id="reviewer-a"
        )
        await session.commit()
    (repo / "dirty.txt").write_text("do not overwrite\n", encoding="utf-8")

    async with lifecycle_store() as session:
        with pytest.raises(DevelopmentTaskApplyError, match="未提交改动"):
            await apply_development_task(
                session, "tenant-a", "dev-dirty", actor_id="owner-a"
            )

    async with lifecycle_store() as session:
        record = await get_development_task(session, "tenant-a", "dev-dirty")
    assert record is not None
    assert record.status == DevelopmentTaskStatus.approved
    assert (repo / "dirty.txt").read_text(encoding="utf-8") == "do not overwrite\n"
