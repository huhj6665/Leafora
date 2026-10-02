"""设备绑定接口测试：绑定成功 / 幂等自绑定 / 他人拒绝 / 列表隔离 / 设备不存在."""
from sqlalchemy import func, select

from app.models.device import Device, DeviceBinding
from tests.helpers import make_device

DEVICE_ID = "TLD_SIM_001"


async def _register_and_login(client, username):
    await client.post(
        "/api/auth/register", json={"username": username, "password": "secret123"}
    )
    r = await client.post(
        "/api/auth/login", json={"username": username, "password": "secret123"}
    )
    return r.json()["data"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _binding_count(session_factory, device_id):
    async with session_factory() as db:
        device = await db.scalar(select(Device).where(Device.device_id == device_id))
        return await db.scalar(
            select(func.count(DeviceBinding.id)).where(
                DeviceBinding.device_id == device.id,
                DeviceBinding.status == 1,
            )
        )


async def _active_binding_owner(session_factory, device_id):
    async with session_factory() as db:
        device = await db.scalar(select(Device).where(Device.device_id == device_id))
        binding = await db.scalar(
            select(DeviceBinding).where(
                DeviceBinding.device_id == device.id,
                DeviceBinding.status == 1,
            )
        )
        return binding.user_id if binding else None


async def test_bind_success_and_list(client, session_factory):
    async with session_factory() as db:
        await make_device(db, device_id=DEVICE_ID, owner_user_id=None)
    token_data = await _register_and_login(client, "binder_a")
    token = token_data["access_token"]

    resp = await client.post(
        "/api/device/bind", json={"device_id": DEVICE_ID}, headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["bound"] is True
    assert body["data"]["already_bound"] is False

    listing = await client.get("/api/device/list", headers=_auth(token))
    assert listing.status_code == 200
    ids = [d["device_id"] for d in listing.json()["data"]]
    assert DEVICE_ID in ids


async def test_bind_idempotent_self(client, session_factory):
    async with session_factory() as db:
        await make_device(db, device_id=DEVICE_ID, owner_user_id=None)
    token_data = await _register_and_login(client, "binder_b")
    token = token_data["access_token"]

    first = await client.post(
        "/api/device/bind", json={"device_id": DEVICE_ID}, headers=_auth(token)
    )
    assert first.json()["data"]["already_bound"] is False

    second = await client.post(
        "/api/device/bind", json={"device_id": DEVICE_ID}, headers=_auth(token)
    )
    assert second.status_code == 200
    assert second.json()["data"]["already_bound"] is True

    # 仅存在一条活跃绑定记录
    assert await _binding_count(session_factory, DEVICE_ID) == 1


async def test_bind_other_user_refused(client, session_factory):
    async with session_factory() as db:
        await make_device(db, device_id=DEVICE_ID, owner_user_id=None)

    owner = await _register_and_login(client, "owner_x")
    other = await _register_and_login(client, "owner_y")

    ok_resp = await client.post(
        "/api/device/bind", json={"device_id": DEVICE_ID}, headers=_auth(owner["access_token"])
    )
    assert ok_resp.status_code == 200

    refused = await client.post(
        "/api/device/bind", json={"device_id": DEVICE_ID}, headers=_auth(other["access_token"])
    )
    assert refused.status_code == 409
    assert "其他用户" in refused.json()["message"]

    # 归属仍为 owner_x，未被覆盖
    assert await _active_binding_owner(session_factory, DEVICE_ID) == owner["user_id"]


async def test_list_isolated_between_users(client, session_factory):
    async with session_factory() as db:
        await make_device(db, device_id=DEVICE_ID, owner_user_id=None)

    owner = await _register_and_login(client, "iso_owner")
    other = await _register_and_login(client, "iso_other")

    await client.post(
        "/api/device/bind", json={"device_id": DEVICE_ID}, headers=_auth(owner["access_token"])
    )

    other_list = await client.get("/api/device/list", headers=_auth(other["access_token"]))
    assert other_list.json()["data"] == []


async def test_bind_nonexistent_device(client, session_factory):
    token_data = await _register_and_login(client, "no_device")
    resp = await client.post(
        "/api/device/bind", json={"device_id": "TLD_UNKNOWN"}, headers=_auth(token_data["access_token"])
    )
    assert resp.status_code == 404
