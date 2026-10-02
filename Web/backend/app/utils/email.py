"""邮箱校验、标准化与脱敏工具.

规则：
    - 统一转为小写存储与比较（大小写等价）。
    - 使用 email-validator 做格式校验（关闭可投递性 DNS 查询，离线可用）。
    - 脱敏展示本地部分，避免泄露完整邮箱。
"""
from email_validator import EmailNotValidError, validate_email as _validate_email

from app.core.exceptions import BusinessError


def normalize_email(email: str) -> str:
    """校验并标准化邮箱，统一转为小写；非法则抛出业务异常."""
    raw = (email or "").strip()
    if not raw:
        raise BusinessError("邮箱格式不正确", code=400, status_code=400)
    try:
        info = _validate_email(raw, check_deliverability=False)
    except EmailNotValidError as exc:
        raise BusinessError("邮箱格式不正确", code=400, status_code=400) from exc
    return info.normalized.lower()


def is_valid_email(email: str) -> bool:
    """校验邮箱格式是否合法（不抛异常）."""
    try:
        normalize_email(email)
        return True
    except BusinessError:
        return False


def mask_email(email: str) -> str:
    """邮箱脱敏：a***@163.com（保留首字符与域名）."""
    normalized = normalize_email(email)
    local, _, domain = normalized.partition("@")
    if not local:
        return normalized
    return f"{local[0]}***@{domain}"
