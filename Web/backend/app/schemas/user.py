"""用户相关请求与响应 Schema."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


PROFILE_AVATARS = {"preset:leaf", "preset:field", "preset:path"}


class IdentityItem(BaseModel):
    """登录身份项."""

    identity_type: str
    identifier: str
    created_at: Optional[datetime] = None


class UserProfileData(BaseModel):
    """用户信息响应数据."""

    user_id: int
    nickname: str
    avatar: Optional[str] = None
    status: int
    email: Optional[str] = None
    email_verified: bool = False
    has_phone_password: bool = False
    created_at: Optional[datetime] = None
    identities: List[IdentityItem] = []


class UpdateUserProfileRequest(BaseModel):
    """只允许当前用户修改昵称和预设头像。"""

    model_config = ConfigDict(extra="forbid")

    nickname: Optional[str] = Field(default=None, min_length=2, max_length=32)
    avatar: Optional[str] = Field(default=None, max_length=32)

    @field_validator("nickname")
    @classmethod
    def _normalize_nickname(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            raise ValueError("昵称不能为空")
        value = value.strip()
        if len(value) < 2:
            raise ValueError("昵称至少 2 个字符")
        return value

    @field_validator("avatar")
    @classmethod
    def _validate_avatar(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PROFILE_AVATARS:
            raise ValueError("头像预设无效")
        return value

class CurrentPhonePasswordRequest(BaseModel):
    """当前账号通过短信验证码设置或更新手机号密码。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, value: str) -> str:
        import re

        if not re.search(r"[a-zA-Z]", value) or not re.search(r"\d", value):
            raise ValueError("密码至少包含一个字母和一个数字")
        return value


class PhoneBindRequest(BaseModel):
    """绑定手机号请求."""

    phone: str = Field(..., description="手机号")
    code: str = Field(..., description="6 位验证码")
