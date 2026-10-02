"""巡检/图片上传 HTTP 接口测试.

覆盖：正常图片 / 不存在 data_id / 跨用户 data_id / 非图片文件 / 超尺寸 / 重复图片，
以及列表 / 完整 JSON / 统计接口。模型调用统一 mock，不加载真实权重。
"""
import uuid

from app.core.config import settings
from app.services import inspection_service
from tests.helpers import make_device, valid_payload

DEVICE_ID = "TLD_SIM_001"
TOPIC = f"tld/device/{DEVICE_ID}/data"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def _register_and_login(client, username):
    await client.post(
        "/api/auth/register", json={"username": username, "password": "secret123"}
    )
    r = await client.post(
        "/api/auth/login", json={"username": username, "password": "secret123"}
    )
    data = r.json()["data"]
    return data["access_token"], data["user_id"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _seed_record(session_factory, user_id, data_id=None):
    data_id = data_id or uuid.uuid4().hex
    async with session_factory() as db:
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user_id)
        payload = valid_payload(data_id=data_id)
        await inspection_service.ingest_message(db, payload, TOPIC)
    return data_id


async def test_upload_normal_image(client, session_factory, monkeypatch, tmp_path):
    async def fake(*args, **kwargs):
        return {"available": False, "status": "model_unavailable", "reason": "down"}

    monkeypatch.setattr("app.services.model_client.submit_image", fake)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))

    token, user_id = await _register_and_login(client, "uploader")
    data_id = await _seed_record(session_factory, user_id)

    resp = await client.post(
        "/api/inspection/upload-image",
        data={"device_id": DEVICE_ID, "data_id": data_id},
        files={"image": ("a.png", PNG, "image/png")},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["upload_status"] == "completed"
    assert body["data"]["cloud_detection"]["status"] == "model_unavailable"


async def test_upload_nonexistent_data_id(client, session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    token, user_id = await _register_and_login(client, "ghostuploader")
    await _seed_record(session_factory, user_id)

    resp = await client.post(
        "/api/inspection/upload-image",
        data={"device_id": DEVICE_ID, "data_id": "no-such-id"},
        files={"image": ("a.png", PNG, "image/png")},
        headers=_auth(token),
    )
    assert resp.status_code == 404


async def test_upload_cross_user(client, session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    token_a, user_a = await _register_and_login(client, "owner_a")
    token_b, user_b = await _register_and_login(client, "owner_b")
    data_id = await _seed_record(session_factory, user_a)

    resp = await client.post(
        "/api/inspection/upload-image",
        data={"device_id": DEVICE_ID, "data_id": data_id},
        files={"image": ("a.png", PNG, "image/png")},
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


async def test_upload_non_image(client, session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    token, user_id = await _register_and_login(client, "badfile")
    data_id = await _seed_record(session_factory, user_id)

    resp = await client.post(
        "/api/inspection/upload-image",
        data={"device_id": DEVICE_ID, "data_id": data_id},
        files={"image": ("x.txt", b"hello world", "text/plain")},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_upload_oversize(client, session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "IMAGE_MAX_SIZE_MB", 0)  # 任何内容都超尺寸
    token, user_id = await _register_and_login(client, "bigfile")
    data_id = await _seed_record(session_factory, user_id)

    resp = await client.post(
        "/api/inspection/upload-image",
        data={"device_id": DEVICE_ID, "data_id": data_id},
        files={"image": ("a.png", PNG, "image/png")},
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_upload_duplicate_image(client, session_factory, monkeypatch, tmp_path):
    async def fake(*args, **kwargs):
        return {"available": False, "status": "model_unavailable", "reason": "down"}

    monkeypatch.setattr("app.services.model_client.submit_image", fake)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))

    token, user_id = await _register_and_login(client, "dupimg")
    data_id = await _seed_record(session_factory, user_id)

    r1 = await client.post(
        "/api/inspection/upload-image",
        data={"device_id": DEVICE_ID, "data_id": data_id},
        files={"image": ("a.png", PNG, "image/png")},
        headers=_auth(token),
    )
    r2 = await client.post(
        "/api/inspection/upload-image",
        data={"device_id": DEVICE_ID, "data_id": data_id},
        files={"image": ("a.png", PNG, "image/png")},
        headers=_auth(token),
    )
    assert r1.status_code == 200 and r2.status_code == 200
    # 每次上传生成独立 image_id，不冲突
    assert r1.json()["data"]["image_id"] != r2.json()["data"]["image_id"]


async def test_list_and_full_json(client, session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_ROOT", str(tmp_path))
    token, user_id = await _register_and_login(client, "query_user")
    data_id = await _seed_record(session_factory, user_id)

    listing = await client.get("/api/inspection/list", headers=_auth(token))
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] == 1

    full = await client.get(f"/api/inspection/{data_id}", headers=_auth(token))
    assert full.status_code == 200
    data = full.json()["data"]
    assert data["device_id"] == DEVICE_ID
    assert data["data_id"] == data_id
    assert data["location"]["latitude"] == 39.12345678
    assert data["detection"]["results"][0]["class"] == "Frogeye"

    stats = await client.get("/api/inspection/stats", headers=_auth(token))
    assert stats.status_code == 200
    assert stats.json()["data"]["total"] == 1
