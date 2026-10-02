"""Mock 邮件发送器（仅用于自动化测试）.

在内存中记录发送的邮件，不进行任何网络连接。可模拟发送失败。

测试辅助：
    - ``get_code(to)`` 从最近一封发送给该收件邮箱的正文中提取 6 位验证码。
    - ``sent`` 记录全部发送明细。
"""
import re
from typing import Optional

from app.services.email.base import EmailSender

# 从正文中提取 6 位数字验证码
_CODE_RE = re.compile(r"\b(\d{6})\b")


class MockEmailSender(EmailSender):
    """内存版邮件发送器，用于单元测试."""

    name = "mock"

    def __init__(self) -> None:
        # 发送明细：[{to, subject, body}]
        self.sent: list[dict] = []
        # 为 True 时下一次 send_mail 抛出异常，模拟发送失败
        self.fail_send: bool = False

    async def send_mail(self, to: str, subject: str, body_html: str) -> None:
        if self.fail_send:
            raise RuntimeError("模拟邮件发送失败")
        self.sent.append({"to": to, "subject": subject, "body": body_html})

    # ---- 测试辅助 ----
    def get_code(self, to: str) -> Optional[str]:
        """返回最近一封发送给该邮箱正文中的 6 位验证码（仅测试用）.

        按小写比较，与业务层规范化一致。
        """
        target = (to or "").lower()
        for item in reversed(self.sent):
            if (item["to"] or "").lower() == target:
                m = _CODE_RE.search(item["body"])
                if m:
                    return m.group(1)
        return None

    def reset(self) -> None:
        """清空状态（测试隔离用）."""
        self.sent.clear()
        self.fail_send = False
