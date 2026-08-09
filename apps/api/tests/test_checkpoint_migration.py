"""checkpoint scope unique migration guards dirty data before constraining."""

from __future__ import annotations

import importlib

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

_MIGRATION = importlib.import_module(
    "migrations.versions.20260809_checkpoint_scope_unique"
)


def _create_checkpoint_table(connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "checkpoints",
        metadata,
        sa.Column("checkpoint_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("parent_checkpoint_id", sa.String(64), nullable=False, default=""),
        sa.Column("step", sa.Integer(), nullable=False, default=0),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False, default=""),
        sa.Column("messages_json", sa.Text(), nullable=False, default="[]"),
        sa.Column("changed_files_json", sa.Text(), nullable=False, default="[]"),
        sa.Column("resumed_run_id", sa.String(96), nullable=False, default=""),
        sa.Column("rollback_source", sa.String(32), nullable=False, default=""),
        sa.Column("rollback_commit", sa.String(128), nullable=False, default=""),
        sa.Column("rollback_error", sa.Text(), nullable=False, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(connection)


def _install_op(monkeypatch: pytest.MonkeyPatch, connection) -> None:
    context = MigrationContext.configure(connection)
    monkeypatch.setattr(_MIGRATION, "op", Operations(context))


def _insert_checkpoint(connection, checkpoint_id: str, *, content: str = "payload") -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO checkpoints (
                checkpoint_id, tenant_id, conversation_id, run_id, step, status,
                goal, messages_json, changed_files_json, created_at, updated_at,
                parent_checkpoint_id, resumed_run_id, rollback_source,
                rollback_commit, rollback_error
            )
            VALUES (
                :checkpoint_id, 'tenant-a', 'conversation-a', 'run-a', 5,
                'available', '', :messages_json, '[]', CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP, '', '', '', '', ''
            )
            """
        ),
        {"checkpoint_id": checkpoint_id, "messages_json": f'[{{"content":"{content}"}}]'},
    )


def _unique_indexes(connection) -> list[dict]:
    return [
        index
        for index in sa.inspect(connection).get_indexes("checkpoints")
        if index.get("unique")
    ]


def test_checkpoint_scope_unique_migration_blocks_duplicates_without_schema_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _create_checkpoint_table(connection)
        _install_op(monkeypatch, connection)
        _insert_checkpoint(connection, "checkpoint-a", content="first")
        _insert_checkpoint(connection, "checkpoint-b", content="second")

        with pytest.raises(RuntimeError, match=r"checkpoint_scope_duplicates: groups=1"):
            _MIGRATION.upgrade()

        assert _unique_indexes(connection) == []
        rows = connection.execute(sa.text("SELECT COUNT(*) FROM checkpoints")).scalar()
        assert rows == 2


def test_checkpoint_scope_unique_migration_upgrade_and_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _MIGRATION.down_revision == "20260807_checkpoints"
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _create_checkpoint_table(connection)
        _install_op(monkeypatch, connection)
        _insert_checkpoint(connection, "checkpoint-a")

        _MIGRATION.upgrade()

        indexes = _unique_indexes(connection)
        assert [index["name"] for index in indexes] == ["uq_checkpoints_scope"]
        with pytest.raises(IntegrityError):
            _insert_checkpoint(connection, "checkpoint-b")

        _MIGRATION.downgrade()

        assert _unique_indexes(connection) == []
        _insert_checkpoint(connection, "checkpoint-b")
        rows = connection.execute(sa.text("SELECT COUNT(*) FROM checkpoints")).scalar()
        assert rows == 2
