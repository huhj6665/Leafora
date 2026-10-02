"""Browser QR login sessions confirmed by an authenticated mini-program user."""
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError, UnauthorizedError
from app.models.protocol import WebLoginSession
from app.models.user import User
from app.services.jwt_service import create_access_token
from app.services.protocol_tokens import new_token, token_hash, token_matches

TTL_SECONDS = 120
MAX_ATTEMPTS = 5


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return _aware(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def create_session(db: AsyncSession) -> dict[str, Any]:
    scan_token, poll_token = new_token(), new_token()
    session_id = f"LOGIN_{new_token()[:24]}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TTL_SECONDS)
    row = WebLoginSession(
        login_session_id=session_id,
        scan_token_hash=token_hash(scan_token),
        poll_token_hash=token_hash(poll_token),
        expires_at=expires_at,
    )
    db.add(row)
    await db.commit()
    return {
        "type": "tld_web_login", "version": "1.0",
        "login_session_id": session_id, "scan_token": scan_token,
        "poll_token": poll_token, "expires_at": _iso(expires_at),
    }


async def _locked(db: AsyncSession, session_id: str) -> WebLoginSession:
    row = await db.scalar(
        select(WebLoginSession).where(WebLoginSession.login_session_id == session_id).with_for_update()
    )
    if row is None:
        raise NotFoundError("登录会话不存在")
    if row.status not in {"CONSUMED", "CANCELLED", "EXPIRED"} and _aware(row.expires_at) <= datetime.now(timezone.utc):
        row.status = "EXPIRED"
        await db.commit()
    return row


async def confirm(db: AsyncSession, session_id: str, scan_token: str, user_id: int) -> dict[str, Any]:
    row = await _locked(db, session_id)
    if row.status != "PENDING":
        raise BusinessError(f"登录会话状态为 {row.status}", code=409, status_code=409)
    if not token_matches(scan_token, row.scan_token_hash):
        row.attempts += 1
        if row.attempts >= MAX_ATTEMPTS:
            row.status = "CANCELLED"
        await db.commit()
        raise UnauthorizedError("扫码凭证无效")
    now = datetime.now(timezone.utc)
    row.status = "CONFIRMED"
    row.confirmed_user_id = user_id
    row.confirmed_at = now
    await db.commit()
    return {"login_session_id": session_id, "status": "CONFIRMED"}


async def poll(db: AsyncSession, session_id: str, poll_token: str) -> dict[str, Any]:
    row = await _locked(db, session_id)
    if not token_matches(poll_token, row.poll_token_hash):
        row.attempts += 1
        if row.attempts >= MAX_ATTEMPTS and row.status == "PENDING":
            row.status = "CANCELLED"
        await db.commit()
        raise UnauthorizedError("轮询凭证无效")
    data: dict[str, Any] = {
        "login_session_id": session_id, "status": row.status, "expires_at": _iso(row.expires_at)
    }
    if row.status == "CONFIRMED":
        user = await db.get(User, row.confirmed_user_id)
        if user is None or user.status != 1:
            row.status = "CANCELLED"
            await db.commit()
            raise UnauthorizedError("确认用户不可用")
        data.update({
            "access_token": create_access_token(user.id, token_version=user.token_version),
            "token_type": "bearer", "user_id": user.id, "status": "CONSUMED",
        })
        row.status = "CONSUMED"
        row.consumed_at = datetime.now(timezone.utc)
        await db.commit()
    return data


async def cancel(db: AsyncSession, session_id: str, poll_token: str) -> dict[str, Any]:
    row = await _locked(db, session_id)
    if not token_matches(poll_token, row.poll_token_hash):
        raise UnauthorizedError("轮询凭证无效")
    if row.status != "PENDING":
        raise BusinessError(f"登录会话状态为 {row.status}", code=409, status_code=409)
    row.status = "CANCELLED"
    await db.commit()
    return {"login_session_id": session_id, "status": "CANCELLED"}
