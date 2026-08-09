"""checkpoint scope uniqueness

Revision ID: 20260809_checkpoint_scope_unique
Revises: 20260807_checkpoints
Create Date: 2026-08-09
"""

import sqlalchemy as sa
from alembic import op

revision = "20260809_checkpoint_scope_unique"
down_revision = "20260807_checkpoints"
branch_labels = None
depends_on = None

_SCOPE_NAME = "uq_checkpoints_scope"
_SCOPE_COLUMNS = ["tenant_id", "conversation_id", "run_id", "step"]


def _duplicate_group_count(bind) -> int:
    result = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM (
                SELECT 1
                FROM checkpoints
                GROUP BY tenant_id, conversation_id, run_id, step
                HAVING COUNT(*) > 1
            ) duplicate_scopes
            """
        )
    )
    return int(result.scalar() or 0)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "checkpoints" not in tables:
        return
    duplicate_groups = _duplicate_group_count(bind)
    if duplicate_groups:
        raise RuntimeError(
            f"checkpoint_scope_duplicates: groups={duplicate_groups}"
        )
    if bind.dialect.name == "sqlite":
        op.create_index(_SCOPE_NAME, "checkpoints", _SCOPE_COLUMNS, unique=True)
    else:
        op.create_unique_constraint(_SCOPE_NAME, "checkpoints", _SCOPE_COLUMNS)


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "checkpoints" not in tables:
        return
    if bind.dialect.name == "sqlite":
        op.drop_index(_SCOPE_NAME, table_name="checkpoints")
    else:
        op.drop_constraint(_SCOPE_NAME, "checkpoints", type_="unique")
