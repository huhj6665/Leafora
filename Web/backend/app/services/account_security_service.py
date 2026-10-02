"""账号安全业务服务：邮箱绑定与密码找回.

设计要点：
    - 短数字验证码以 HMAC(服务端密钥) 摘要落库（``email_credentials``），不存明文。
    - 绑定凭据与重置凭据按 ``purpose`` 隔离，不可混用。
    - 凭据具备过期时间、一次性消费（``used_at``）与失败尝试限制（``attempts``）。
    - 公开找回接口返回统一响应，不泄露邮箱是否存在/已绑定。
    - 密码重置成功后自增 ``token_version``，撤销此前签发的全部 JWT。
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BusinessError, ConflictError, UnauthorizedError
from app.core.security import hash_password
from app.models.email_credential import EmailCredential, EmailCredentialPurpose
from app.models.identity import IdentityType, UserIdentity
from app.models.user import User
from app.services.email import get_email_sender
from app.services.rate_limit import rate_limiter
from app.utils.email import mask_email, normalize_email

logger = logging.getLogger("app.account_security")


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(expires_at: datetime) -> bool:
    """判断凭据是否过期（兼容 SQLite 返回 naive datetime 的情况）."""
    now = _utcnow()
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < now


def _generate_code() -> str:
    """生成 N 位纯数字验证码（无偏）."""
    return "".join(str(secrets.randbelow(10)) for _ in range(settings.EMAIL_CODE_LENGTH))


def _code_digest(purpose: str, user_id: int, email: str, code: str) -> str:
    """计算验证码的 HMAC 摘要（带用途/用户/邮箱绑定，防止跨用途与跨用户复用）."""
    msg = f"{purpose}:{user_id}:{email}:{code}"
    return hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _validate_code_format(code: str) -> None:
    """验证码格式校验."""
    if not code or not code.isdigit() or len(code) != settings.EMAIL_CODE_LENGTH:
        raise BusinessError("验证码格式不正确", code=400, status_code=400)


def _peek_limited(key: str, limit: int, window: int, message: str) -> None:
    """限流探测：超限抛出 429（不消耗额度）."""
    if not settings.RATE_LIMIT_ENABLED:
        return
    result = rate_limiter.check(key, limit, window)
    if not result.allowed:
        raise BusinessError(
            message, code=429, status_code=429, data={"retry_after": result.retry_after}
        )


def _record(key: str) -> None:
    """记录一次成功事件（消耗限流额度）."""
    if settings.RATE_LIMIT_ENABLED:
        rate_limiter.record(key)


async def _find_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """按规范化邮箱查找用户（email 列为规范化小写）."""
    return await db.scalar(select(User).where(User.email == email))


async def _store_credential(
    db: AsyncSession,
    purpose: EmailCredentialPurpose,
    user_id: int,
    email: str,
    code: str,
) -> EmailCredential:
    """生成并保存验证码凭据（仅 HMAC 摘要落库）."""
    cred = EmailCredential(
        purpose=purpose.value,
        user_id=user_id,
        email=email,
        code_digest=_code_digest(purpose.value, user_id, email, code),
        expires_at=_utcnow() + timedelta(seconds=settings.EMAIL_CODE_TTL_SECONDS),
    )
    db.add(cred)
    await db.flush()
    return cred


async def _verify_and_consume(
    db: AsyncSession,
    purpose: EmailCredentialPurpose,
    user_id: int,
    email: str,
    code: str,
) -> bool:
    """校验并一次性消费验证码凭据.

    返回 True 表示验证通过并已标记使用；False 表示错误/过期/已用/超次（失败会累计 attempts）。
    """
    cred = await db.scalar(
        select(EmailCredential)
        .where(
            EmailCredential.purpose == purpose.value,
            EmailCredential.user_id == user_id,
            EmailCredential.email == email,
            EmailCredential.used_at.is_(None),
        )
        .order_by(EmailCredential.id.desc())
        .limit(1)
    )
    if cred is None or _is_expired(cred.expires_at):
        return False
    if cred.attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
        return False

    expected = _code_digest(purpose.value, user_id, email, code)
    if not hmac.compare_digest(cred.code_digest, expected):
        cred.attempts += 1
        await db.flush()
        return False

    cred.used_at = _utcnow()
    await db.flush()
    return True


async def _send_code_email(email: str, code: str, action: str) -> None:
    """发送验证码邮件（失败抛出可诊断异常，绝不标记成功）."""
    subject = f"【{settings.SMTP_FROM_NAME}】{action}"
    ttl_minutes = max(1, settings.EMAIL_CODE_TTL_SECONDS // 60)
    body = (
        f"<p>您的{action}验证码为：<strong>{code}</strong></p>"
        f"<p>验证码 {ttl_minutes} 分钟内有效，请勿泄露给他人。</p>"
    )
    masked = mask_email(email)
    try:
        await get_email_sender().send_mail(email, subject, body)
    except BusinessError:
        raise
    except Exception as exc:  # noqa: BLE001 - 兜底，不泄露内部信息
        logger.error(
            "EMAIL_SEND_ERROR action=%s to=%s type=%s",
            action, masked, type(exc).__name__,
        )
        raise BusinessError("邮件发送失败，请稍后再试", code=502, status_code=502) from exc


async def _send_notification_email(email: str, action: str) -> None:
    """发送通知邮件（尽力而为，失败由调用方处理）."""
    subject = f"【{settings.SMTP_FROM_NAME}】{action}"
    body = f"<p>您的账号{action}。若非本人操作，请尽快登录并修改密码。</p>"
    await get_email_sender().send_mail(email, subject, body)


# ---------------------------------------------------------------------------
# 邮箱绑定（需登录）
# ---------------------------------------------------------------------------
def _bind_rule_keys(email: str, client_ip: str) -> list[tuple[str, int, int, str]]:
    """邮箱绑定发送限流维度（key, limit, window, message）."""
    return [
        (f"email:bind_interval:{email}", 1, 60, "发送过于频繁，请稍后再试"),
        (f"email:bind_daily:{email}", 10, 86400, "该邮箱今日发送次数已达上限"),
        (f"ip:bind_interval:{client_ip}", 3, 60, "操作过于频繁，请稍后再试"),
        (f"ip:bind_daily:{client_ip}", 30, 86400, "今日发送次数已达上限"),
    ]


async def get_email_status(db: AsyncSession, user: User) -> dict[str, Any]:
    """返回当前账号邮箱绑定状态."""
    return {
        "has_email": user.email is not None,
        "verified": user.email_verified_at is not None,
        "email": mask_email(user.email) if user.email else None,
    }


async def send_bind_code(
    db: AsyncSession, user: User, email: str, client_ip: str
) -> dict[str, Any]:
    """已登录用户绑定邮箱前发送验证码."""
    email = normalize_email(email)
    masked = mask_email(email)

    if user.email is not None:
        raise ConflictError("当前账号已绑定邮箱，如需更换请联系管理员")

    # 发送阶段即拦截他人已绑定邮箱（避免无效邮件与占用探测）
    owner = await _find_user_by_email(db, email)
    if owner is not None:
        raise ConflictError("该邮箱已被其他账号绑定")

    rules = _bind_rule_keys(email, client_ip)
    for key, limit, window, message in rules:
        _peek_limited(key, limit, window, message)

    code = _generate_code()
    await _store_credential(db, EmailCredentialPurpose.BIND, user.id, email, code)
    await _send_code_email(email, code, "邮箱绑定验证码")
    await db.commit()

    for key, _, _, _ in rules:
        _record(key)

    return {"email": masked}


async def confirm_bind(
    db: AsyncSession, user: User, email: str, code: str
) -> dict[str, Any]:
    """确认邮箱绑定：校验验证码 + 占用检查 + 写入 verified email."""
    email = normalize_email(email)
    _validate_code_format(code)

    if user.email is not None:
        raise ConflictError("当前账号已绑定邮箱")

    ok = await _verify_and_consume(db, EmailCredentialPurpose.BIND, user.id, email, code)
    if not ok:
        raise UnauthorizedError("验证码错误或已过期")

    # 占用检查（发送阶段已拦截，此处为并发兜底）
    owner = await _find_user_by_email(db, email)
    if owner is not None:
        raise ConflictError("该邮箱已被其他账号绑定")

    user.email = email
    user.email_verified_at = _utcnow()
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("该邮箱已被其他账号绑定") from exc

    return {"email": mask_email(email), "verified": True}


# ---------------------------------------------------------------------------
# 密码找回（公开接口）
# ---------------------------------------------------------------------------
_GENERIC_RESET_MESSAGE = "如果该邮箱已绑定，重置邮件将发送至该邮箱"


def _reset_rule_keys(email: str, client_ip: str) -> list[tuple[str, int, int, str]]:
    """密码找回限流维度（key, limit, window, message）."""
    return [
        (f"email:reset_interval:{email}", 1, 60, "操作过于频繁，请稍后再试"),
        (f"email:reset_daily:{email}", 10, 86400, "今日申请次数已达上限"),
        (f"ip:reset_interval:{client_ip}", 5, 60, "操作过于频繁，请稍后再试"),
        (f"ip:reset_daily:{client_ip}", 50, 86400, "今日申请次数已达上限"),
    ]


def _generic_reset_response() -> dict[str, Any]:
    return {"message": _GENERIC_RESET_MESSAGE}


async def request_password_reset(
    db: AsyncSession, email: str, client_ip: str
) -> dict[str, Any]:
    """申请密码重置（统一响应，不泄露邮箱是否存在/已绑定）."""
    try:
        normalized = normalize_email(email)
    except BusinessError:
        # 非法格式也返回统一响应，避免通过响应差异探测
        return _generic_reset_response()

    rules = _reset_rule_keys(normalized, client_ip)
    for key, limit, window, message in rules:
        _peek_limited(key, limit, window, message)

    user = await _find_user_by_email(db, normalized)
    if user is not None and user.email_verified_at is not None:
        code = _generate_code()
        await _store_credential(
            db, EmailCredentialPurpose.RESET, user.id, normalized, code
        )
        try:
            await _send_code_email(normalized, code, "密码重置验证码")
        except Exception:  # noqa: BLE001 - 不因发信失败泄露邮箱存在性
            await db.rollback()
            logger.error("EMAIL_RESET_SEND_FAILED to=%s", mask_email(normalized))
        else:
            await db.commit()

    for key, _, _, _ in rules:
        _record(key)

    return _generic_reset_response()


async def reset_password(
    db: AsyncSession, email: str, code: str, new_password: str
) -> dict[str, Any]:
    """校验重置验证码并设置新密码（成功后撤销旧会话）."""
    try:
        normalized = normalize_email(email)
    except BusinessError as exc:
        raise UnauthorizedError("重置链接无效或已过期") from exc

    _validate_code_format(code)

    user = await _find_user_by_email(db, normalized)
    if user is None or user.email_verified_at is None:
        raise UnauthorizedError("重置链接无效或已过期")

    ok = await _verify_and_consume(
        db, EmailCredentialPurpose.RESET, user.id, normalized, code
    )
    if not ok:
        raise UnauthorizedError("重置链接无效或已过期")

    # 正式手机号账号更新 phone 凭据；仍只使用 username 密码的历史混合账号
    # 继续更新 username，避免改变旧登录与找回语义。
    identities = (
        await db.execute(
            select(UserIdentity).where(
                UserIdentity.user_id == user.id,
                UserIdentity.identity_type.in_(
                    [IdentityType.PHONE.value, IdentityType.USERNAME.value]
                ),
            )
        )
    ).scalars().all()
    phone_identity = next(
        (i for i in identities if i.identity_type == IdentityType.PHONE.value), None
    )
    username_identity = next(
        (i for i in identities if i.identity_type == IdentityType.USERNAME.value), None
    )
    identity = (
        phone_identity
        if phone_identity is not None
        and (phone_identity.credential is not None or username_identity is None)
        else username_identity
    )
    if identity is None:
        raise UnauthorizedError("重置链接无效或已过期")

    identity.credential = hash_password(new_password)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()

    # 重置成功通知（尽力而为，失败不影响重置结果）
    try:
        await _send_notification_email(normalized, "密码已重置")
    except Exception:  # noqa: BLE001 - 通知失败不影响主流程
        logger.warning("EMAIL_NOTIFY_FAILED to=%s", mask_email(normalized))

    return {"message": "密码已重置，请使用新密码登录"}


# ---------------------------------------------------------------------------
# 开发环境 SMTP 发信测试
# ---------------------------------------------------------------------------
async def send_test_email(to_email: str) -> dict[str, Any]:
    """向指定邮箱发送一封测试邮件（仅开发环境，调用方负责开关控制）."""
    to_email = normalize_email(to_email)
    subject = f"【{settings.SMTP_FROM_NAME}】SMTP 测试邮件"
    body = (
        "<p>这是一封 SMTP 发信测试邮件。</p>"
        "<p>如果您收到本邮件，说明 SMTP 配置与发送链路正常。</p>"
    )
    await get_email_sender().send_mail(to_email, subject, body)
    return {"to_email": mask_email(to_email), "sent": True}
