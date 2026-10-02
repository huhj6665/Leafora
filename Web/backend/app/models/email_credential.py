"""邮箱验证凭据模型 (email_credentials).

用于邮箱绑定与密码重置的短数字验证码凭据。

安全设计：
    - ``purpose`` 区分用途（bind_email / password_reset），相互隔离。
    - 验证码不存明文，仅保存 HMAC(服务端密钥) 摘要 ``code_digest``。
    - 具备过期时间 ``expires_at``、一次性消费 ``used_at`` 与失败尝试 ``attempts``。
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BigIntPK, TimestampMixin


class EmailCredentialPurpose(str, enum.Enum):
    """凭据用途，隔离邮箱绑定与密码重置."""

    BIND = "bind_email"
    RESET = "password_reset"


class EmailCredential(TimestampMixin, Base):
    """邮箱验证码凭据表."""

    __tablename__ = "email_credentials"
    __table_args__ = (
        Index("ix_email_credentials_email", "email"),
        Index("ix_email_credentials_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigIntPK, primary_key=True, autoincrement=True, comment="凭据ID"
    )
    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="用途: bind_email / password_reset"
    )
    user_id: Mapped[int] = mapped_column(
        BigIntPK,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="目标用户ID",
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="目标邮箱（规范化小写）"
    )
    # HMAC-SHA256(服务端密钥, purpose:user_id:email:code) 的十六进制摘要
    code_digest: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="验证码摘要（HMAC）"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="过期时间"
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="使用（消费）时间"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="失败尝试次数"
    )
