from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
from xagent.core.spine.models import GoalStatus, SpinePhase
from xagent.core.spine.service import create_goal, decompose_goal
from xagent.infra.models import DeliveryTaskORM, GoalORM, InitiativeORM, ReleaseRecordORM

EXPECTED_SPINE_TABLES = {
    "delivery_goals",
    "delivery_initiatives",
    "delivery_tasks",
    "release_records",
}


@pytest.fixture
def migrated_spine_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "spine.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    api_dir = Path(__file__).resolve().parent.parent
    env = {**os.environ, "XAGENT_DB__URL": url, "PYTHONPATH": str(api_dir)}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=api_dir,
        env=env,
        check=True,
        capture_output=True,
    )
    return db_file



def _sqlite_engine_with_foreign_keys(db_file: Path) -> sa.Engine:
    engine = sa.create_engine(f"sqlite:///{db_file}")

    @sa.event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine



def _assert_insert_rejected(
    engine: sa.Engine,
    statement: sa.Insert,
    params: dict[str, object],
) -> None:
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(statement, params)
        finally:
            transaction.rollback()



def _orm_unique_signatures(table: sa.Table) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }



def _orm_foreign_key_signatures(
    table: sa.Table,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(element.parent.name for element in constraint.elements),
            constraint.referred_table.name,
            tuple(element.column.name for element in constraint.elements),
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }



def _inspected_unique_signatures(
    inspector: sa.Inspector,
    table_name: str,
) -> set[tuple[str, ...]]:
    return {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    }



def _inspected_foreign_key_signatures(
    inspector: sa.Inspector,
    table_name: str,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }



def test_create_goal_defaults_to_planning_phase() -> None:
    goal = create_goal(
        tenant_id="t-1",
        owner_id="owner-1",
        title="Build auto-delivery spine",
        description="Phase 1 self-hosted delivery loop",
    )
    assert goal.phase is SpinePhase.planning
    assert goal.status is GoalStatus.pending
    assert goal.title == "Build auto-delivery spine"



def test_decompose_goal_creates_initiatives_and_ready_tasks() -> None:
    goal = create_goal(
        tenant_id="t-1",
        owner_id="owner-1",
        title="Build auto-delivery spine",
        description="Phase 1 self-hosted delivery loop",
    )
    initiatives, tasks = decompose_goal(goal)
    assert [item.title for item in initiatives] == [
        "Goal / Taskboard / Session Core",
        "Execution Environment Orchestrator",
        "PR / Review / Release Packaging Core",
        "Deploy / Verify / Recover Core",
        "Control / Policy / Safety Core",
        "Evidence / Archive / Continuous Learning Core",
    ]
    assert all(task.status == "ready" for task in tasks)



def test_spine_package_exports_core_symbols() -> None:
    import xagent.core.spine as spine

    assert spine.SpinePhase is SpinePhase
    assert spine.GoalStatus is GoalStatus
    assert spine.Goal.__name__ == "Goal"
    assert spine.Initiative.__name__ == "Initiative"
    assert spine.DeliveryTask.__name__ == "DeliveryTask"
    assert spine.INITIATIVE_BLUEPRINTS[0] == "Goal / Taskboard / Session Core"
    assert spine.create_goal is create_goal
    assert spine.decompose_goal is decompose_goal



def test_spine_models_exported_from_package() -> None:
    assert GoalORM.__tablename__ == "delivery_goals"
    assert InitiativeORM.__tablename__ == "delivery_initiatives"
    assert DeliveryTaskORM.__tablename__ == "delivery_tasks"
    assert ReleaseRecordORM.__tablename__ == "release_records"



def test_spine_orm_metadata_declares_composite_integrity_constraints() -> None:
    assert ("tenant_id", "goal_id") in _orm_unique_signatures(GoalORM.__table__)

    initiative_uniques = _orm_unique_signatures(InitiativeORM.__table__)
    assert ("tenant_id", "initiative_id") in initiative_uniques
    assert ("tenant_id", "goal_id", "initiative_id") in initiative_uniques
    assert (
        ("tenant_id", "goal_id"),
        "delivery_goals",
        ("tenant_id", "goal_id"),
    ) in _orm_foreign_key_signatures(InitiativeORM.__table__)

    task_foreign_keys = _orm_foreign_key_signatures(DeliveryTaskORM.__table__)
    assert (
        ("tenant_id", "goal_id"),
        "delivery_goals",
        ("tenant_id", "goal_id"),
    ) in task_foreign_keys
    assert (
        ("tenant_id", "goal_id", "initiative_id"),
        "delivery_initiatives",
        ("tenant_id", "goal_id", "initiative_id"),
    ) in task_foreign_keys

    assert (
        ("tenant_id", "goal_id"),
        "delivery_goals",
        ("tenant_id", "goal_id"),
    ) in _orm_foreign_key_signatures(ReleaseRecordORM.__table__)



