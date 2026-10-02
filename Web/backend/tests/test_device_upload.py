"""设备专用 HTTP 图片上传测试.

覆盖：设备认证（有效/无效/缺失）、幂等重复上传、跨设备越权、
图片先于 MQTT 记录到达（有界等待）、非法图片、超尺寸、模型不可用。
模型调用统一 mock，不加载真实权重、不发起真实网络请求。
"""
import asyncio
import uuid

from sqlalchemy import func, select

from app.core.config import settings
from app.models.inspection import ImageRecord
from app.services import inspection_service
from tests.helpers import make_device, make_user, valid_payload

DEVICE_ID = "TLD_SIM_001"
SECRET = "dev-secret"
TOPIC = f"tld/device/{DEVICE_ID}/data"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _device_headers(device_id=DEVICE_ID, secret=SECRET):
    return {"X-Device-ID": device_id, "X-Device-Secret": secret}


async def _seed_device_and_record(session_factory, device_id=DEVICE_ID, data_id=None):
    """创建已绑定设备 + 一条巡检记录，返回 data_id."""
    data_id = data_id or uuid.uuid4().hex
    async with session_factory() as db:
        user = await make_user(db, nickname=f"user_{uuid.uuid4().hex[:6]}")
        await make_device(db, device_id=device_id, owner_user_id=user.id)
        await inspection_service.ingest_message(db, valid_payload(data_id=data_id), TOPIC)
    return data_id


async def _upload(client, data_id, image_id=None, headers=None, image=PNG, inspection_id=None, timestamp=None):
    form = {"data_id": data_id}
    if image_id:
        form["image_id"] = image_id
    if inspection_id:
        form["inspection_id"] = inspection_id
    if timestamp:
        form["timestamp"] = timestamp
    return await client.post(
        "/api/inspection/device-upload",
        data=form,
        files={"image": ("a.png", image, "image/png")},
        headers=headers or _device_headers(),
    )


def _mock_unavailable(monkeypatch):
    async def fake(*args, **kwargs):
        return {"available": False, "status": "model_unavailable", "reason": "down"}

    monkeypatch.setattr("app.services.model_client.submit_image", fake)


