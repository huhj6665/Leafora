"""账号安全接口：邮箱绑定 / 密码找回 / SMTP 发信测试.

- 邮箱绑定接口要求有效 JWT（用户 ID 由令牌确定，不接受前端指定）。
- 密码找回为公开接口，采用统一响应防账号枚举。
- SMTP 测试接口仅开发环境可用。
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.exceptions import ForbiddenError
from app.database.session import get_db
from app.models.user import User
from app.schemas.account_security import (
    BindEmailRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SendBindEmailCodeRequest,
    SmtpTestRequest,
)
from app.services import account_security_service
from app.utils.response import ok

router = APIRouter(tags=["账号安全"])


def _client_ip(request: Request) -> str:
    """提取客户端 IP（优先 X-Forwarded-For，其次直连地址）."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# 邮箱绑定（需登录）
# ---------------------------------------------------------------------------
@router.get("/user/email", summary="获取邮箱绑定状态")
async def get_email_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前账号邮箱绑定状态（脱敏）."""
    data = await account_security_service.get_email_status(db, current_user)
    return ok(data)


@router.post("/user/email/send-code", summary="发送邮箱绑定验证码")
async def send_bind_email_code(
    req: SendBindEmailCodeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """已登录用户绑定邮箱前发送验证码（需要 JWT）."""
    data = await account_security_service.send_bind_code(
        db, current_user, req.email, _client_ip(request)
    )
    return ok(data)


@router.post("/user/email/bind", summary="确认邮箱绑定")
async def bind_email(
    req: BindEmailRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """校验验证码并绑定邮箱到当前用户（需要 JWT）."""
    data = await account_security_service.confirm_bind(
        db, current_user, req.email, req.code
    )
    return ok(data)


# ---------------------------------------------------------------------------
# 密码找回（公开接口）
# ---------------------------------------------------------------------------
@router.post("/auth/forgot-password", summary="申请密码重置")
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """申请密码重置（统一响应，不泄露邮箱是否存在/已绑定）."""
    data = await account_security_service.request_password_reset(
        db, req.email, _client_ip(request)
    )
    return ok(data)


@router.post("/auth/reset-password", summary="设置新密码")
async def reset_password(
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """校验重置验证码并设置新密码（成功后撤销旧会话）."""
    data = await account_security_service.reset_password(
        db, req.email, req.code, req.new_password
    )
    return ok(data)


# ---------------------------------------------------------------------------
# 开发环境 SMTP 发信测试
# ---------------------------------------------------------------------------
@router.post("/dev/smtp-test", summary="SMTP 发信测试（仅开发环境）")
async def smtp_test(
    req: SmtpTestRequest,
):
    """向指定邮箱发送一封测试邮件，验证 SMTP 配置与链路."""
    if not settings.ENABLE_DEV_TOOLS:
        raise ForbiddenError("该接口仅在开发环境可用")
    data = await account_security_service.send_test_email(req.to_email)
    return ok(data)
