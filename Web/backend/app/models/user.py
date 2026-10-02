"""用户主体模型 (users).

设计原则（用户主体与身份认证分离）：
    User 仅表示一个真实用户，保存核心信息，不保存任何登录凭据
    （用户名、密码、手机号、微信 openid、邮箱等）。
    所有登录方式统一通过 UserIdentity 关联到同一个 User。
"""
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, BigIntPK, TimestampMixin

if TYPE_CHECKING:
    from app.models.identity import UserIdentity
    from app.models.profile import UserProfile


class User(TimestampMixin, Base):
    """用户主体表."""

    __tablename__ = "users"
    __table_args__ = (
        # 同一规范化邮箱只能绑定一个用户（NULL 互不冲突，兼容未绑定邮箱的旧用户）
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[int] = mapped_column(
        BigIntPK, primary_key=True, autoincrement=True, comment="用户ID"
    )
    nickname: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="昵称"
    )
    avatar: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="头像URL"
    )
    # 状态：1-正常，0-禁用
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", comment="状态"
    )

    # 邮箱仅作为账号恢复凭据（绑定并通过验证后写入），不作为登录方式。
    # 统一以规范化（小写）形式存储；唯一约束保证同一邮箱只能绑定一个用户。
    email: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="已验证邮箱（规范化小写）"
    )
    email_verified_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="邮箱验证完成时间"
    )

    # 令牌版本：密码重置后自增，使此前签发的 JWT 全部失效（会话撤销）。
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="令牌版本"
    )

    # 一个用户可拥有多种登录身份（username / phone / wechat / email）
    identities: Mapped[List["UserIdentity"]] = relationship(
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # 一个用户对应一条扩展资料
    profile: Mapped[Optional["UserProfile"]] = relationship(
        back_populates="user",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )
