"""身份提供者抽象接口.

每种登录方式（username / phone / wechat / email）对应一个 IdentityProvider 实现。
业务侧通过 get_provider() 获取提供者，从而与具体登录方式解耦。
"""
from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import IdentityType, UserIdentity
from app.models.user import User


class IdentityProvider(ABC):
    """登录身份提供者基类."""

    #: 该提供者负责的身份类型
    identity_type: IdentityType

    @abstractmethod
    async def create_identity(
        self,
        db: AsyncSession,
        user: User,
        identifier: str,
        credential: Optional[str] = None,
    ) -> UserIdentity:
        """为指定用户创建一条身份记录.

        参数:
            db:         数据库会话
            user:       已创建的 User
            identifier: 身份标识（用户名/手机号/openid/邮箱）
            credential: 凭据（如密码哈希）；无凭据的登录方式传 None
        """
        raise NotImplementedError

    @abstractmethod
    async def authenticate(
        self,
        db: AsyncSession,
        identifier: str,
        credential: Optional[str] = None,
    ) -> User:
        """根据身份标识与凭据认证，成功返回 User，失败抛出 UnauthorizedError."""
        raise NotImplementedError
