"""creative studio persistence

creative_drafts + creative_productions + creative_canvases + creative_media_tasks

短剧工厂持久化落库（Phase 5）：
- creative_drafts：一句话→工作流草稿（此前进程内 dict，重启即丢）。
- creative_productions：短剧成片产物（同上）。
- creative_canvases：生产画布节点链（此前仅 JSON 文件快照）。
- creative_media_tasks：媒体任务 → 租户映射（按租户拉取媒体任务状态用）。

所有建表均带 inspector 存在性检查：对已被 ORM create_all / 惰性建表兜底
建过表的存量库可安全 upgrade，不会重复建表报错。

Revision ID: 20260803_creative
Revises: 20260802_persist
Create Date: 2026-08-03
"""

import sqlalchemy as sa
from alembic import op

revision = "20260803_creative"
down_revision = "20260802_persist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "creative_drafts" not in existing:
        op.create_table(
            "creative_drafts",
            sa.Column("draft_id", sa.String(64), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("owner", sa.String(64), server_default="", nullable=False),
            sa.Column("status", sa.String(32), server_default="pending_review", nullable=False),
            sa.Column("doc", sa.Text, server_default="{}", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_creative_drafts_tenant_id", "creative_drafts", ["tenant_id"])

    if "creative_productions" not in existing:
        op.create_table(
            "creative_productions",
            sa.Column("storyboard_id", sa.String(64), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("owner", sa.String(64), server_default="", nullable=False),
            sa.Column("status", sa.String(32), server_default="pending", nullable=False),
            sa.Column("doc", sa.Text, server_default="{}", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_creative_productions_tenant_id", "creative_productions", ["tenant_id"]
        )

    if "creative_canvases" not in existing:
        op.create_table(
            "creative_canvases",
            sa.Column("canvas_id", sa.String(64), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("doc", sa.Text, server_default="{}", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_creative_canvases_tenant_id", "creative_canvases", ["tenant_id"])

    if "creative_media_tasks" not in existing:
        op.create_table(
            "creative_media_tasks",
            sa.Column("task_id", sa.String(64), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_creative_media_tasks_tenant_id", "creative_media_tasks", ["tenant_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table in (
        "creative_media_tasks",
        "creative_canvases",
        "creative_productions",
        "creative_drafts",
    ):
        if table in existing:
            op.drop_table(table)
