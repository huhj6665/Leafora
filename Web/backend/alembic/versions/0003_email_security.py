"""email binding & token version

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22

新增账号安全能力：
    - users 表新增 email / email_verified_at / token_version 字段与 email 唯一约束；
    - 新增 email_credentials 表（邮箱绑定 / 密码重置验证码凭据）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- users 新增邮箱与令牌版本 ----------------
    op.add_column(
        "users",
        sa.Column("email", sa.String(length=255), nullable=True, comment="已验证邮箱（规范化小写）"),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True, comment="邮箱验证完成时间"),
    )
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False, comment="令牌版本"),
    )
    # 同一规范化邮箱只能绑定一个用户（NULL 互不冲突，兼容旧用户未绑定邮箱）
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    # ---------------- email_credentials 邮箱验证凭据表 ----------------
    op.create_table(
        "email_credentials",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="凭据ID"),
        sa.Column("purpose", sa.String(length=32), nullable=False, comment="用途: bind_email / password_reset"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="目标用户ID"),
        sa.Column("email", sa.String(length=255), nullable=False, comment="目标邮箱（规范化小写）"),
        sa.Column("code_digest", sa.String(length=128), nullable=False, comment="验证码摘要（HMAC）"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, comment="过期时间"),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True, comment="使用（消费）时间"),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False, comment="失败尝试次数"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_credentials_email", "email_credentials", ["email"])
    op.create_index("ix_email_credentials_user_id", "email_credentials", ["user_id"])


def downgrade() -> None:
    op.drop_table("email_credentials")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "token_version")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email")
