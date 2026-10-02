"""用户信息接口."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.auth import SendPhoneCodeRequest
from app.schemas.user import (
    CurrentPhonePasswordRequest,
    PhoneBindRequest,
    UpdateUserProfileRequest,
)
from app.services import user_service
from app.utils.response import ok

router = APIRouter(prefix="/user", tags=["用户"])


@router.get("/profile", summary="获取当前用户信息")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前登录用户的信息与登录身份列表（需要 JWT）."""
    data = await user_service.get_profile_data(db, current_user)
    return ok(data)


@router.patch("/profile", summary="更新当前用户资料")
async def update_profile(
    req: UpdateUserProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """仅更新昵称和预设头像；身份、状态与创建时间均不可修改。"""
    data = await user_service.update_profile(db, current_user, req)
    return ok(data)


@router.post(
    "/security/phone-password/send-code",
    summary="向当前账号手机号发送密码验证码",
)
async def send_current_phone_password_code(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fwd = request.headers.get("x-forwarded-for")
    client_ip = fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown"
    )
    data = await user_service.send_current_phone_password_code(
        db, current_user, client_ip
    )
    return ok(data)


@router.post(
    "/security/phone-password",
    summary="设置或更新当前账号手机号密码",
)
async def set_current_phone_password(
    req: CurrentPhonePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await user_service.set_current_phone_password(
        db, current_user, req.code, req.new_password
    )
    return ok(data)


@router.post("/phone/send-code", summary="发送绑定手机号验证码")
async def send_bind_phone_code(
    req: SendPhoneCodeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """已登录用户绑定手机号前发送验证码（需要 JWT）."""
    fwd = request.headers.get("x-forwarded-for")
    client_ip = fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown"
    )
    data = await user_service.send_bind_phone_code(
        db, current_user, req.phone, client_ip
    )
    return ok(data)


@router.post("/phone/bind", summary="绑定手机号")
async def bind_phone(
    req: PhoneBindRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """绑定手机号到当前用户（需要 JWT，需短信验证码）."""
    data = await user_service.bind_phone(db, current_user, req.phone, req.code)
    return ok(data)
