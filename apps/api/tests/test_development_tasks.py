"""开发任务持久模型与 Git 生命周期测试。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from xagent.domains.development_tasks.models import (
    DevelopmentTaskCreate,
    DevelopmentTaskStatus,
)
from xagent.domains.development_tasks.service import (
    create_development_task,
    get_development_task,
    list_development_tasks,
    update_development_task,
)
from xagent.infra.db import Base


async def test_development_task_persists_and_is_tenant_isolated(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as session:
        created = await create_development_task(
            session,
            DevelopmentTaskCreate(
                task_id="dev-1",
                parent_run_id="parallel-1",
                sub_run_id="parallel-1_sub0",
                tenant_id="tenant-a",
                owner_id="owner-a",
                goal="修改 README",
                main_workspace=str(tmp_path / "repo"),
                base_commit="base123",
                target_branch="main",
                work_branch="agent/dev-1",
                worktree_path=str(tmp_path / "worktrees" / "dev-1"),
                patch_path=str(tmp_path / "patches" / "dev-1.patch"),
            ),
        )
        assert created.status == DevelopmentTaskStatus.running
        await session.commit()

    async with sessions() as session:
        persisted = await get_development_task(session, "tenant-a", "dev-1")
        hidden = await get_development_task(session, "tenant-b", "dev-1")
        tenant_tasks = await list_development_tasks(session, "tenant-a")

        assert persisted is not None
        assert persisted.goal == "修改 README"
        assert hidden is None
        assert [task.task_id for task in tenant_tasks] == ["dev-1"]

        updated = await update_development_task(
            session,
            "tenant-a",
            "dev-1",
            status=DevelopmentTaskStatus.awaiting_review,
            result_commit="result456",
            diff_stat="README.md | 1 +",
            test_summary='{"passed": 1}',
        )
        assert updated is not None
        await session.commit()

    async with sessions() as session:
        persisted = await get_development_task(session, "tenant-a", "dev-1")
        assert persisted is not None
        assert persisted.status == DevelopmentTaskStatus.awaiting_review
        assert persisted.result_commit == "result456"
        assert persisted.test_summary == '{"passed": 1}'

    await engine.dispose()
