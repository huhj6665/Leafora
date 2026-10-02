"""安全工具：密码哈希与校验.

使用 passlib + bcrypt 进行密码哈希，禁止明文存储密码。
"""
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt 密码哈希上下文。
# schemes=["bcrypt"] 表示使用 bcrypt 算法；
# deprecated="auto" 表示当未来更换更安全的算法时，旧哈希可自动升级。
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)


def hash_password(plain: str) -> str:
    """对明文密码进行 bcrypt 哈希，返回哈希字符串."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与已存储的哈希是否匹配."""
    return pwd_context.verify(plain, hashed)


def hash_device_secret(plain: str) -> str:
    """设备长期凭据只保存 bcrypt 摘要，原文仅在创建/轮换时展示一次。"""
    return pwd_context.hash(plain)


def verify_device_secret(plain: str, stored: str) -> bool:
    """校验设备凭据；兼容 V2 旧库中的明文值，便于无停机迁移。"""
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return pwd_context.verify(plain, stored)
        except ValueError:
            return False
    # 旧数据仅过渡使用常数时间比较；成功认证后依赖层会自动升级为哈希。
    import hmac
    return hmac.compare_digest(plain, stored)
