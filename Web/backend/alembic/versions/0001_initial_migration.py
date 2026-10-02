"""initial migration

Revision ID: 0001
Revises:
Create Date: 2026-09-19

创建全部基础表：
    users / user_identity / user_profile / devices / device_binding
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- users 用户主体表 ----------------
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="用户ID"),
        sa.Column("nickname", sa.String(length=64), nullable=False, comment="昵称"),
        sa.Column("avatar", sa.String(length=255), nullable=True, comment="头像URL"),
        sa.Column("status", sa.Integer(), server_default="1", nullable=False, comment="状态"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ---------------- user_identity 用户身份表 ----------------
    op.create_table(
        "user_identity",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="身份ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="关联的用户ID"),
        sa.Column("identity_type", sa.String(length=32), nullable=False, comment="身份类型: username/phone/wechat/email"),
        sa.Column("identifier", sa.String(length=255), nullable=False, comment="身份标识，如用户名/手机号/openid"),
        sa.Column("credential", sa.String(length=255), nullable=True, comment="凭据，如密码哈希；phone/wechat 为 NULL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_type", "identifier", name="uq_user_identity_type_identifier"),
    )
    op.create_index("ix_user_identity_user_id", "user_identity", ["user_id"])

    # ---------------- user_profile 用户资料表 ----------------
    op.create_table(
        "user_profile",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="资料ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="关联的用户ID（一对一）"),
        sa.Column("real_name", sa.String(length=64), nullable=True, comment="真实姓名"),
        sa.Column("phone_display", sa.String(length=32), nullable=True, comment="展示用手机号，不作为登录依据"),
        sa.Column("company", sa.String(length=128), nullable=True, comment="公司"),
        sa.Column("description", sa.Text(), nullable=True, comment="个人简介"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    # ---------------- devices 设备表 ----------------
    op.create_table(
        "devices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="设备主键ID"),
        sa.Column("device_id", sa.String(length=64), nullable=False, comment="设备编号，如 TLD001"),
        sa.Column("device_name", sa.String(length=128), nullable=False, comment="设备名称"),
        sa.Column("device_secret", sa.String(length=255), nullable=False, comment="设备认证密钥"),
        sa.Column("status", sa.Integer(), server_default="1", nullable=False, comment="状态"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
    )

    # ---------------- device_binding 设备绑定表 ----------------
    op.create_table(
        "device_binding",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="绑定ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("device_id", sa.BigInteger(), nullable=False, comment="设备ID（外键 -> devices.id）"),
        sa.Column("bind_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="绑定时间"),
        sa.Column("unbind_time", sa.DateTime(timezone=True), nullable=True, comment="解绑时间"),
        sa.Column("status", sa.Integer(), server_default="1", nullable=False, comment="绑定状态"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_binding_user_id", "device_binding", ["user_id"])
    # 部分唯一索引：同一设备只能存在一条 status=1 的绑定记录
    op.create_index(
        "uq_device_binding_active_device",
        "device_binding",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("status = 1"),
        sqlite_where=sa.text("status = 1"),
    )


def downgrade() -> None:
    op.drop_table("device_binding")
    op.drop_table("devices")
    op.drop_table("user_profile")
    op.drop_table("user_identity")
    op.drop_table("users")