async def test_device_upload_success(client, session_factory, monkeypatch, tmp_path):
    _mock_unavailable(monkeypatch)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    data_id = await _seed_device_and_record(session_factory)

    resp = await _upload(client, data_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["upload_status"] == "completed"
    assert body["data"]["already_uploaded"] is False
    assert body["data"]["cloud_detection"]["status"] == "model_unavailable"


async def test_device_upload_invalid_secret(client, session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    data_id = await _seed_device_and_record(session_factory)

    resp = await _upload(client, data_id, headers=_device_headers(secret="wrong-secret"))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "设备密钥不匹配"


async def test_device_upload_missing_auth(client, session_factory):
    data_id = await _seed_device_and_record(session_factory)

    resp = await client.post(
        "/api/inspection/device-upload",
        data={"data_id": data_id},
        files={"image": ("a.png", PNG, "image/png")},
    )
    assert resp.status_code == 401
    assert "X-Device-ID" in resp.json()["detail"]
    assert "X-Device-Secret" in resp.json()["detail"]


async def test_device_upload_idempotent(client, session_factory, monkeypatch, tmp_path):
    _mock_unavailable(monkeypatch)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    data_id = await _seed_device_and_record(session_factory)

    first = await _upload(client, data_id, image_id="img-fixed-1")
    assert first.status_code == 200
    assert first.json()["data"]["already_uploaded"] is False

    second = await _upload(client, data_id, image_id="img-fixed-1")
    assert second.status_code == 200
    assert second.json()["data"]["already_uploaded"] is True

    # 仅一条图片记录
    async with session_factory() as db:
        count = await db.scalar(
            select(func.count(ImageRecord.id)).where(ImageRecord.image_id == "img-fixed-1")
        )
        assert count == 1


async def test_device_upload_cross_device(client, session_factory, monkeypatch, tmp_path):
    _mock_unavailable(monkeypatch)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    # 记录属于设备 B（TLD_SIM_002）；同时注册设备 A（TLD_SIM_001）
    data_id = await _seed_device_and_record(session_factory, device_id="TLD_SIM_002")
    async with session_factory() as db:
        await make_device(db, device_id="TLD_SIM_001", owner_user_id=None)

    resp = await _upload(client, data_id, headers=_device_headers(device_id="TLD_SIM_001"))
    # 设备 A 无法关联到设备 B 的记录（视为记录不存在，不泄露归属信息）
    assert resp.status_code == 404


async def test_device_upload_invalid_image(client, session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    data_id = await _seed_device_and_record(session_factory)

    resp = await _upload(client, data_id, image=b"not-an-image")
    assert resp.status_code == 400


async def test_device_upload_oversize(client, session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "IMAGE_MAX_SIZE_MB", 0)
    data_id = await _seed_device_and_record(session_factory)

    resp = await _upload(client, data_id)
    assert resp.status_code == 400


async def test_device_upload_record_not_found(client, session_factory, monkeypatch, tmp_path):
    """记录尚未入库且有界等待超时 → 返回可重试错误."""
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "IMAGE_PENDING_WAIT_SECONDS", 0.1)
    monkeypatch.setattr(settings, "IMAGE_PENDING_POLL_INTERVAL", 0.02)
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)

    resp = await _upload(client, "no-such-data-id")
    assert resp.status_code == 404


async def test_device_upload_image_before_record(client, session_factory, monkeypatch, tmp_path):
    """HTTP 图片先到、MQTT 记录后到：有界等待后成功关联."""
    _mock_unavailable(monkeypatch)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "IMAGE_PENDING_WAIT_SECONDS", 3.0)
    monkeypatch.setattr(settings, "IMAGE_PENDING_POLL_INTERVAL", 0.05)

    async with session_factory() as db:
        user = await make_user(db, nickname="later_owner")
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)

    data_id = uuid.uuid4().hex

    async def insert_later():
        await asyncio.sleep(0.3)
        async with session_factory() as db2:
            await inspection_service.ingest_message(db2, valid_payload(data_id=data_id), TOPIC)

    task = asyncio.create_task(insert_later())
    resp = await _upload(client, data_id)
    await task

    assert resp.status_code == 200
    assert resp.json()["data"]["upload_status"] == "completed"


async def test_device_upload_validates_event_and_timestamp(client, session_factory, monkeypatch, tmp_path):
    _mock_unavailable(monkeypatch)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    inspection_id = "INS_IMAGE_BINDING_001"
    timestamp = "2026-09-22T05:30:22.000Z"
    async with session_factory() as db:
        user = await make_user(db, nickname="image_binding_owner")
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        control = {"type": "inspection_control", "command": "START", "inspection_id": inspection_id, "device_id": DEVICE_ID, "timestamp": timestamp}
        await inspection_service.ingest_control_message(db, control, f"tld/device/{DEVICE_ID}/control")
        payload = valid_payload(data_id="image-binding-data")
        payload["inspection_id"] = inspection_id
        await inspection_service.ingest_message(db, payload, TOPIC)

    ok = await _upload(client, "image-binding-data", image_id="img-binding-ok", inspection_id=inspection_id, timestamp=timestamp)
    assert ok.status_code == 200
    wrong_event = await _upload(client, "image-binding-data", image_id="img-binding-bad-event", inspection_id="INS_WRONG", timestamp=timestamp)
    assert wrong_event.status_code == 409
    wrong_time = await _upload(client, "image-binding-data", image_id="img-binding-bad-time", inspection_id=inspection_id, timestamp="2026-09-22T06:30:22Z")
    assert wrong_time.status_code == 409
