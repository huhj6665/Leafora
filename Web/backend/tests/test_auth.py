"""认证接口测试：注册 / 登录 / 错误密码."""
import pytest

REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/login"


async def test_register_success(client):
    """注册成功：返回 user_id 与 nickname."""
    resp = await client.post(
        REGISTER_URL, json={"username": "alice", "password": "secret123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["nickname"] == "alice"
    assert body["data"]["user_id"] > 0


async def test_register_duplicate_username(client):
    """重复用户名注册：返回 409 冲突."""
    await client.post(
        REGISTER_URL, json={"username": "bob", "password": "secret123"}
    )
    resp = await client.post(
        REGISTER_URL, json={"username": "bob", "password": "secret123"}
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == 409


async def test_login_success(client):
    """登录成功：返回 access_token."""
    await client.post(
        REGISTER_URL, json={"username": "carol", "password": "secret123"}
    )
    resp = await client.post(
        LOGIN_URL, json={"username": "carol", "password": "secret123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user_id"] > 0


async def test_login_wrong_password(client):
    """错误密码：返回 401."""
    await client.post(
        REGISTER_URL, json={"username": "dave", "password": "secret123"}
    )
    resp = await client.post(
        LOGIN_URL, json={"username": "dave", "password": "wrongpass"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == 401


async def test_login_nonexistent_user(client):
    """不存在的用户：返回 401."""
    resp = await client.post(
        LOGIN_URL, json={"username": "ghost", "password": "secret123"}
    )
    assert resp.status_code == 401
