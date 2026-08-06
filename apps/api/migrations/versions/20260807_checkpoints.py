"""数据库 checkpoint 与恢复/回滚状态

Revision ID: 20260807_checkpoints
Revises: 20260807_skill_packages
Create Date: 2026-08-07
"""

import sqlalchemy as sa
from alembic import op

revision = "20260807_checkpoints"
down_revision = "20260807_skill_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "checkpoints" in tables:
        return
    op.create_table(
        "checkpoints",
        sa.Column("checkpoint_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("parent_checkpoint_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False, server_default=""),
        sa.Column("messages_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("changed_files_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("resumed_run_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("rollback_source", sa.String(32), nullable=False, server_default=""),
        sa.Column("rollback_commit", sa.String(128), nullable=False, server_default=""),
        sa.Column("rollback_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        "tenant_id",
        "conversation_id",
        "run_id",
        "parent_checkpoint_id",
        "status",
    ):
        op.create_index(f"ix_checkpoints_{column}", "checkpoints", [column])


def downgrade() -> None:
    op.drop_table("checkpoints")
