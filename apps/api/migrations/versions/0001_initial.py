"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-21
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("roles", sa.String(256), server_default="member"),
        sa.Column("password_hash", sa.String(256), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    op.create_table(
        "subscriptions",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("plan", sa.String(32), server_default="free"),
        sa.Column("period_start", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "billing_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), server_default=""),
        sa.Column("action", sa.String(64), server_default=""),
        sa.Column("cost", sa.Float, server_default="0"),
        sa.Column("tokens", sa.Integer, server_default="0"),
        sa.Column("ts", sa.DateTime(timezone=True)),
        sa.Column("detail", sa.String(1024), server_default=""),
    )
    op.create_index("ix_billing_records_tenant_id", "billing_records", ["tenant_id"])

    op.create_table(
        "audit_events",
        sa.Column("seq", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True)),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), server_default=""),
        sa.Column("action", sa.String(64), server_default=""),
        sa.Column("resource", sa.String(64), server_default=""),
        sa.Column("detail", sa.Text, server_default=""),
        sa.Column("prev_hash", sa.String(64), server_default="0" * 64),
        sa.Column("hash", sa.String(64), server_default=""),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])

    op.create_table(
        "workflow_runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("spec_name", sa.String(128), server_default=""),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("view", sa.Text, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflow_runs_tenant_id", "workflow_runs", ["tenant_id"])

    op.create_table(
        "memory_meta",
        sa.Column("record_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("text_preview", sa.String(512), server_default=""),
        sa.Column("source", sa.String(64), server_default="manual"),
        sa.Column("tags", sa.String(256), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_memory_meta_tenant_id", "memory_meta", ["tenant_id"])


def downgrade() -> None:
    for t in ("memory_meta", "workflow_runs", "audit_events", "billing_records",
              "subscriptions", "users", "tenants"):
        op.drop_table(t)
