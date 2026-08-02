"""enterprise persistence: marketplace_entries + tenant_usage + conversations + conversation_messages

工作流 D（持久化改造）：
- marketplace_entries：技能市场条目真实落库（此前纯内存，写操作假成功）。
- tenant_usage：租户用量计数（配额扣减），与 billing_records（账单流水）分离。
- conversations / conversation_messages：ORM 早已存在（infra/models/conversation.py），
  此前仅靠 main.py create_all 兜底，本迁移补齐版本化管理。

所有建表均带 inspector 存在性检查：对已被 create_all 兜底建过表的存量库
（如开发环境 xagent.db）可安全 upgrade，不会重复建表报错。

Revision ID: 20260802_persist
Revises: 20260709_spine_positions
Create Date: 2026-08-02
"""

import sqlalchemy as sa
from alembic import op

revision = "20260802_persist"
down_revision = "20260709_spine_positions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "marketplace_entries" not in existing:
        op.create_table(
            "marketplace_entries",
            sa.Column("entry_id", sa.String(32), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.String(500), server_default=""),
            sa.Column("author", sa.String(64), server_default=""),
            sa.Column("tenant_id", sa.String(64), server_default=""),
            sa.Column("version", sa.String(32), server_default="1.0.0"),
            sa.Column("tags", sa.String(512), server_default=""),
            sa.Column("downloads", sa.Integer, server_default="0"),
            sa.Column("rating", sa.Float, server_default="0"),
            sa.Column("rating_count", sa.Integer, server_default="0"),
            sa.Column("skill_id", sa.String(64), server_default=""),
            sa.Column("published_at", sa.Float, server_default="0"),
            sa.Column("updated_at", sa.Float, server_default="0"),
            sa.Column("status", sa.String(16), server_default="published"),
        )
        op.create_index(
            "ix_marketplace_entries_tenant_id", "marketplace_entries", ["tenant_id"]
        )

    if "tenant_usage" not in existing:
        op.create_table(
            "tenant_usage",
            sa.Column("tenant_id", sa.String(64), primary_key=True),
            sa.Column("agent_runs", sa.Integer, server_default="0"),
            sa.Column("media_generations", sa.Integer, server_default="0"),
            sa.Column("tokens", sa.Integer, server_default="0"),
        )

    if "conversations" not in existing:
        op.create_table(
            "conversations",
            sa.Column("conversation_id", sa.String(64), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("title", sa.String(200), server_default=""),
            sa.Column("message_count", sa.Integer, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("last_active", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])

    if "conversation_messages" not in existing:
        op.create_table(
            "conversation_messages",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("conversation_id", sa.String(64), nullable=False),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("content", sa.Text, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )
        op.create_index(
            "ix_conversation_messages_conversation_id",
            "conversation_messages",
            ["conversation_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for t in (
        "conversation_messages",
        "conversations",
        "tenant_usage",
        "marketplace_entries",
    ):
        if t in existing:
            op.drop_table(t)
