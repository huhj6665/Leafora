"""邮件发送抽象接口.

业务代码依赖 ``EmailSender`` 接口而非具体 SMTP 实现。
自动化测试使用 ``MockEmailSender`` 替换真实实现，绝不发送真实邮件。
"""
from abc import ABC, abstractmethod


class EmailSender(ABC):
    """邮件发送提供者基类."""

    name: str = "base"

    @abstractmethod
    async def send_mail(self, to: str, subject: str, body_html: str) -> None:
        """发送一封邮件.

        参数:
            to:         收件邮箱
            subject:    主题
            body_html:  正文（HTML）
        发送失败应抛出异常，绝不静默标记成功。
        """
        raise NotImplementedError
