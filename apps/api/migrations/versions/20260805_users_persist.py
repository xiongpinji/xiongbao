"""user store persistence: users 表补 email + must_change_password 列

UserStore DB 化（lite 内存用户存储不跨实例/重启丢账号的修复）：
- users 表 0001 已建，但缺 email / must_change_password 两列，本迁移补齐；
- 对已被 create_all 兜底建过表的存量库（如开发环境 xagent.db）做列级存在性检查，
  可安全 upgrade；极端情况下 users 表不存在则按新结构整表创建。

Revision ID: 20260805_users_persist
Revises: 20260803_creative
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op

revision = "20260805_users_persist"
down_revision = "20260803_creative"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("user_id", sa.String(64), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("roles", sa.String(256), server_default="member"),
            sa.Column("password_hash", sa.String(256), server_default=""),
            sa.Column("email", sa.String(256), server_default=""),
            sa.Column("must_change_password", sa.Boolean, server_default=sa.false()),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
        )
        op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
        return

    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    if "email" not in existing_cols:
        op.add_column(
            "users", sa.Column("email", sa.String(256), server_default="")
        )
    if "must_change_password" not in existing_cols:
        op.add_column(
            "users",
            sa.Column("must_change_password", sa.Boolean, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in set(inspector.get_table_names()):
        return
    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    if "must_change_password" in existing_cols:
        op.drop_column("users", "must_change_password")
    if "email" in existing_cols:
        op.drop_column("users", "email")
