"""完整 Skill Package 持久记录

Revision ID: 20260807_skill_packages
Revises: 20260807_durable_scheduler
Create Date: 2026-08-07
"""

import sqlalchemy as sa
from alembic import op

revision = "20260807_skill_packages"
down_revision = "20260807_durable_scheduler"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "skill_packages" in tables:
        return
    op.create_table(
        "skill_packages",
        sa.Column("package_id", sa.String(64), primary_key=True),
        sa.Column("skill_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("version", sa.String(64), nullable=False, server_default="1"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("frontmatter_json", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("source", sa.String(512), nullable=False, server_default=""),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_size", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "content_hash", name="uq_skill_package_tenant_hash"
        ),
    )
    for column in ("skill_id", "tenant_id", "owner_id"):
        op.create_index(f"ix_skill_packages_{column}", "skill_packages", [column])


def downgrade() -> None:
    op.drop_table("skill_packages")

