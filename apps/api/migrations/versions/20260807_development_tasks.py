"""development task review lifecycle

Revision ID: 20260807_development_tasks
Revises: 20260805_users_persist
Create Date: 2026-08-07
"""

import sqlalchemy as sa
from alembic import op

revision = "20260807_development_tasks"
down_revision = "20260805_users_persist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "development_tasks" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "development_tasks",
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("parent_run_id", sa.String(64), nullable=False),
        sa.Column("sub_run_id", sa.String(96), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("main_workspace", sa.String(1024), nullable=False, server_default=""),
        sa.Column("base_commit", sa.String(128), nullable=False, server_default=""),
        sa.Column("target_branch", sa.String(256), nullable=False, server_default=""),
        sa.Column("work_branch", sa.String(256), nullable=False, server_default=""),
        sa.Column("worktree_path", sa.String(1024), nullable=False, server_default=""),
        sa.Column("result_commit", sa.String(128), nullable=False, server_default=""),
        sa.Column("applied_commit", sa.String(128), nullable=False, server_default=""),
        sa.Column("diff_stat", sa.Text(), nullable=False, server_default=""),
        sa.Column("patch_path", sa.String(1024), nullable=False, server_default=""),
        sa.Column("test_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("conflict_files", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("reviewed_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("parent_run_id", "sub_run_id", "tenant_id", "owner_id", "status"):
        op.create_index(f"ix_development_tasks_{column}", "development_tasks", [column])


def downgrade() -> None:
    bind = op.get_bind()
    if "development_tasks" not in set(sa.inspect(bind).get_table_names()):
        return
    op.drop_table("development_tasks")
