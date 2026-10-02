"""Mock 短信提供者（仅用于自动化测试）.

模拟阿里云号码认证服务的行为：
    - send_code：生成 6 位数字验证码并存入内存，可模拟发送失败；
    - verify_code：校验并一次性消费验证码（防止重放）。

绝不发送真实短信。
"""
from typing import Optional

from app.services.sms.base import SMSProvider


class MockSMSProvider(SMSProvider):
    """内存版短信提供者，用于单元测试."""

    name = "mock"

    def __init__(self) -> None:
        # phone -> code；验证成功后删除，保证一次性使用
        self._codes: dict[str, str] = {}
        # 为 True 时下一次 send_code 抛出异常，模拟发送失败
        self.fail_send: bool = False

    async def send_code(self, phone: str) -> Optional[str]:
        if self.fail_send:
            raise RuntimeError("模拟短信发送失败")
        code = "123456"
        self._codes[phone] = code
        return None

    async def verify_code(self, phone: str, code: str) -> bool:
        expected = self._codes.get(phone)
        if expected is None or code != expected:
            return False
        # 一次性消费，防止同一验证码重复换取 JWT
        self._codes.pop(phone, None)
        return True

    # ---- 测试辅助 ----
    def get_code(self, phone: str) -> Optional[str]:
        """返回指定手机号当前验证码（仅测试用）."""
        return self._codes.get(phone)

    def reset(self) -> None:
        """清空状态（测试隔离用）."""
        self._codes.clear()
        self.fail_send = False
