"""add spine tables

Revision ID: 20260708_spine
Revises: 0005
Create Date: 2026-07-08
"""

import sqlalchemy as sa
from alembic import op

revision = "20260708_spine"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_goals",
        sa.Column("goal_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="planning"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("owner_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "goal_id", name="uq_delivery_goals_tenant_goal"),
    )
    op.create_index("ix_delivery_goals_tenant_id", "delivery_goals", ["tenant_id"])

    op.create_table(
        "delivery_initiatives",
        sa.Column("initiative_id", sa.String(length=64), primary_key=True),
        sa.Column("goal_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "goal_id"],
            ["delivery_goals.tenant_id", "delivery_goals.goal_id"],
            name="fk_delivery_initiatives_tenant_goal",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "initiative_id",
            name="uq_delivery_initiatives_tenant_initiative",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "goal_id",
            "initiative_id",
            name="uq_delivery_initiatives_tenant_goal_initiative",
        ),
    )
    op.create_index("ix_delivery_initiatives_goal_id", "delivery_initiatives", ["goal_id"])
    op.create_index("ix_delivery_initiatives_tenant_id", "delivery_initiatives", ["tenant_id"])

    op.create_table(
        "delivery_tasks",
        sa.Column("task_id", sa.String(length=64), primary_key=True),
        sa.Column("initiative_id", sa.String(length=64), nullable=False),
        sa.Column("goal_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("task_kind", sa.String(length=32), nullable=False, server_default="execution"),
        sa.Column("run_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("blocker_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "goal_id"],
            ["delivery_goals.tenant_id", "delivery_goals.goal_id"],
            name="fk_delivery_tasks_tenant_goal",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "goal_id", "initiative_id"],
            [
                "delivery_initiatives.tenant_id",
                "delivery_initiatives.goal_id",
                "delivery_initiatives.initiative_id",
            ],
            name="fk_delivery_tasks_tenant_goal_initiative",
        ),
    )
    op.create_index("ix_delivery_tasks_goal_id", "delivery_tasks", ["goal_id"])
    op.create_index(
        "ix_delivery_tasks_initiative_id",
        "delivery_tasks",
        ["initiative_id"],
    )
    op.create_index("ix_delivery_tasks_tenant_id", "delivery_tasks", ["tenant_id"])

    op.create_table(
        "release_records",
        sa.Column("release_id", sa.String(length=64), primary_key=True),
        sa.Column("goal_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("branch_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("commit_sha", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("pr_number", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="candidate"),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "goal_id"],
            ["delivery_goals.tenant_id", "delivery_goals.goal_id"],
            name="fk_release_records_tenant_goal",
        ),
    )
    op.create_index("ix_release_records_goal_id", "release_records", ["goal_id"])
    op.create_index("ix_release_records_tenant_id", "release_records", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_release_records_tenant_id", table_name="release_records")
    op.drop_index("ix_release_records_goal_id", table_name="release_records")
    op.drop_table("release_records")

    op.drop_index("ix_delivery_tasks_tenant_id", table_name="delivery_tasks")
    op.drop_index("ix_delivery_tasks_initiative_id", table_name="delivery_tasks")
    op.drop_index("ix_delivery_tasks_goal_id", table_name="delivery_tasks")
    op.drop_table("delivery_tasks")

    op.drop_index("ix_delivery_initiatives_tenant_id", table_name="delivery_initiatives")
    op.drop_index("ix_delivery_initiatives_goal_id", table_name="delivery_initiatives")
    op.drop_table("delivery_initiatives")

    op.drop_index("ix_delivery_goals_tenant_id", table_name="delivery_goals")
    op.drop_table("delivery_goals")
