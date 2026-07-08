from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
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
