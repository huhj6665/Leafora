"""邮件发送模块.

通过 ``EmailSender`` 接口抽象邮件发送能力，按配置切换：

- ``APP_ENV=test``：内存 Mock（自动化测试，不发送真实邮件）。
- ``SMTP_USERNAME / SMTP_PASSWORD / SMTP_FROM_EMAIL`` 已配置：真实 SMTP。
- 其他情况：未配置发送器，调用时抛出可诊断错误，绝不把失败标记为成功。
"""
from app.core.config import settings
from app.core.exceptions import BusinessError
from app.services.email.base import EmailSender
from app.services.email.mock import MockEmailSender

_provider: EmailSender | None = None


class _NotConfiguredEmailSender(EmailSender):
    """SMTP 未配置时的占位发送器，调用即失败."""

    name = "not_configured"

    async def send_mail(self, to: str, subject: str, body_html: str) -> None:
        raise BusinessError(
            "邮件服务未配置，请在 backend/.env 中填写 SMTP_USERNAME / SMTP_PASSWORD / SMTP_FROM_EMAIL",
            code=500,
            status_code=500,
        )


def _build_provider() -> EmailSender:
    if settings.APP_ENV == "test":
        return MockEmailSender()
    if settings.smtp_configured:
        from app.services.email.smtp import build_smtp_sender

        return build_smtp_sender()
    return _NotConfiguredEmailSender()


def get_email_sender() -> EmailSender:
    """返回进程内单例邮件发送器."""
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider


def reset_email_sender() -> None:
    """重置发送器（测试隔离用）."""
    global _provider
    _provider = None


__all__ = [
    "EmailSender",
    "MockEmailSender",
    "get_email_sender",
    "reset_email_sender",
]
