"""认证业务服务：注册、登录（账号/手机号）与验证码发送.

业务逻辑与 HTTP 层解耦，便于复用与测试。
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessError,
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
)
from app.models.identity import IdentityType, UserIdentity
from app.models.user import User
from app.services.identity import get_provider
from app.services.jwt_service import create_access_token
from app.services.sms import get_sms_provider
from app.services.sms_service import send_verification_code
from app.core.security import hash_password, verify_password
from app.utils.phone import mask_phone, validate_phone


async def register(db: AsyncSession, username: str, password: str) -> User:
    """注册账号.

    流程：
        1. 检查 username 是否已存在；
        2. 创建 User；
        3. 创建 UserIdentity（密码 bcrypt 哈希）；
    """
    provider = get_provider(IdentityType.USERNAME)

    # 1. 检查用户名是否已存在
    exists = await db.scalar(
        select(UserIdentity.id).where(
            UserIdentity.identity_type == IdentityType.USERNAME.value,
            UserIdentity.identifier == username,
        )
    )
    if exists is not None:
        raise ConflictError("用户名已存在")

    # 2. 创建用户主体
    user = User(nickname=username, status=1)
    db.add(user)
    await db.flush()  # 刷新以获取 user.id

    # 3. 创建账号密码身份（内部完成密码哈希）
    await provider.create_identity(db, user, username, password)

    await db.commit()
    await db.refresh(user)
    return user


async def login(db: AsyncSession, username: str, password: str) -> dict[str, Any]:
    """账号登录：校验身份并签发 JWT.

    返回 {access_token, token_type, user_id}。
    """
    provider = get_provider(IdentityType.USERNAME)
    user = await provider.authenticate(db, username, password)
    return _issue_token(user)


async def send_phone_code(db: AsyncSession, phone: str, client_ip: str) -> dict[str, Any]:
    """发送手机验证码（登录用）."""
    return await send_verification_code(phone, client_ip)


async def login_by_phone(db: AsyncSession, phone: str, code: str) -> dict[str, Any]:
    """手机号验证码登录.

    流程：
        1. 手机号格式校验；
        2. 阿里云 CheckSmsVerifyCode（VerifyResult == PASS）；
        3. 查询 UserIdentity(phone)：
           存在 → 登录原 User；
           不存在 → 创建新 User + phone identity；
        4. 签发 JWT。
    """
    phone = validate_phone(phone)
    _validate_code_format(code)

    # 核验验证码（错误/过期统一返回，不泄露验证码具体状态）
    provider = get_sms_provider()
    verified = await provider.verify_code(phone, code)
    if not verified:
        raise UnauthorizedError("验证码错误或已过期")

    phone_provider = get_provider(IdentityType.PHONE)
    user = await phone_provider.find_user(db, phone)

    if user is None:
        # 新手机号首次登录：创建 User + phone identity
        user = User(nickname=f"用户{mask_phone(phone)}", status=1)
        db.add(user)
        await db.flush()
        await phone_provider.create_identity(db, user, phone)
    elif user.status != 1:
        raise ForbiddenError("账号已被禁用")

    await db.commit()
    return _issue_token(user)


async def login_by_phone_password(db: AsyncSession, phone: str, password: str) -> dict[str, Any]:
    """Log in with the password attached to the verified phone identity."""
    phone = validate_phone(phone)
    identity = await db.scalar(
        select(UserIdentity).where(
            UserIdentity.identity_type == IdentityType.PHONE.value,
            UserIdentity.identifier == phone,
        )
    )
    if identity is None or not identity.credential or not verify_password(password, identity.credential):
        raise UnauthorizedError("手机号或密码错误")
    user = await db.get(User, identity.user_id)
    if user is None or user.status != 1:
        raise UnauthorizedError("手机号或密码错误")
    return _issue_token(user)


async def set_phone_password(
    db: AsyncSession, user_id: int, phone: str, code: str, new_password: str
) -> dict[str, Any]:
    """Set a phone password only after a fresh SMS verification."""
    phone = validate_phone(phone)
    _validate_code_format(code)
    if not await get_sms_provider().verify_code(phone, code):
        raise UnauthorizedError("验证码错误或已过期")
    identity = await db.scalar(
        select(UserIdentity).where(
            UserIdentity.identity_type == IdentityType.PHONE.value,
            UserIdentity.identifier == phone,
            UserIdentity.user_id == user_id,
        )
    )
    if identity is None:
        raise ForbiddenError("手机号不属于当前用户")
    identity.credential = hash_password(new_password)
    user = await db.get(User, user_id)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    return {"phone": mask_phone(phone), "password_set": True}


async def reset_phone_password(db: AsyncSession, phone: str, code: str, new_password: str) -> dict[str, Any]:
    """Reset a phone password after SMS verification without leaking account existence."""
    phone = validate_phone(phone)
    _validate_code_format(code)
    if not await get_sms_provider().verify_code(phone, code):
        raise UnauthorizedError("验证码错误或已过期")
    identity = await db.scalar(
        select(UserIdentity).where(
            UserIdentity.identity_type == IdentityType.PHONE.value,
            UserIdentity.identifier == phone,
        )
    )
    if identity is None:
        raise UnauthorizedError("验证码错误或账号不可用")
    identity.credential = hash_password(new_password)
    user = await db.get(User, identity.user_id)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    return {"password_reset": True}


def _validate_code_format(code: str) -> None:
    """验证码格式校验：6 位数字."""
    if not code or not code.isdigit() or len(code) != 6:
        raise BusinessError("验证码格式不正确", code=400, status_code=400)


def _issue_token(user: User) -> dict[str, Any]:
    """为指定用户签发访问令牌（绑定令牌版本，支持密码重置后撤销旧会话）."""
    access_token = create_access_token(user.id, token_version=user.token_version)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
    }
