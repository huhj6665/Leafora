"""手机号身份提供者.

手机号身份的认证通过阿里云短信验证码完成（见 auth_service），
因此本类不实现基于凭据的 ``authenticate``，仅负责：
    - 创建 phone 身份（credential 为 NULL）
    - 按手机号查找已绑定用户
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import IdentityType, UserIdentity
from app.models.user import User
from app.services.identity.base import IdentityProvider


class PhoneIdentityProvider(IdentityProvider):
    """基于手机号的身份提供者."""

    identity_type = IdentityType.PHONE

    async def create_identity(
        self,
        db: AsyncSession,
        user: User,
        identifier: str,
        credential: Optional[str] = None,
    ) -> UserIdentity:
        """为指定用户创建手机号身份（credential 恒为 NULL）."""
        identity = UserIdentity(
            user_id=user.id,
            identity_type=self.identity_type.value,
            identifier=identifier,
            credential=None,
        )
        db.add(identity)
        await db.flush()
        return identity

    async def find_user(self, db: AsyncSession, phone: str) -> Optional[User]:
        """根据手机号查找已绑定用户，不存在返回 None."""
        identity = await db.scalar(
            select(UserIdentity).where(
                UserIdentity.identity_type == self.identity_type.value,
                UserIdentity.identifier == phone,
            )
        )
        if identity is None:
            return None
        return await db.get(User, identity.user_id)

    async def authenticate(
        self,
        db: AsyncSession,
        identifier: str,
        credential: Optional[str] = None,
    ) -> User:
        """手机号认证不基于本地凭据，此方法不适用."""
        raise NotImplementedError("手机号身份通过短信验证码认证，请使用 auth_service.login_by_phone")
