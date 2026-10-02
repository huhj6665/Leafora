"""邮箱绑定与密码找回相关请求 Schema."""
import re

from pydantic import BaseModel, Field, field_validator


def _validate_new_password(v: str) -> str:
    """新密码强度校验：至少包含一个字母和一个数字（与注册一致）."""
    v = v.strip()
    if not re.search(r"[a-zA-Z]", v) or not re.search(r"\d", v):
        raise ValueError("密码至少包含一个字母和一个数字")
    return v


class SendBindEmailCodeRequest(BaseModel):
    """发送邮箱绑定验证码请求."""

    email: str = Field(..., description="待绑定邮箱")


class BindEmailRequest(BaseModel):
    """确认邮箱绑定请求."""

    email: str = Field(..., description="待绑定邮箱")
    code: str = Field(..., description="6 位验证码")


class ForgotPasswordRequest(BaseModel):
    """申请密码重置请求（公开接口，统一响应防枚举）."""

    email: str = Field(..., description="已绑定邮箱")


class ResetPasswordRequest(BaseModel):
    """设置新密码请求."""

    email: str = Field(..., description="已绑定邮箱")
    code: str = Field(..., description="6 位验证码")
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return _validate_new_password(v)


class SmtpTestRequest(BaseModel):
    """开发环境 SMTP 发信测试请求."""

    to_email: str = Field(..., description="测试收件邮箱")
