"""认证相关请求/响应 Schema."""
import re

from pydantic import BaseModel, Field, field_validator

# 用户名：3-32 位字母/数字/下划线
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class RegisterRequest(BaseModel):
    """注册请求."""

    username: str = Field(..., min_length=3, max_length=32, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        v = v.strip()
        if not _USERNAME_RE.match(v):
            raise ValueError("用户名须为 3-32 位字母、数字或下划线")
        return v

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        # 基本强度：至少包含一个字母和一个数字
        if not re.search(r"[a-zA-Z]", v) or not re.search(r"\d", v):
            raise ValueError("密码至少包含一个字母和一个数字")
        return v


class LoginRequest(BaseModel):
    """账号登录请求."""

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class SendPhoneCodeRequest(BaseModel):
    """发送手机验证码请求."""

    phone: str = Field(..., description="手机号")


class PhoneLoginRequest(BaseModel):
    """手机号验证码登录请求."""

    phone: str = Field(..., description="手机号")
    code: str = Field(..., description="6 位验证码")


class PhonePasswordLoginRequest(BaseModel):
    phone: str
    password: str = Field(..., min_length=6, max_length=128)


class PhonePasswordSetRequest(BaseModel):
    phone: str
    code: str
    new_password: str = Field(..., min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, value: str) -> str:
        if not re.search(r"[a-zA-Z]", value) or not re.search(r"\d", value):
            raise ValueError("密码至少包含一个字母和一个数字")
        return value


class PhonePasswordResetRequest(PhonePasswordSetRequest):
    pass


class QrSessionConfirmRequest(BaseModel):
    scan_token: str = Field(..., min_length=20, max_length=512)


class RegisterData(BaseModel):
    """注册响应数据."""

    user_id: int
    nickname: str


class TokenData(BaseModel):
    """登录响应数据."""

    access_token: str
    token_type: str = "bearer"
    user_id: int