def test_spine_migration_head_creates_tables_and_composite_constraints(
    migrated_spine_db: Path,
) -> None:
    engine = sa.create_engine(f"sqlite:///{migrated_spine_db}")
    try:
        inspector = sa.inspect(engine)
        assert EXPECTED_SPINE_TABLES.issubset(set(inspector.get_table_names()))

        assert ("tenant_id", "goal_id") in _inspected_unique_signatures(
            inspector, "delivery_goals"
        )

        initiative_uniques = _inspected_unique_signatures(
            inspector, "delivery_initiatives"
        )
        assert ("tenant_id", "initiative_id") in initiative_uniques
        assert ("tenant_id", "goal_id", "initiative_id") in initiative_uniques
        assert (
            ("tenant_id", "goal_id"),
            "delivery_goals",
            ("tenant_id", "goal_id"),
        ) in _inspected_foreign_key_signatures(inspector, "delivery_initiatives")

        task_foreign_keys = _inspected_foreign_key_signatures(
            inspector, "delivery_tasks"
        )
        assert (
            ("tenant_id", "goal_id"),
            "delivery_goals",
            ("tenant_id", "goal_id"),
        ) in task_foreign_keys
        assert (
            ("tenant_id", "goal_id", "initiative_id"),
            "delivery_initiatives",
            ("tenant_id", "goal_id", "initiative_id"),
        ) in task_foreign_keys

        assert (
            ("tenant_id", "goal_id"),
            "delivery_goals",
            ("tenant_id", "goal_id"),
        ) in _inspected_foreign_key_signatures(inspector, "release_records")
    finally:
        engine.dispose()



def test_spine_database_constraints_reject_bad_hierarchy_data(
    migrated_spine_db: Path,
) -> None:
    engine = _sqlite_engine_with_foreign_keys(migrated_spine_db)
    metadata = sa.MetaData()
    now = datetime.now(UTC)

    try:
        goals = sa.Table("delivery_goals", metadata, autoload_with=engine)
        initiatives = sa.Table("delivery_initiatives", metadata, autoload_with=engine)
        tasks = sa.Table("delivery_tasks", metadata, autoload_with=engine)

        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

        with engine.begin() as conn:
            conn.execute(
                goals.insert(),
                [
                    {
                        "goal_id": "goal-1",
                        "tenant_id": "tenant-1",
                        "title": "Goal 1",
                        "description": "",
                        "phase": "planning",
                        "status": "pending",
                        "owner_id": "owner-1",
                        "metadata_json": "{}",
                        "created_at": now,
                        "updated_at": now,
                    },
                    {
                        "goal_id": "goal-2",
                        "tenant_id": "tenant-1",
                        "title": "Goal 2",
                        "description": "",
                        "phase": "planning",
                        "status": "pending",
                        "owner_id": "owner-1",
                        "metadata_json": "{}",
                        "created_at": now,
                        "updated_at": now,
                    },
                ],
            )
            conn.execute(
                initiatives.insert(),
                {
                    "initiative_id": "initiative-1",
                    "goal_id": "goal-1",
                    "tenant_id": "tenant-1",
                    "title": "Initiative 1",
                    "status": "pending",
                    "priority": "medium",
                    "created_at": now,
                    "updated_at": now,
                },
            )

        _assert_insert_rejected(
            engine,
            initiatives.insert(),
            {
                "initiative_id": "initiative-1",
                "goal_id": "goal-2",
                "tenant_id": "tenant-1",
                "title": "Duplicate initiative id within tenant",
                "status": "pending",
                "priority": "medium",
                "created_at": now,
                "updated_at": now,
            },
        )
        _assert_insert_rejected(
            engine,
            initiatives.insert(),
            {
                "initiative_id": "initiative-cross-tenant",
                "goal_id": "goal-1",
                "tenant_id": "tenant-2",
                "title": "Mismatched tenant",
                "status": "pending",
                "priority": "medium",
                "created_at": now,
                "updated_at": now,
            },
        )
        _assert_insert_rejected(
            engine,
            tasks.insert(),
            {
                "task_id": "task-cross-goal",
                "initiative_id": "initiative-1",
                "goal_id": "goal-2",
                "tenant_id": "tenant-1",
                "title": "Invalid task linkage",
                "detail": "",
                "status": "ready",
                "task_kind": "execution",
                "run_id": "run-1",
                "blocker_reason": "",
                "created_at": now,
                "updated_at": now,
            },
        )
    finally:
        engine.dispose()
