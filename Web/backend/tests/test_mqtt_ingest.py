"""MQTT ingest 管线测试.

覆盖：合法 V1.0 / 非法 schema / topic 与 device_id 不一致 / 重复 data_id /
未知设备 / 未绑定设备 / 合法模拟设备 / QoS 重复消息。
"""
import copy

from sqlalchemy import select

from app.models.inspection import InspectionEvent, InspectionRecord
from app.services import inspection_service
from app.services.inspection_service import (
    INGEST_DUPLICATE,
    INGEST_INSERTED,
    INGEST_INVALID_SCHEMA,
    INGEST_DEVICE_MISMATCH,
    INGEST_UNKNOWN_DEVICE,
    INGEST_UNBOUND_DEVICE,
    INGEST_INVALID_TOPIC,
    CONTROL_COMPLETED,
    CONTROL_DUPLICATE,
    CONTROL_STARTED,
)
from tests.helpers import make_device, make_user, valid_payload

DEVICE_ID = "TLD_SIM_001"
TOPIC = f"tld/device/{DEVICE_ID}/data"


async def test_valid_message_inserted(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)

        result = await inspection_service.ingest_message(db, valid_payload(), TOPIC)
        assert result.status == INGEST_INSERTED
        assert result.device_id == DEVICE_ID

        record = await db.scalar(
            select(InspectionRecord).where(InspectionRecord.device_id == DEVICE_ID)
        )
        assert record is not None
        assert record.owner_user_id == user.id


async def test_invalid_topic(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        result = await inspection_service.ingest_message(
            db, valid_payload(), "wrong/topic/structure"
        )
        assert result.status == INGEST_INVALID_TOPIC


async def test_invalid_schema(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        payload = valid_payload()
        del payload["location"]["latitude"]  # 缺失必填字段
        result = await inspection_service.ingest_message(db, payload, TOPIC)
        assert result.status == INGEST_INVALID_SCHEMA


async def test_device_mismatch(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        payload = valid_payload(device_id="TLD_SIM_999")  # 与 topic 不一致
        result = await inspection_service.ingest_message(db, payload, TOPIC)
        assert result.status == INGEST_DEVICE_MISMATCH


async def test_duplicate_data_id(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        payload = valid_payload(data_id="fixed-data-id")

        first = await inspection_service.ingest_message(db, payload, TOPIC)
        assert first.status == INGEST_INSERTED

        # QoS1 重投：同一 data_id 不产生重复业务数据
        second = await inspection_service.ingest_message(db, copy.deepcopy(payload), TOPIC)
        assert second.status == INGEST_DUPLICATE

        count = await db.scalar(
            select(InspectionRecord.id).where(InspectionRecord.data_id == "fixed-data-id")
        )
        rows = (await db.execute(
            select(InspectionRecord).where(InspectionRecord.data_id == "fixed-data-id")
        )).scalars().all()
        assert len(rows) == 1


async def test_unknown_device(session_factory):
    async with session_factory() as db:
        # 设备不存在
        result = await inspection_service.ingest_message(db, valid_payload(), TOPIC)
        assert result.status == INGEST_UNKNOWN_DEVICE


async def test_unbound_device(session_factory):
    async with session_factory() as db:
        # 设备存在但未绑定
        await make_device(db, device_id=DEVICE_ID, owner_user_id=None)
        result = await inspection_service.ingest_message(db, valid_payload(), TOPIC)
        assert result.status == INGEST_UNBOUND_DEVICE


async def test_owner_determined_from_binding(session_factory):
    """owner_user_id 由绑定关系确定，而非设备上报."""
    async with session_factory() as db:
        user = await make_user(db, nickname="owner")
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)

        payload = valid_payload()
        # 尝试在 payload 中伪造 owner（协议不含该字段，但若被塞入应被忽略）
        payload["owner_user_id"] = 99999
        result = await inspection_service.ingest_message(db, payload, TOPIC)
        assert result.status == INGEST_INSERTED

        record = await db.scalar(
            select(InspectionRecord).where(InspectionRecord.data_id == payload["data_id"])
        )
        assert record.owner_user_id == user.id


async def test_device_control_lifecycle_and_data_association(session_factory):
    inspection_id = "INS_TEST_CONTROL_001"
    control_topic = f"tld/device/{DEVICE_ID}/control"
    async with session_factory() as db:
        user = await make_user(db, nickname="control_owner")
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        start_payload = {
            "type": "inspection_control", "command": "START",
            "inspection_id": inspection_id, "device_id": DEVICE_ID,
            "timestamp": "2026-09-24T08:00:00Z",
        }
        started = await inspection_service.ingest_control_message(db, start_payload, control_topic)
        assert started.status == CONTROL_STARTED
        duplicate = await inspection_service.ingest_control_message(db, start_payload, control_topic)
        assert duplicate.status == CONTROL_DUPLICATE

        payload = valid_payload(data_id="control-data-1")
        payload["inspection_id"] = inspection_id
        assert (await inspection_service.ingest_message(db, payload, TOPIC)).status == INGEST_INSERTED
        event = await db.scalar(select(InspectionEvent).where(InspectionEvent.inspection_id == inspection_id))
        record = await db.scalar(select(InspectionRecord).where(InspectionRecord.data_id == "control-data-1"))
        assert event.status == "RUNNING"
        assert record.event_id == event.id

        ended = await inspection_service.ingest_control_message(
            db,
            {**start_payload, "command": "END", "timestamp": "2026-09-24T08:10:00Z"},
            control_topic,
        )
        assert ended.status == CONTROL_COMPLETED
        await db.refresh(event)
        assert event.status == "COMPLETED"
