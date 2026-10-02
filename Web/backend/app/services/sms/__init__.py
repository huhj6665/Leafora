"""短信服务模块.

通过 ``SMSProvider`` 接口抽象短信发送/核验能力，
按配置在阿里云与 Mock 实现之间切换：

- ``SMS_PROVIDER=aliyun``：使用阿里云号码认证服务（真实发送）。
- ``SMS_PROVIDER=mock``：使用内存 Mock（自动化测试，不发送真实短信）。
- 未显式指定时：若已配置阿里云 AccessKey 则使用阿里云，否则回退 Mock。
"""
from app.core.config import settings
from app.services.sms.base import SMSProvider
from app.services.sms.mock import MockSMSProvider

_provider: SMSProvider | None = None


def _build_provider() -> SMSProvider:
    chosen = (settings.SMS_PROVIDER or "").strip().lower()
    if chosen == "mock":
        return MockSMSProvider()
    if chosen == "aliyun":
        from app.services.sms.aliyun import build_aliyun_provider

        return build_aliyun_provider()
    # 自动选择：配置了阿里云凭据则用真实，否则 Mock（避免误发真实短信）
    if settings.sms_configured:
        from app.services.sms.aliyun import build_aliyun_provider

        return build_aliyun_provider()
    return MockSMSProvider()


def get_sms_provider() -> SMSProvider:
    """返回进程内单例短信提供者."""
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider


def reset_sms_provider() -> None:
    """重置提供者（测试隔离用）."""
    global _provider
    _provider = None


__all__ = [
    "SMSProvider",
    "MockSMSProvider",
    "get_sms_provider",
    "reset_sms_provider",
]
