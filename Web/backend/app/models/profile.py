"""用户扩展资料模型 (user_profile).

保存用户的扩展展示信息。
注意：phone_display 仅作为展示用途，不作为登录依据。
"""
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, BigIntPK, TimestampMixin


class UserProfile(TimestampMixin, Base):
    """用户资料表."""

    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(
        BigIntPK, primary_key=True, autoincrement=True, comment="资料ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigIntPK,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="关联的用户ID（一对一）",
    )
    real_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="真实姓名"
    )
    phone_display: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="展示用手机号，不作为登录依据"
    )
    company: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="公司"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="个人简介"
    )

    user = relationship("User", back_populates="profile")
