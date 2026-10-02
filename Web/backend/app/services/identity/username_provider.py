"""账号密码身份提供者."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import hash_password, verify_password
from app.models.identity import IdentityType, UserIdentity
from app.models.user import User
from app.services.identity.base import IdentityProvider


class UsernameIdentityProvider(IdentityProvider):
    """基于用户名 + 密码的身份提供者."""

    identity_type = IdentityType.USERNAME

    async def create_identity(
        self,
        db: AsyncSession,
        user: User,
        identifier: str,
        credential: Optional[str] = None,
    ) -> UserIdentity:
        # 密码必须哈希后存储，禁止明文
        identity = UserIdentity(
            user_id=user.id,
            identity_type=self.identity_type.value,
            identifier=identifier,
            credential=hash_password(credential) if credential else None,
        )
        db.add(identity)
        await db.flush()
        return identity

    async def authenticate(
        self,
        db: AsyncSession,
        identifier: str,
        credential: Optional[str] = None,
    ) -> User:
        # 1. 查询身份记录
        identity = await db.scalar(
            select(UserIdentity).where(
                UserIdentity.identity_type == self.identity_type.value,
                UserIdentity.identifier == identifier,
            )
        )
        # 2. 校验凭据（统一返回“用户名或密码错误”，避免泄露用户是否存在）
        if (
            identity is None
            or identity.credential is None
            or credential is None
            or not verify_password(credential, identity.credential)
        ):
            raise UnauthorizedError("用户名或密码错误")

        # 3. 返回关联用户
        user = await db.get(User, identity.user_id)
        if user is None:
            raise UnauthorizedError("用户名或密码错误")
        return user
