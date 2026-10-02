"""用户身份模型 (user_identity).

一个 User 可拥有多种登录身份，当前支持 username，
未来扩展 phone / wechat / email。

每种身份以 (identity_type, identifier) 唯一标识。
credential 字段用于保存密码哈希；历史 username 和经短信验证后设置密码的
phone 身份可使用，wechat 等无密码身份保持 NULL。
"""
import enum
from typing import Optional

from sqlalchemy import (
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, BigIntPK, TimestampMixin


class IdentityType(str, enum.Enum):
    """支持的登录身份类型."""

    USERNAME = "username"
    PHONE = "phone"
    WECHAT = "wechat"
    EMAIL = "email"


class UserIdentity(TimestampMixin, Base):
    """用户身份表."""

    __tablename__ = "user_identity"
    __table_args__ = (
        # 同一身份类型下的标识唯一（例如 username 不允许重复）
        UniqueConstraint(
            "identity_type",
            "identifier",
            name="uq_user_identity_type_identifier",
        ),
        Index("ix_user_identity_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigIntPK, primary_key=True, autoincrement=True, comment="身份ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigIntPK,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的用户ID",
    )
    identity_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="身份类型: username/phone/wechat/email"
    )
    identifier: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="身份标识，如用户名/手机号/openid"
    )
    credential: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="凭据，如密码哈希；phone/wechat 为 NULL"
    )

    user = relationship("User", back_populates="identities")
