"""身份提供者注册中心.

未来新增登录方式时，只需实现新的 IdentityProvider 并在此处注册，
认证业务代码无需修改。
"""
from app.models.identity import IdentityType
from app.services.identity.base import IdentityProvider
from app.services.identity.phone_provider import PhoneIdentityProvider
from app.services.identity.username_provider import UsernameIdentityProvider

# 身份类型 -> 提供者实例 映射
PROVIDERS: dict[IdentityType, IdentityProvider] = {
    IdentityType.USERNAME: UsernameIdentityProvider(),
    IdentityType.PHONE: PhoneIdentityProvider(),
    # 未来扩展示例：
    # IdentityType.WECHAT: WechatIdentityProvider(),
    # IdentityType.EMAIL: EmailIdentityProvider(),
}


def get_provider(identity_type: IdentityType) -> IdentityProvider:
    """根据身份类型获取对应的提供者实例."""
    provider = PROVIDERS.get(identity_type)
    if provider is None:
        raise ValueError(f"未注册的身份类型: {identity_type}")
    return provider
