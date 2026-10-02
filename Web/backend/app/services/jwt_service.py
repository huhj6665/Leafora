"""JWT 生成与解析服务.

Token 载荷内容包含 user_id 与 exp（过期时间）。
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError


def create_access_token(
    user_id: int,
    expires_minutes: Optional[int] = None,
    token_version: Optional[int] = None,
) -> str:
    """生成访问令牌.

    payload 同时写入标准 ``sub``（subject，用户ID）与 ``user_id``，
    便于遵循 JWT 规范并保持向后兼容。
    当提供 ``token_version`` 时写入 ``ver`` 声明，用于密码重置后撤销旧会话。

    参数:
        user_id:         用户ID
        expires_minutes: 令牌有效期（分钟），缺省使用配置值
        token_version:   令牌版本，用于会话撤销
    """
    expire_minutes = expires_minutes or settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "user_id": user_id,
        "iat": now,
        "exp": expire,
    }
    if token_version is not None:
        payload["ver"] = token_version
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_token(token: str) -> dict[str, Any]:
    """解析并校验 JWT，失败抛出 UnauthorizedError."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("登录已过期，请重新登录") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("无效的访问令牌") from exc
