"""Annotation evidence borrows only its exact source, without double counting."""
import base64

from sqlalchemy import select

from app.models.inspection import ImageRecord, InspectionRecord
from app.services import event_service, image_service, inspection_service
from tests.helpers import make_device, make_user, valid_payload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


async def test_annotation_results_match_exact_original_and_preserve_totals(session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.IMAGE_STORAGE_ROOT", str(tmp_path))
    calls = 0

    async def model(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {"status": "completed", "has_target": calls == 1,
                "results": [{"class": "Frogeye", "confidence": .96, "bbox": [1, 2, 3, 4]}] if calls == 1 else [],
                "annotated_image_base64": base64.b64encode(PNG).decode()}

    monkeypatch.setattr("app.services.model_client.submit_image", model)
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, owner_user_id=user.id)
        event = await event_service.create_event(db, user.id, "TLD_SIM_001", "证据测试", None)
        payload = valid_payload()
        payload["inspection_id"] = event["inspection_id"]
        await inspection_service.ingest_message(db, payload, "tld/device/TLD_SIM_001/data")
        first = await image_service.upload_image(db, user, "TLD_SIM_001", payload["data_id"], PNG, "image/png")
        second = await image_service.upload_image(db, user, "TLD_SIM_001", payload["data_id"], PNG, "image/png")
        record = await db.scalar(select(InspectionRecord).where(InspectionRecord.data_id == payload["data_id"]))
        unrelated = ImageRecord(image_id="unrelated_annotation", inspection_id=record.id,
                                image_type="annotated", storage_key="images/annotated/missing_ann.jpg")
        db.add(unrelated)
        await db.commit()

    # Fresh session: test the actual query and relationship loading path.
    async with session_factory() as db:
        detail = await event_service.get_event_detail(db, user.id, event["inspection_id"], include_series=False)
        rows = (await db.execute(select(ImageRecord).where(ImageRecord.inspection_id == record.id))).scalars().all()
        by_id = {image["image_id"]: image for image in detail["images"]}
        for source in [first, second]:
            annotation = next(row for row in rows if row.storage_key == f"images/annotated/{source['image_id']}_ann.jpg")
            assert by_id[annotation.image_id]["cloud_detection"] == by_id[source["image_id"]]["cloud_detection"]
            assert by_id[annotation.image_id]["cloud_detection"]["status"] == "completed"
        assert by_id["unrelated_annotation"]["cloud_detection"] is None
        assert detail["risk"]["target_count"] == 2  # One edge + one cloud, not annotation copies.
        assert detail["image_count"] == 5
