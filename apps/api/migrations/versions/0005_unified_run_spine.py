"""unified run spine

Revision ID: 0005
Revises: 0001
Create Date: 2026-06-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_tasks",
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("kind", sa.String(64), nullable=False, server_default="agent.run"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("backend", sa.String(32), nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("intent_type", sa.String(32), nullable=False, server_default="general"),
        sa.Column("route_source", sa.String(32), nullable=False, server_default="fallback"),
        sa.Column("input_payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result_payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.String(1024), nullable=False, server_default=""),
        sa.Column("validation_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("delivery_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("lineage_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("preview_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_tasks_run_id", "agent_tasks", ["run_id"])
    op.create_index("ix_agent_tasks_tenant_id", "agent_tasks", ["tenant_id"])

    op.create_table(
        "artifacts",
        sa.Column("artifact_id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False, server_default=""),
        sa.Column("name", sa.String(256), nullable=False, server_default=""),
        sa.Column("uri", sa.String(1024), nullable=False, server_default=""),
        sa.Column("content_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(128), nullable=False, server_default=""),
        sa.Column("validation_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("delivery_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("lineage_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("preview_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("ix_artifacts_task_id", "artifacts", ["task_id"])
    op.create_index("ix_artifacts_tenant_id", "artifacts", ["tenant_id"])

    op.create_table(
        "evidence_records",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("evidence_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("artifact_id", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False, server_default=""),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "evidence_id", name="pk_evidence_records"),
    )
    op.create_index("ix_evidence_records_run_id", "evidence_records", ["run_id"])
    op.create_index("ix_evidence_records_task_id", "evidence_records", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_records_task_id", table_name="evidence_records")
    op.drop_index("ix_evidence_records_run_id", table_name="evidence_records")
    op.drop_table("evidence_records")

    op.drop_index("ix_artifacts_tenant_id", table_name="artifacts")
    op.drop_index("ix_artifacts_task_id", table_name="artifacts")
    op.drop_index("ix_artifacts_run_id", table_name="artifacts")
    op.drop_table("artifacts")

    op.drop_index("ix_agent_tasks_tenant_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_run_id", table_name="agent_tasks")
    op.drop_table("agent_tasks")
