"""durable scheduler jobs and runs

Revision ID: 20260807_durable_scheduler
Revises: 20260807_development_tasks
Create Date: 2026-08-07
"""

import sqlalchemy as sa
from alembic import op

revision = "20260807_durable_scheduler"
down_revision = "20260807_development_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "scheduled_jobs" not in tables:
        op.create_table(
            "scheduled_jobs",
            sa.Column("job_id", sa.String(64), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("owner_id", sa.String(64), nullable=False),
            sa.Column("name", sa.String(256), nullable=False),
            sa.Column("goal", sa.Text(), nullable=False),
            sa.Column("role", sa.String(128), nullable=False, server_default=""),
            sa.Column("cron_expr", sa.String(128), nullable=False, server_default=""),
            sa.Column("interval_seconds", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("retry_backoff_seconds", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("last_run", sa.DateTime(timezone=True)),
            sa.Column("next_run", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        for column in ("tenant_id", "owner_id", "next_run"):
            op.create_index(f"ix_scheduled_jobs_{column}", "scheduled_jobs", [column])
    if "scheduled_job_runs" not in tables:
        op.create_table(
            "scheduled_job_runs",
            sa.Column("run_id", sa.String(64), primary_key=True),
            sa.Column(
                "job_id",
                sa.String(64),
                sa.ForeignKey("scheduled_jobs.job_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("attempt", sa.Integer(), nullable=False),
            sa.Column("claim_token", sa.String(128), nullable=False, server_default=""),
            sa.Column("claimed_at", sa.DateTime(timezone=True)),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.Column("agent_run_id", sa.String(96), nullable=False, server_default=""),
            sa.Column("result", sa.Text(), nullable=False, server_default=""),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("next_retry_at", sa.DateTime(timezone=True)),
            sa.Column(
                "notification_status", sa.String(32), nullable=False, server_default="pending"
            ),
            sa.Column("notification_error", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("job_id", "scheduled_for", "attempt", name="uq_job_run_attempt"),
        )
        for column in (
            "job_id",
            "tenant_id",
            "scheduled_for",
            "status",
            "lease_expires_at",
            "next_retry_at",
        ):
            op.create_index(f"ix_scheduled_job_runs_{column}", "scheduled_job_runs", [column])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "scheduled_job_runs" in tables:
        op.drop_table("scheduled_job_runs")
    if "scheduled_jobs" in tables:
        op.drop_table("scheduled_jobs")
