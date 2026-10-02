"""短信服务抽象接口.

业务代码依赖 ``SMSProvider`` 接口而非具体供应商实现。
本平台使用阿里云「号码认证服务」（短信认证）：
    - ``send_code``   对应 SendSmsVerifyCode（发送验证码）
    - ``verify_code`` 对应 CheckSmsVerifyCode（核验验证码）

自动化测试使用 ``MockSMSProvider`` 替换真实实现，绝不发送真实收费短信。
"""
from abc import ABC, abstractmethod
from typing import Optional


class SMSProvider(ABC):
    """短信发送/核验提供者基类."""

    name: str = "base"

    @abstractmethod
    async def send_code(self, phone: str) -> Optional[str]:
        """向手机号发送验证码.

        参数:
            phone: 标准化后的手机号
        返回:
            业务 ID（biz_id），可选；发送失败抛出异常。
        """
        raise NotImplementedError

    @abstractmethod
    async def verify_code(self, phone: str, code: str) -> bool:
        """核验验证码是否有效.

        参数:
            phone: 标准化后的手机号
            code:  用户输入的验证码
        返回:
            是否核验通过（True = PASS）。
        """
        raise NotImplementedError
