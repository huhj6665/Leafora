"""短信验证码发送业务（手机号校验 + 服务端限流 + 发送）.

登录与绑定共享同一发送流程。限流为服务端强制，前端倒计时仅为 UI 提示。

关键：限流采用「先探测 → 发送 → 成功后记录」，
发送失败（配置错误 / 阿里云异常 / 网络错误）不会消耗限流额度。
"""
import logging
from typing import Any

from app.core.config import settings
from app.core.exceptions import BusinessError
from app.services.rate_limit import rate_limiter
from app.services.sms import get_sms_provider
from app.utils.phone import mask_phone, validate_phone

logger = logging.getLogger("app.sms")


def _peek(
    label: str,
    key: str,
    limit: int,
    window: int,
    message: str,
    masked_phone: str,
) -> None:
    """限流探测：超限抛出 429 业务异常（不消耗额度）."""
    result = rate_limiter.check(key, limit, window)
    if not result.allowed:
        logger.warning(
            "LOCAL_RATE_LIMIT rule=%s phone=%s retry_after=%ss",
            label,
            masked_phone,
            result.retry_after,
        )
        raise BusinessError(
            message,
            code=429,
            status_code=429,
            data={"retry_after": result.retry_after},
        )


async def send_verification_code(phone: str, client_ip: str) -> dict[str, Any]:
    """发送验证码.

    返回脱敏后的手机号；不返回、不记录验证码本身。
    """
    phone = validate_phone(phone)
    masked = mask_phone(phone)

    rules = [
        # (label, key, limit, window, message)
        ("phone_interval", f"phone:interval:{phone}", 1, 60, "发送过于频繁，请稍后再试"),
        ("phone_daily", f"phone:daily:{phone}", 10, 86400, "该手机号今日发送次数已达上限"),
        ("ip_interval", f"ip:interval:{client_ip}", 3, 60, "操作过于频繁，请稍后再试"),
        ("ip_daily", f"ip:daily:{client_ip}", 30, 86400, "今日发送次数已达上限"),
    ]

    # 1. 先探测（不消耗额度）
    if settings.RATE_LIMIT_ENABLED:
        for label, key, limit, window, message in rules:
            _peek(label, key, limit, window, message, masked)

    # 2. 发送（失败不消耗额度，由 provider 分类并记录日志）
    try:
        await get_sms_provider().send_code(phone)
    except BusinessError:
        raise
    except Exception as exc:  # noqa: BLE001 - 兜底，避免泄露内部信息
        logger.error("SMS_SEND_ERROR category=UNKNOWN phone=%s desc=%s", masked, str(exc)[:200])
        raise BusinessError(
            "验证码发送失败，请稍后再试", code=502, status_code=502
        ) from exc

    # 3. 发送成功后记录额度
    if settings.RATE_LIMIT_ENABLED:
        for _, key, _, _, _ in rules:
            rate_limiter.record(key)

    # 仅返回脱敏手机号，绝不返回验证码
    return {"phone": masked}
