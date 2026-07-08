"""add spine position columns

Revision ID: 20260709_spine_positions
Revises: 20260708_spine
Create Date: 2026-07-09
"""

import sqlalchemy as sa
from alembic import op

revision = "20260709_spine_positions"
down_revision = "20260708_spine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "delivery_initiatives",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "delivery_tasks",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("delivery_tasks", "position")
    op.drop_column("delivery_initiatives", "position")
