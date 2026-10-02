"""用户资料与当前账号密码接口测试。"""

from app.services.email import get_email_sender
from app.services.email.mock import MockEmailSender
from app.services.sms import get_sms_provider
from app.services.sms.mock import MockSMSProvider


async def test_profile_requires_auth(client):
    """未携带令牌访问受保护接口：返回 401."""
    resp = await client.get("/api/user/profile")
    assert resp.status_code == 401


async def test_profile_with_token(client):
    """携带有效令牌访问：返回当前用户信息."""
    await client.post(
        "/api/auth/register", json={"username": "eve", "password": "secret123"}
    )
    login = await client.post(
        "/api/auth/login", json={"username": "eve", "password": "secret123"}
    )
    token = login.json()["data"]["access_token"]

    resp = await client.get(
        "/api/user/profile", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["user_id"] > 0
    assert data["nickname"] == "eve"


async def test_update_profile_only_allows_nickname_and_avatar(client):
    await client.post(
        "/api/auth/register", json={"username": "profile_user", "password": "secret123"}
    )
    login = await client.post(
        "/api/auth/login", json={"username": "profile_user", "password": "secret123"}
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    updated = await client.patch(
        "/api/user/profile",
        json={"nickname": "烟田巡检员", "avatar": "preset:leaf"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["nickname"] == "烟田巡检员"
    assert data["avatar"] == "preset:leaf"

    forbidden = await client.patch(
        "/api/user/profile",
        json={"nickname": "其他昵称", "user_id": 999, "status": 0},
        headers=headers,
    )
    assert forbidden.status_code == 422

    unchanged = await client.get("/api/user/profile", headers=headers)
    assert unchanged.json()["data"]["user_id"] == data["user_id"]
    assert unchanged.json()["data"]["status"] == 1


async def test_update_profile_validates_fields(client):
    await client.post(
        "/api/auth/register", json={"username": "profile_valid", "password": "secret123"}
    )
    login = await client.post(
        "/api/auth/login", json={"username": "profile_valid", "password": "secret123"}
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    assert (
        await client.patch("/api/user/profile", json={}, headers=headers)
    ).status_code == 400
    assert (
        await client.patch(
            "/api/user/profile", json={"nickname": "a"}, headers=headers
        )
    ).status_code == 422
    assert (
        await client.patch(
            "/api/user/profile",
            json={"avatar": "https://invalid.example/avatar.png"},
            headers=headers,
        )
    ).status_code == 422


async def test_current_phone_password_flow(client):
    phone = "13800138055"
    sms = get_sms_provider()
    assert isinstance(sms, MockSMSProvider)
    await client.post("/api/auth/send-phone-code", json={"phone": phone})
    login = await client.post(
        "/api/auth/login-phone", json={"phone": phone, "code": sms.get_code(phone)}
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sent = await client.post(
        "/api/user/security/phone-password/send-code", json={}, headers=headers
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["data"]["phone"] == "138****8055"
    code = sms.get_code(phone)

    saved = await client.post(
        "/api/user/security/phone-password",
        json={"code": code, "new_password": "newpass123"},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    password_login = await client.post(
        "/api/auth/login-phone-password",
        json={"phone": phone, "password": "newpass123"},
    )
    assert password_login.status_code == 200


async def test_email_reset_updates_formal_phone_password(client):
    phone = "13800138066"
    email = "phone-recovery@example.com"
    sms = get_sms_provider()
    assert isinstance(sms, MockSMSProvider)
    await client.post("/api/auth/send-phone-code", json={"phone": phone})
    login = await client.post(
        "/api/auth/login-phone", json={"phone": phone, "code": sms.get_code(phone)}
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/user/email/send-code", json={"email": email}, headers=headers)
    sender = get_email_sender()
    assert isinstance(sender, MockEmailSender)
    await client.post(
        "/api/user/email/bind",
        json={"email": email, "code": sender.get_code(email)},
        headers=headers,
    )
    await client.post("/api/auth/forgot-password", json={"email": email})
    reset = await client.post(
        "/api/auth/reset-password",
        json={
            "email": email,
            "code": sender.get_code(email),
            "new_password": "mailpass123",
        },
    )
    assert reset.status_code == 200, reset.text
    password_login = await client.post(
        "/api/auth/login-phone-password",
        json={"phone": phone, "password": "mailpass123"},
    )
    assert password_login.status_code == 200
