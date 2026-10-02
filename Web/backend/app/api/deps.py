"""通用依赖注入：当前用户认证.

get_current_user 解析请求中的 Bearer Token，校验 JWT 并返回当前 User。
所有需要登录的接口通过 Depends(get_current_user) 引入该依赖。
"""
import logging

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.config import settings
from app.database.session import get_db
from app.models.device import Device
from app.models.user import User
from app.services.jwt_service import decode_token
from app.core.security import hash_device_secret, verify_device_secret

logger = logging.getLogger("app.device_auth")

# 从 Authorization: Bearer <token> 中提取令牌；auto_error=False 便于自定义错误响应
bearer_scheme = HTTPBearer(auto_error=False)


def _device_auth_error(reason: str, detail: str, device_id: str | None = None) -> HTTPException:
    """Build a safe 401 and log its precise local troubleshooting reason."""
    logger.warning("设备 HTTP 认证失败 reason=%s device_id=%s", reason, device_id or "<missing>")
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail if settings.APP_ENV != "production" else "设备认证失败",
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """解析 Bearer Token 并返回当前登录用户.

    异常：
        401 未提供令牌 / 令牌无效 / 令牌过期
        403 账号被禁用
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息",
        )

    try:
        payload = decode_token(credentials.credentials)
    except UnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
        ) from exc

    user_id = payload.get("user_id")
    if user_id is None:
        # 兼容标准 sub 声明（字符串形式）
        sub = payload.get("sub")
        user_id = int(sub) if sub is not None else None
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的访问令牌",
        )

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    if user.status != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    # 令牌版本校验：密码重置后 token_version 自增，旧 JWT 立即失效。
    # 旧格式令牌（无 ver）按版本 0 处理，首次重置密码后同样失效。
    token_version = payload.get("ver", 0)
    if token_version != (user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态已失效，请重新登录",
        )
    return user


async def get_current_device(
    x_device_id: str | None = Header(None, alias="X-Device-ID"),
    x_device_secret: str | None = Header(None, alias="X-Device-Secret"),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """设备专用 HTTP 认证.

    通过请求头 ``X-Device-ID`` + ``X-Device-Secret`` 验证设备身份，
    使用常数时间比较校验密钥与 ``device_id`` 的对应关系。

    用于虚拟设备 / 未来真实 Jetson 的 HTTP 图片上传，独立于网站用户 JWT，
    设备不保存网站用户密码或 Access Token。
    """
    if not x_device_id or not x_device_secret:
        missing = []
        if not x_device_id:
            missing.append("X-Device-ID")
        if not x_device_secret:
            missing.append("X-Device-Secret")
        raise _device_auth_error(
            "missing_header",
            f"缺少设备认证请求头：{', '.join(missing)}",
            x_device_id,
        )

    device = await db.scalar(
        select(Device).where(Device.device_id == x_device_id)
    )
    if device is None:
        raise _device_auth_error("device_not_found", "设备不存在", x_device_id)
    if device.status != 1:
        raise _device_auth_error("device_disabled", "设备已禁用", x_device_id)

    # 常数时间比较，避免时序侧信道；secret 为空时直接判失败
    if not device.device_secret:
        raise _device_auth_error("stored_secret_missing", "设备未配置认证凭据", x_device_id)
    if not verify_device_secret(x_device_secret, device.device_secret):
        raise _device_auth_error("secret_mismatch", "设备密钥不匹配", x_device_id)
    # 旧库凭据在首次成功认证后原地升级为不可逆摘要，不改变设备侧 secret。
    if not device.device_secret.startswith(("$2a$", "$2b$", "$2y$")):
        device.device_secret = hash_device_secret(x_device_secret)
        await db.commit()
    return device
