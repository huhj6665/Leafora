"""云端推理（cloud_detection）测试，使用 mock model（不加载真实 RT-DETR-L 权重）."""
import base64

from app.services import image_service, inspection_service
from tests.helpers import make_device, make_user, valid_payload

DEVICE_ID = "TLD_SIM_001"
TOPIC = f"tld/device/{DEVICE_ID}/data"

# 最小合法 PNG 魔数（仅用于通过类型/大小校验，测试不真实解码图片）
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _completed_fake(**overrides):
    async def fake(image_bytes, content_type, device_id, data_id, timeout=None):
        result = {
            "available": True,
            "status": "completed",
            "has_target": True,
            "results": [
                {"class": "Frogeye", "confidence": 0.96, "bbox": [118, 82, 252, 301]}
            ],
            "model_name": "RT-DETR-L",
            "model_version": "v1.0",
            "weights_identifier": "sha256:abc123",
            "annotated_image_base64": base64.b64encode(PNG).decode(),
        }
        result.update(overrides)
        return result

    return fake


async def _seed_inspection(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        payload = valid_payload()
        await inspection_service.ingest_message(db, payload, TOPIC)
        return user, payload["data_id"]


async def test_upload_completed(monkeypatch, session_factory, tmp_path):
    monkeypatch.setattr("app.services.model_client.submit_image", _completed_fake())
    monkeypatch.setattr("app.core.config.settings.IMAGE_STORAGE_ROOT", str(tmp_path))

    async with session_factory() as db:
        user, data_id = await _seed_inspection(session_factory)

        result = await image_service.upload_image(
            db, user, DEVICE_ID, data_id, PNG, "image/png"
        )
        assert result["cloud_detection"]["status"] == "completed"
        assert result["cloud_detection"]["model_name"] == "RT-DETR-L"
        assert result["cloud_detection"]["has_target"] is True
        assert len(result["cloud_detection"]["results"]) == 1


async def test_upload_model_unavailable(monkeypatch, session_factory, tmp_path):
    async def fake(*args, **kwargs):
        return {"available": False, "status": "model_unavailable", "reason": "no_weights"}

    monkeypatch.setattr("app.services.model_client.submit_image", fake)
    monkeypatch.setattr("app.core.config.settings.IMAGE_STORAGE_ROOT", str(tmp_path))

    async with session_factory() as db:
        user, data_id = await _seed_inspection(session_factory)
        # 模型不可用不应影响图片上传成功
        result = await image_service.upload_image(
            db, user, DEVICE_ID, data_id, PNG, "image/png"
        )
        assert result["upload_status"] == "completed"
        assert result["cloud_detection"]["status"] == "model_unavailable"


async def test_upload_failed(monkeypatch, session_factory, tmp_path):
    async def fake(*args, **kwargs):
        return {"available": False, "status": "failed", "reason": "inference error"}

    monkeypatch.setattr("app.services.model_client.submit_image", fake)
    monkeypatch.setattr("app.core.config.settings.IMAGE_STORAGE_ROOT", str(tmp_path))

    async with session_factory() as db:
        user, data_id = await _seed_inspection(session_factory)
        result = await image_service.upload_image(
            db, user, DEVICE_ID, data_id, PNG, "image/png"
        )
        assert result["cloud_detection"]["status"] == "failed"


async def test_multiple_detections(monkeypatch, session_factory, tmp_path):
    async def fake(*args, **kwargs):
        return {
            "available": True,
            "status": "completed",
            "has_target": True,
            "results": [
                {"class": "Frogeye", "confidence": 0.9, "bbox": [1, 2, 3, 4]},
                {"class": "Mosaic", "confidence": 0.8, "bbox": [5, 6, 7, 8]},
            ],
            "model_name": "RT-DETR-L",
            "model_version": "v1.0",
            "weights_identifier": "sha256:abc",
        }

    monkeypatch.setattr("app.services.model_client.submit_image", fake)
    monkeypatch.setattr("app.core.config.settings.IMAGE_STORAGE_ROOT", str(tmp_path))

    async with session_factory() as db:
        user, data_id = await _seed_inspection(session_factory)
        result = await image_service.upload_image(
            db, user, DEVICE_ID, data_id, PNG, "image/png"
        )
        assert len(result["cloud_detection"]["results"]) == 2


async def test_no_detection(monkeypatch, session_factory, tmp_path):
    async def fake(*args, **kwargs):
        return {
            "available": True,
            "status": "completed",
            "has_target": False,
            "results": [],
            "model_name": "RT-DETR-L",
            "model_version": "v1.0",
            "weights_identifier": "sha256:abc",
        }

    monkeypatch.setattr("app.services.model_client.submit_image", fake)
    monkeypatch.setattr("app.core.config.settings.IMAGE_STORAGE_ROOT", str(tmp_path))

    async with session_factory() as db:
        user, data_id = await _seed_inspection(session_factory)
        result = await image_service.upload_image(
            db, user, DEVICE_ID, data_id, PNG, "image/png"
        )
        assert result["cloud_detection"]["has_target"] is False
        assert result["cloud_detection"]["results"] == []


async def test_reprocess(monkeypatch, session_factory, tmp_path):
    monkeypatch.setattr("app.core.config.settings.IMAGE_STORAGE_ROOT", str(tmp_path))

    async def unavailable(*args, **kwargs):
        return {"available": False, "status": "model_unavailable", "reason": "down"}

    async with session_factory() as db:
        user, data_id = await _seed_inspection(session_factory)
        monkeypatch.setattr("app.services.model_client.submit_image", unavailable)
        first = await image_service.upload_image(db, user, DEVICE_ID, data_id, PNG, "image/png")
        assert first["cloud_detection"]["status"] == "model_unavailable"

        # 模型就绪后重试 → completed
        monkeypatch.setattr("app.services.model_client.submit_image", _completed_fake())
        second = await image_service.reprocess_image(db, user.id, data_id)
        assert second["cloud_detection"]["status"] == "completed"
