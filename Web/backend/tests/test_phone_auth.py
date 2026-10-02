"""手机号验证码登录 / 绑定 相关测试（使用 MockSMSProvider）."""
import pytest

from app.services.jwt_service import create_access_token
from app.services.sms import get_sms_provider
from app.services.sms.mock import MockSMSProvider

SEND_URL = "/api/auth/send-phone-code"
PHONE_LOGIN_URL = "/api/auth/login-phone"
REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/login"
PROFILE_URL = "/api/user/profile"
BIND_SEND_URL = "/api/user/phone/send-code"
BIND_URL = "/api/user/phone/bind"

PHONE = "13800001111"


async def _send_code(client, phone: str = PHONE):
    """发送验证码并返回 mock 生成的验证码."""
    resp = await client.post(SEND_URL, json={"phone": phone})
    assert resp.status_code == 200, resp.text
    provider = get_sms_provider()
    assert isinstance(provider, MockSMSProvider)
    return provider.get_code(phone)


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_send_code_invalid_phone(client):
    """手机号格式错误：返回 400."""
    resp = await client.post(SEND_URL, json={"phone": "12345"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 400


async def test_send_code_mock_success(client):
    """短信发送 mock 成功：返回脱敏手机号，不返回验证码."""
    resp = await client.post(SEND_URL, json={"phone": PHONE})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["phone"] == "138****1111"
    assert "code" not in data  # 不泄露验证码


async def test_send_code_mock_failure(client):
    """短信发送 mock 失败：返回 502."""
    provider = get_sms_provider()
    assert isinstance(provider, MockSMSProvider)
    provider.fail_send = True
    resp = await client.post(SEND_URL, json={"phone": PHONE})
    # send 失败被转换为业务错误（502），不会抛出 500 堆栈
    assert resp.status_code == 502


async def test_login_phone_wrong_code(client):
    """错误验证码：返回 401."""
    await _send_code(client)
    resp = await client.post(
        PHONE_LOGIN_URL, json={"phone": PHONE, "code": "000000"}
    )
    assert resp.status_code == 401


async def test_login_phone_success_creates_user(client):
    """正确验证码登录成功，新手机号自动创建用户."""
    code = await _send_code(client)
    resp = await client.post(
        PHONE_LOGIN_URL, json={"phone": PHONE, "code": code}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"]
    assert data["user_id"] > 0


async def test_login_phone_existing_user_same_id(client):
    """同一手机号再次登录，返回原用户（不新建 User）."""
    code = await _send_code(client)
    first = await client.post(PHONE_LOGIN_URL, json={"phone": PHONE, "code": code})
    first_id = first.json()["data"]["user_id"]

    code2 = await _send_code(client)
    second = await client.post(PHONE_LOGIN_URL, json={"phone": PHONE, "code": code2})
    assert second.status_code == 200
    assert second.json()["data"]["user_id"] == first_id


async def test_login_phone_code_single_use(client):
    """验证码一次性：同一验证码不能重复换取 JWT."""
    code = await _send_code(client)
    first = await client.post(PHONE_LOGIN_URL, json={"phone": PHONE, "code": code})
    assert first.status_code == 200
    # 复用同一验证码
    second = await client.post(PHONE_LOGIN_URL, json={"phone": PHONE, "code": code})
    assert second.status_code == 401


async def test_bind_phone_rejected_for_other_user(client):
    """手机号已被其他账号绑定：拒绝绑定（409）."""
    # 用户 A 注册并绑定手机号
    await client.post(REGISTER_URL, json={"username": "alice", "password": "secret123"})
    login_a = await client.post(LOGIN_URL, json={"username": "alice", "password": "secret123"})
    token_a = login_a.json()["data"]["access_token"]

    send_a = await client.post(BIND_SEND_URL, json={"phone": PHONE}, headers=_auth_header(token_a))
    assert send_a.status_code == 200
    code_a = get_sms_provider().get_code(PHONE)
    bind_a = await client.post(BIND_URL, json={"phone": PHONE, "code": code_a}, headers=_auth_header(token_a))
    assert bind_a.status_code == 200

    # 用户 B 尝试绑定同一手机号
    await client.post(REGISTER_URL, json={"username": "bob", "password": "secret123"})
    login_b = await client.post(LOGIN_URL, json={"username": "bob", "password": "secret123"})
    token_b = login_b.json()["data"]["access_token"]

    send_b = await client.post(BIND_SEND_URL, json={"phone": PHONE}, headers=_auth_header(token_b))
    assert send_b.status_code == 200
    code_b = get_sms_provider().get_code(PHONE)
    bind_b = await client.post(BIND_URL, json={"phone": PHONE, "code": code_b}, headers=_auth_header(token_b))
    assert bind_b.status_code == 409


async def test_expired_token_rejected(client):
    """JWT 过期：访问受保护接口返回 401."""
    await client.post(REGISTER_URL, json={"username": "frank", "password": "secret123"})
    login = await client.post(LOGIN_URL, json={"username": "frank", "password": "secret123"})
    user_id = login.json()["data"]["user_id"]

    expired = create_access_token(user_id, expires_minutes=-1)
    resp = await client.get(PROFILE_URL, headers=_auth_header(expired))
    assert resp.status_code == 401
