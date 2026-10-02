"""认证接口."""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.auth import (
    LoginRequest,
    PhoneLoginRequest,
    PhonePasswordLoginRequest,
    PhonePasswordResetRequest,
    PhonePasswordSetRequest,
    QrSessionConfirmRequest,
    RegisterRequest,
    SendPhoneCodeRequest,
)
from app.services import auth_service
from app.services import qr_login_service
from app.api.deps import get_current_user
from app.models.user import User
from app.utils.response import ok

router = APIRouter(prefix="/auth", tags=["认证"])


def _client_ip(request: Request) -> str:
    """提取客户端 IP（优先 X-Forwarded-For，其次直连地址）."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/register", summary="旧用户名注册（兼容/开发）")
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """注册新账号（用户名 + 密码），返回 user_id 与 nickname."""
    user = await auth_service.register(db, req.username, req.password)
    return ok({"user_id": user.id, "nickname": user.nickname})


@router.post("/login", summary="旧用户名登录（兼容/开发）")
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """账号登录，返回 JWT 访问令牌."""
    token_data = await auth_service.login(db, req.username, req.password)
    return ok(token_data)


@router.post("/send-phone-code", summary="发送手机验证码（登录）")
async def send_phone_code(
    req: SendPhoneCodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """发送登录验证码（服务端限流，不返回验证码）."""
    data = await auth_service.send_phone_code(
        db, req.phone, _client_ip(request)
    )
    return ok(data)


@router.post("/login-phone", summary="手机号验证码登录")
async def login_phone(
    req: PhoneLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """手机号验证码登录（新手机号自动注册），返回 JWT."""
    token_data = await auth_service.login_by_phone(db, req.phone, req.code)
    return ok(token_data)


@router.post("/login-phone-password", summary="手机号密码登录")
async def login_phone_password(req: PhonePasswordLoginRequest, db: AsyncSession = Depends(get_db)):
    return ok(await auth_service.login_by_phone_password(db, req.phone, req.password))


@router.post("/phone-password/send-code", summary="发送手机号密码验证码")
async def send_phone_password_code(
    req: SendPhoneCodeRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    return ok(await auth_service.send_phone_code(db, req.phone, _client_ip(request)))


@router.post("/phone-password/set", summary="验证手机号后设置密码")
async def set_phone_password(
    req: PhonePasswordSetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await auth_service.set_phone_password(db, user.id, req.phone, req.code, req.new_password))


@router.post("/phone-password/reset", summary="验证码重置手机号密码")
async def reset_phone_password(req: PhonePasswordResetRequest, db: AsyncSession = Depends(get_db)):
    return ok(await auth_service.reset_phone_password(db, req.phone, req.code, req.new_password))


@router.post("/qr-sessions", summary="创建 Web 扫码登录会话")
async def create_qr_session(db: AsyncSession = Depends(get_db)):
    return ok(await qr_login_service.create_session(db))


@router.get("/qr-sessions/{login_session_id}", summary="查询并一次性换取 Web 登录令牌")
async def poll_qr_session(
    login_session_id: str,
    poll_token: str = Query(..., min_length=20),
    db: AsyncSession = Depends(get_db),
):
    return ok(await qr_login_service.poll(db, login_session_id, poll_token))


@router.post("/qr-sessions/{login_session_id}/confirm", summary="小程序确认 Web 登录")
async def confirm_qr_session(
    login_session_id: str,
    req: QrSessionConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await qr_login_service.confirm(db, login_session_id, req.scan_token, user.id))


@router.delete("/qr-sessions/{login_session_id}", summary="取消 Web 扫码登录")
async def cancel_qr_session(
    login_session_id: str,
    poll_token: str = Query(..., min_length=20),
    db: AsyncSession = Depends(get_db),
):
    return ok(await qr_login_service.cancel(db, login_session_id, poll_token))
