"""手机号校验、标准化与脱敏工具.

中国大陆手机号规则：1 开头，第二位 3-9，共 11 位数字。
"""
import re

from app.core.exceptions import BusinessError

# 大陆手机号：1[3-9] + 9 位数字
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def normalize_phone(phone: str) -> str:
    """去除空白与分隔符，返回纯数字串（不校验合法性）."""
    return re.sub(r"[\s\-+()]", "", phone or "").strip()


def is_valid_phone(phone: str) -> bool:
    """校验是否为合法大陆手机号."""
    return bool(_PHONE_RE.match(normalize_phone(phone)))


def validate_phone(phone: str) -> str:
    """校验并返回标准化手机号，非法则抛出业务异常."""
    normalized = normalize_phone(phone)
    if not _PHONE_RE.match(normalized):
        raise BusinessError("手机号格式不正确", code=400, status_code=400)
    return normalized


def mask_phone(phone: str) -> str:
    """手机号脱敏：138****5678."""
    normalized = normalize_phone(phone)
    if len(normalized) != 11:
        return normalized  # 非标准长度不强行脱敏
    return f"{normalized[:3]}****{normalized[7:]}"
