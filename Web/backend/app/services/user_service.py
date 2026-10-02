"""用户信息业务服务."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ConflictError, NotFoundError, UnauthorizedError
from app.core.security import hash_password
from app.models.identity import IdentityType, UserIdentity
from app.models.user import User
from app.schemas.user import PROFILE_AVATARS, UpdateUserProfileRequest
from app.services.identity import get_provider
from app.services.sms import get_sms_provider
from app.services.sms_service import send_verification_code
from app.utils.email import mask_email
from app.utils.phone import mask_phone, validate_phone


def _identity_identifier(identity: UserIdentity) -> str:
    """身份标识展示（手机号脱敏）."""
    if identity.identity_type == IdentityType.PHONE.value:
        return mask_phone(identity.identifier)
    return identity.identifier


async def get_profile_data(db: AsyncSession, user: User) -> dict[str, Any]:
    """组装当前用户信息（用户主体 + 登录身份列表）."""
    identities = (
        await db.execute(
            select(UserIdentity).where(UserIdentity.user_id == user.id)
        )
    ).scalars().all()

    phone_identity = next(
        (i for i in identities if i.identity_type == IdentityType.PHONE.value), None
    )

    return {
        "user_id": user.id,
        "nickname": user.nickname,
        "avatar": user.avatar,
        "status": user.status,
        "email": mask_email(user.email) if user.email else None,
        "email_verified": user.email_verified_at is not None,
        "has_phone_password": bool(phone_identity and phone_identity.credential),
        "created_at": user.created_at,
        "identities": [
            {
                "identity_type": i.identity_type,
                "identifier": _identity_identifier(i),
                "created_at": i.created_at,
            }
            for i in identities
        ],
    }


async def update_profile(
    db: AsyncSession, user: User, req: UpdateUserProfileRequest
) -> dict[str, Any]:
    """更新当前用户可编辑的基础资料，不接收身份与状态字段。"""
    fields = req.model_fields_set
    if not fields:
        raise BusinessError("至少提供一个可修改字段")
    if "nickname" in fields:
        user.nickname = req.nickname
    if "avatar" in fields:
        if req.avatar is not None and req.avatar not in PROFILE_AVATARS:
            raise ValueError("头像预设无效")
        user.avatar = req.avatar
    await db.commit()
    await db.refresh(user)
    return await get_profile_data(db, user)


async def get_phone_identity(db: AsyncSession, user_id: int) -> UserIdentity:
    identity = await db.scalar(
        select(UserIdentity).where(
            UserIdentity.user_id == user_id,
            UserIdentity.identity_type == IdentityType.PHONE.value,
        )
    )
    if identity is None:
        raise NotFoundError("当前账号未绑定手机号")
    return identity


async def send_current_phone_password_code(
    db: AsyncSession, user: User, client_ip: str
) -> dict[str, Any]:
    """向当前账号已验证手机号发送密码设置验证码。"""
    identity = await get_phone_identity(db, user.id)
    data = await send_verification_code(identity.identifier, client_ip)
    return {**data, "phone": mask_phone(identity.identifier)}


async def set_current_phone_password(
    db: AsyncSession, user: User, code: str, new_password: str
) -> dict[str, Any]:
    """校验当前账号手机号验证码后设置密码并撤销旧会话。"""
    identity = await get_phone_identity(db, user.id)
    provider = get_sms_provider()
    if not await provider.verify_code(identity.identifier, code):
        raise UnauthorizedError("验证码错误或已过期")
    identity.credential = hash_password(new_password)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    return {"phone": mask_phone(identity.identifier), "password_set": True}


async def send_bind_phone_code(
    db: AsyncSession, user: User, phone: str, client_ip: str
) -> dict[str, Any]:
    """已登录用户绑定手机号前，发送验证码（需 JWT）."""
    return await send_verification_code(phone, client_ip)


async def bind_phone(
    db: AsyncSession, user: User, phone: str, code: str
) -> dict[str, Any]:
    """已登录用户绑定手机号.

    流程：
        1. 手机号格式校验；
        2. 核验验证码；
        3. 检查手机号是否已属于其他 User（属于他人 → 拒绝）；
        4. 绑定到当前 User。
    """
    phone = validate_phone(phone)

    provider = get_sms_provider()
    if not await provider.verify_code(phone, code):
        raise UnauthorizedError("验证码错误或已过期")

    phone_provider = get_provider(IdentityType.PHONE)
    owner = await phone_provider.find_user(db, phone)
    if owner is not None:
        if owner.id == user.id:
            raise ConflictError("该手机号已绑定当前账号")
        raise ConflictError("该手机号已被其他账号绑定")

    await phone_provider.create_identity(db, user, phone)
    await db.commit()

    return {"phone": mask_phone(phone), "bound": True}
