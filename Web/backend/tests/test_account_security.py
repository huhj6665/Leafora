"""邮箱绑定与密码找回相关测试（使用 MockEmailSender，绝不发送真实邮件）."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models.device import Device, DeviceBinding
from app.models.email_credential import EmailCredential
from app.models.inspection import InspectionRecord
from app.models.user import User
from app.services.email import get_email_sender
from app.services.email.mock import MockEmailSender

REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/login"
PROFILE_URL = "/api/user/profile"
EMAIL_STATUS_URL = "/api/user/email"
EMAIL_SEND_URL = "/api/user/email/send-code"
EMAIL_BIND_URL = "/api/user/email/bind"
FORGOT_URL = "/api/auth/forgot-password"
RESET_URL = "/api/auth/reset-password"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register_login(client, username: str, password: str = "secret123") -> dict:
    await client.post(REGISTER_URL, json={"username": username, "password": password})
    r = await client.post(LOGIN_URL, json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _sender() -> MockEmailSender:
    sender = get_email_sender()
    assert isinstance(sender, MockEmailSender)
    return sender


async def _bind_email(client, token: str, email: str):
    """发送绑定验证码并完成绑定，返回绑定响应."""
    r = await client.post(EMAIL_SEND_URL, json={"email": email}, headers=_auth(token))
    assert r.status_code == 200, r.text
    code = _sender().get_code(email)
    assert code is not None, "Mock 邮件发送器未记录验证码"
    return await client.post(
        EMAIL_BIND_URL, json={"email": email, "code": code}, headers=_auth(token)
    )


# ---------------------------------------------------------------------------
# 邮箱绑定
# ---------------------------------------------------------------------------
async def test_bind_email_success(client):
    """已登录用户正常绑定邮箱，状态接口返回脱敏邮箱."""
    data = await _register_login(client, "bind_ok")
    token = data["access_token"]

    status_before = await client.get(EMAIL_STATUS_URL, headers=_auth(token))
    assert status_before.json()["data"]["has_email"] is False

    resp = await _bind_email(client, token, "Alice@Example.com")
    assert resp.status_code == 200
    assert resp.json()["data"]["verified"] is True
    assert resp.json()["data"]["email"] == "a***@example.com"

    status_after = await client.get(EMAIL_STATUS_URL, headers=_auth(token))
    body = status_after.json()["data"]
    assert body["has_email"] is True
    assert body["verified"] is True
    assert body["email"] == "a***@example.com"


async def test_bind_email_requires_auth(client):
    """未登录用户不能发送绑定验证码或绑定邮箱."""
    r = await client.post(EMAIL_SEND_URL, json={"email": "x@example.com"})
    assert r.status_code == 401
    r = await client.post(
        EMAIL_BIND_URL, json={"email": "x@example.com", "code": "123456"}
    )
    assert r.status_code == 401


async def test_bind_wrong_code(client):
    """错误验证码：绑定被拒绝."""
    data = await _register_login(client, "bind_wrong")
    token = data["access_token"]
    email = "wrong@example.com"
    await client.post(EMAIL_SEND_URL, json={"email": email}, headers=_auth(token))
    r = await client.post(
        EMAIL_BIND_URL, json={"email": email, "code": "000000"}, headers=_auth(token)
    )
    assert r.status_code == 401


async def test_bind_expired_code(client, session_factory):
    """过期验证码：绑定被拒绝."""
    data = await _register_login(client, "bind_expired")
    token = data["access_token"]
    email = "expired@example.com"
    await client.post(EMAIL_SEND_URL, json={"email": email}, headers=_auth(token))

    # 将凭据过期时间改为过去
    async with session_factory() as db:
        cred = await db.scalar(select(EmailCredential).where(EmailCredential.email == email))
        cred.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()

    code = _sender().get_code(email)
    r = await client.post(
        EMAIL_BIND_URL, json={"email": email, "code": code}, headers=_auth(token)
    )
    assert r.status_code == 401


async def test_bind_reused_code(client):
    """绑定成功后同一邮箱/验证码不可重复绑定."""
    data = await _register_login(client, "bind_reuse")
    token = data["access_token"]
    email = "reuse-bind@example.com"

    resp = await _bind_email(client, token, email)
    assert resp.status_code == 200

    code = _sender().get_code(email)
    second = await client.post(
        EMAIL_BIND_URL, json={"email": email, "code": code}, headers=_auth(token)
    )
    assert second.status_code == 409  # 已绑定，拒绝再次绑定


async def test_bind_same_email_other_user_conflict(client):
    """相同邮箱绑定到不同用户时冲突."""
    a = await _register_login(client, "bind_owner")
    await _bind_email(client, a["access_token"], "shared@example.com")

    b = await _register_login(client, "bind_other")
    r = await client.post(
        EMAIL_SEND_URL, json={"email": "shared@example.com"}, headers=_auth(b["access_token"])
    )
    assert r.status_code == 409  # 发送阶段即拦截他人已绑定邮箱
    r = await client.post(
        EMAIL_BIND_URL,
        json={"email": "shared@example.com", "code": "123456"},
        headers=_auth(b["access_token"]),
    )
    assert r.status_code in (401, 409)


async def test_bind_smtp_failure(client):
    """SMTP 发送失败：返回可诊断错误，不标记成功."""
    data = await _register_login(client, "smtp_fail")
    _sender().fail_send = True
    r = await client.post(
        EMAIL_SEND_URL, json={"email": "fail@example.com"}, headers=_auth(data["access_token"])
    )
    assert r.status_code == 502


# ---------------------------------------------------------------------------
# 密码找回
# ---------------------------------------------------------------------------
async def test_forgot_password_uniform_response(client):
    """不存在 / 未绑定 / 已绑定邮箱的找回申请返回统一响应（防枚举）."""
    r_nonexist = await client.post(FORGOT_URL, json={"email": "nobody@example.com"})

    await _register_login(client, "uni_user")
    r_unbound = await client.post(FORGOT_URL, json={"email": "unbound@example.com"})

    data = await _register_login(client, "uni_bound")
    email = "bound@example.com"
    await _bind_email(client, data["access_token"], email)
    r_bound = await client.post(FORGOT_URL, json={"email": email})

    assert r_nonexist.status_code == r_unbound.status_code == r_bound.status_code == 200
    assert (
        r_nonexist.json()["data"]
        == r_unbound.json()["data"]
        == r_bound.json()["data"]
    )


async def test_unverified_email_cannot_reset(client):
    """未绑定/未验证邮箱不能找回密码."""
    await _register_login(client, "unverified")
    r = await client.post(
        RESET_URL,
        json={"email": "unbound@example.com", "code": "123456", "new_password": "newpass123"},
    )
    assert r.status_code == 401


async def test_bind_and_reset_credentials_isolated(client):
    """绑定验证码与重置验证码不能混用."""
    data = await _register_login(client, "iso_user")
    token = data["access_token"]
    email = "iso@example.com"

    # 完成绑定（记录绑定验证码）
    await client.post(EMAIL_SEND_URL, json={"email": email}, headers=_auth(token))
    bind_code = _sender().get_code(email)
    assert bind_code is not None
    r = await client.post(
        EMAIL_BIND_URL, json={"email": email, "code": bind_code}, headers=_auth(token)
    )
    assert r.status_code == 200

    # 申请重置，获取重置验证码
    await client.post(FORGOT_URL, json={"email": email})
    reset_code = _sender().get_code(email)
    assert reset_code is not None

    # 用绑定验证码尝试重置 → 拒绝
    r = await client.post(
        RESET_URL,
        json={"email": email, "code": bind_code, "new_password": "newpass123"},
    )
    assert r.status_code == 401

    # 用重置验证码正确重置 → 成功
    r = await client.post(
        RESET_URL,
        json={"email": email, "code": reset_code, "new_password": "newpass123"},
    )
    assert r.status_code == 200


async def test_reset_password_flow(client):
    """正确重置密码后旧密码失效、新密码可登录."""
    data = await _register_login(client, "reset_user")
    email = "reset@example.com"
    await _bind_email(client, data["access_token"], email)

    await client.post(FORGOT_URL, json={"email": email})
    code = _sender().get_code(email)

    r = await client.post(
        RESET_URL,
        json={"email": email, "code": code, "new_password": "newpass123"},
    )
    assert r.status_code == 200

    old_login = await client.post(
        LOGIN_URL, json={"username": "reset_user", "password": "secret123"}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        LOGIN_URL, json={"username": "reset_user", "password": "newpass123"}
    )
    assert new_login.status_code == 200


async def test_reset_code_single_use(client):
    """重置验证码一次性使用，重复使用被拒绝."""
    data = await _register_login(client, "reuse_reset")
    email = "reuse-reset@example.com"
    await _bind_email(client, data["access_token"], email)

    await client.post(FORGOT_URL, json={"email": email})
    code = _sender().get_code(email)

    first = await client.post(
        RESET_URL, json={"email": email, "code": code, "new_password": "newpass123"}
    )
    assert first.status_code == 200

    second = await client.post(
        RESET_URL, json={"email": email, "code": code, "new_password": "other456"}
    )
    assert second.status_code == 401


async def test_reset_invalidates_old_session(client):
    """密码重置后旧 JWT 在后端失效."""
    data = await _register_login(client, "sess_user")
    old_token = data["access_token"]
    email = "sess@example.com"
    await _bind_email(client, old_token, email)

    await client.post(FORGOT_URL, json={"email": email})
    code = _sender().get_code(email)

    r = await client.post(
        RESET_URL, json={"email": email, "code": code, "new_password": "newpass123"}
    )
    assert r.status_code == 200

    # 旧 token 访问受保护接口 → 401（会话已被撤销）
    r = await client.get(PROFILE_URL, headers=_auth(old_token))
    assert r.status_code == 401


async def test_operations_do_not_modify_user_data(client, session_factory):
    """邮箱绑定与密码重置不修改 user_id、设备绑定及巡检记录."""
    data = await _register_login(client, "keep_user")
    user_id = data["user_id"]
    token = data["access_token"]
    email = "keep@example.com"

    async with session_factory() as db:
        device = Device(
            device_id="TLD_KEEP_001", device_name="keep", device_secret="secret", status=1
        )
        db.add(device)
        await db.flush()
        db.add(DeviceBinding(user_id=user_id, device_id=device.id, status=1))
        db.add(
            InspectionRecord(
                device_id="TLD_KEEP_001",
                data_id="data-keep-1",
                owner_user_id=user_id,
                schema_version="1.0",
                captured_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
            )
        )
        await db.commit()

    await _bind_email(client, token, email)
    await client.post(FORGOT_URL, json={"email": email})
    code = _sender().get_code(email)
    r = await client.post(
        RESET_URL, json={"email": email, "code": code, "new_password": "newpass123"}
    )
    assert r.status_code == 200

    async with session_factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        assert user.id == user_id  # user_id 未变

        binding_count = await db.scalar(
            select(func.count(DeviceBinding.id)).where(DeviceBinding.user_id == user_id)
        )
        assert binding_count == 1  # 设备绑定未变

        rec_count = await db.scalar(
            select(func.count(InspectionRecord.id)).where(
                InspectionRecord.owner_user_id == user_id
            )
        )
        assert rec_count == 1  # 巡检记录未变
