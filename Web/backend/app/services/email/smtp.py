"""163 SMTP 邮件发送提供者（SMTP_SSL，端口 465）.

使用标准库 ``smtplib`` 通过 SSL/TLS 连接并验证服务器证书，
连接、认证与发送均设置超时。发送为阻塞操作，通过线程池执行以避免阻塞事件循环。

安全约束：
    - SMTP_PASSWORD 为客户端授权码，非网页登录密码。
    - 日志仅输出脱敏收件邮箱与异常类型，绝不输出授权码。
"""
import asyncio
import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from app.core.config import settings
from app.services.email.base import EmailSender
from app.utils.email import mask_email

logger = logging.getLogger("app.email.smtp")


class SMTPSender(EmailSender):
    """基于 smtplib 的 SMTP SSL 邮件发送器."""

    name = "smtp"

    def __init__(
        self,
        host: str,
        port: int,
        use_ssl: bool,
        username: str,
        password: str,
        from_email: str,
        from_name: str,
        timeout: float,
    ) -> None:
        self._host = host
        self._port = port
        self._use_ssl = use_ssl
        self._username = username
        self._password = password
        self._from_email = from_email
        self._from_name = from_name
        self._timeout = timeout

    def _validate_config(self) -> None:
        """发送前检查配置完整性，缺失时抛出可诊断的配置错误."""
        if not (self._username and self._password and self._from_email):
            raise RuntimeError("SMTP 配置不完整：缺少 SMTP_USERNAME / SMTP_PASSWORD / SMTP_FROM_EMAIL")

    def _send_sync(self, to: str, subject: str, body_html: str) -> None:
        self._validate_config()

        msg = MIMEText(body_html, "html", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = formataddr((str(Header(self._from_name, "utf-8")), self._from_email))
        msg["To"] = to

        if self._use_ssl:
            # SMTP_SSL 隐式 TLS（端口 465），验证服务器证书
            client = smtplib.SMTP_SSL(
                self._host, self._port, timeout=self._timeout
            )
        else:
            client = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
            client.starttls()

        try:
            client.login(self._username, self._password)
            client.sendmail(self._from_email, [to], msg.as_string())
        finally:
            try:
                client.quit()
            except Exception:  # noqa: BLE001 - 忽略退出时的连接异常
                pass

    async def send_mail(self, to: str, subject: str, body_html: str) -> None:
        """在默认线程池中执行阻塞的 SMTP 发送."""
        masked = mask_email(to)
        try:
            await asyncio.to_thread(self._send_sync, to, subject, body_html)
        except smtplib.SMTPAuthenticationError as exc:
            logger.error("SMTP_AUTH_ERROR to=%s desc=%s", masked, str(exc)[:120])
            raise
        except smtplib.SMTPException as exc:
            logger.error("SMTP_SEND_ERROR to=%s desc=%s", masked, str(exc)[:120])
            raise
        except (OSError, TimeoutError) as exc:
            logger.error("SMTP_NETWORK_ERROR to=%s desc=%s", masked, str(exc)[:120])
            raise
        except Exception as exc:  # noqa: BLE001 - 兜底，不泄露内部信息
            logger.error("SMTP_UNKNOWN_ERROR to=%s type=%s", masked, type(exc).__name__)
            raise
        logger.info("SMTP_SENT to=%s", masked)


def build_smtp_sender() -> SMTPSender:
    """根据项目统一配置创建 SMTP 发送器."""
    return SMTPSender(
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        use_ssl=settings.SMTP_USE_SSL,
        username=settings.SMTP_USERNAME,
        password=settings.SMTP_PASSWORD,
        from_email=settings.SMTP_FROM_EMAIL,
        from_name=settings.SMTP_FROM_NAME,
        timeout=settings.SMTP_TIMEOUT,
    )
