"""巡检数据业务服务：MQTT 数据入库（ingest）与查询.

ingest 管线（消费者核心）：
    Topic 校验 → JSON Schema 校验 → device_id 一致性 → 设备身份校验
    → 绑定关系校验（确定 owner_user_id）→ data_id 幂等校验 → 结构化写入。

幂等保障：``(device_id, data_id)`` 唯一约束 + 先查后插，QoS1 重投不产生重复业务数据。
owner_user_id 绝不信任设备上报，由后端根据绑定关系确定。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.device import Device, DeviceBinding
from app.models.inspection import (
    CloudDetection,
    DetectionRecord,
    DetectionResult,
    DeviceStatusRecord,
    EnvironmentRecord,
    ImageRecord,
    InspectionEvent,
    InspectionRecord,
    LocationRecord,
)
from app.models.protocol import DeviceControlRequest
from app.models.task import DeviceLatestData, TaskCommand
from app.schemas.mqtt import DeviceAckMessage, DeviceStatusMessage, InspectionControlMessage, MqttMessageV1
from app.services import end_confirmation, mqtt_publisher

# Topic：tld/device/{device_id}/data
_TOPIC_RE = re.compile(r"^[^/]+/device/([^/]+)/data$")
_CONTROL_TOPIC_RE = re.compile(r"^[^/]+/device/([^/]+)/control$")
_STATUS_TOPIC_RE = re.compile(r"^[^/]+/device/([^/]+)/status$")
_ACK_TOPIC_RE = re.compile(r"^[^/]+/device/([^/]+)/ack$")


# ---- 入库结果状态 ----
INGEST_INSERTED = "inserted"
INGEST_DUPLICATE = "duplicate"
INGEST_INVALID_TOPIC = "invalid_topic"
INGEST_INVALID_SCHEMA = "invalid_schema"
INGEST_DEVICE_MISMATCH = "device_mismatch"
INGEST_UNKNOWN_DEVICE = "unknown_device"
INGEST_UNBOUND_DEVICE = "unbound_device"
CONTROL_STARTED = "control_started"
CONTROL_COMPLETED = "control_completed"
CONTROL_DUPLICATE = "control_duplicate"
CONTROL_NOT_FOUND = "control_not_found"
CONTROL_INVALID_TRANSITION = "control_invalid_transition"


@dataclass
class IngestResult:
    """一次 ingest 的结果."""

    status: str
    device_id: Optional[str] = None
    data_id: Optional[str] = None
    reason: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == INGEST_INSERTED


def parse_topic(topic: str) -> Optional[str]:
    """从 Topic 中解析 device_id，非法返回 None."""
    m = _TOPIC_RE.match(topic or "")
    return m.group(1) if m else None


def parse_control_topic(topic: str) -> Optional[str]:
    m = _CONTROL_TOPIC_RE.match(topic or "")
    return m.group(1) if m else None


async def ingest_control_message(
    session: AsyncSession, payload: Any, topic: str
) -> IngestResult:
    """Handle START/END and persist an idempotent CONTROL_ACK."""
    topic_device_id = parse_control_topic(topic)
    if topic_device_id is None:
        return IngestResult(status=INGEST_INVALID_TOPIC, reason=f"非法 control topic: {topic}")
    try:
        msg = InspectionControlMessage.model_validate(payload)
    except ValidationError as exc:
        return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=topic_device_id, reason=str(exc.errors())[:200])
    if msg.device_id != topic_device_id:
        return IngestResult(status=INGEST_DEVICE_MISMATCH, device_id=topic_device_id, data_id=msg.inspection_id)
    device, owner_user_id = await _resolve_owner(session, msg.device_id)
    if device is None:
        return IngestResult(status=INGEST_UNKNOWN_DEVICE, device_id=msg.device_id, data_id=msg.inspection_id)
    if owner_user_id is None:
        return IngestResult(status=INGEST_UNBOUND_DEVICE, device_id=msg.device_id, data_id=msg.inspection_id)
    request_id = msg.request_id or f"LEGACY_{msg.command}_{msg.inspection_id}"
    prior = await session.scalar(select(DeviceControlRequest).where(
        DeviceControlRequest.device_id == msg.device_id,
        DeviceControlRequest.request_id == request_id,
    ))
    if prior is not None:
        await mqtt_publisher.publish_downlink(msg.device_id, prior.ack_payload)
        return IngestResult(status=CONTROL_DUPLICATE, device_id=msg.device_id, data_id=msg.inspection_id)

    event = await session.scalar(select(InspectionEvent).where(
        InspectionEvent.inspection_id == msg.inspection_id
    ))
    if event is not None and event.client_request_id is not None:
        return IngestResult(status=CONTROL_INVALID_TRANSITION, device_id=msg.device_id,
                            data_id=msg.inspection_id, reason="云端 V2 任务不可由旧 control 改变生命周期")
    event_time = _parse_dt(msg.timestamp) if msg.timestamp else datetime.now(timezone.utc)
    result_status = CONTROL_STARTED if msg.command == "START" else CONTROL_COMPLETED
    if msg.command == "START":
        if event is not None:
            if event.device_id != msg.device_id or event.owner_user_id != owner_user_id:
                return IngestResult(status=INGEST_DEVICE_MISMATCH, device_id=msg.device_id, data_id=msg.inspection_id, reason="inspection_id 已属于其他设备或用户")
            if event.status == "RUNNING":
                result_status = CONTROL_DUPLICATE
            elif event.status != "CREATED":
                return IngestResult(status=CONTROL_INVALID_TRANSITION, device_id=msg.device_id, data_id=msg.inspection_id, reason=f"当前状态 {event.status}")
            else:
                event.status = "RUNNING"
                event.started_at = event.started_at or event_time
        else:
            event = InspectionEvent(
                inspection_id=msg.inspection_id,
                device_id=msg.device_id,
                owner_user_id=owner_user_id,
                name=(msg.name or f"{msg.device_id} 虚拟巡检").strip(),
                status="RUNNING",
                started_at=event_time,
                sync_status="SYNCING",
            )
            session.add(event)
        device.operating_status = "RUNNING"
        device.communication_status = "ONLINE"
        device.last_seen_at = datetime.now(timezone.utc)
    else:
        if event is None or event.device_id != msg.device_id or event.owner_user_id != owner_user_id:
            return IngestResult(status=CONTROL_NOT_FOUND, device_id=msg.device_id, data_id=msg.inspection_id)
        if event.status in {"COMPLETED", "SYNCING"}:
            result_status = CONTROL_DUPLICATE
        elif event.status != "RUNNING":
            return IngestResult(status=CONTROL_INVALID_TRANSITION, device_id=msg.device_id, data_id=msg.inspection_id, reason=f"当前状态 {event.status}")
        else:
            event.pending_sync_count = msg.pending_sync_count
            event.sync_status = "PENDING" if msg.pending_sync_count else "SYNCED"
            event.status = "SYNCING" if msg.pending_sync_count else "COMPLETED"
            event.ended_at = event_time
        device.operating_status = "SHUTDOWN"
        device.pending_sync_count = msg.pending_sync_count
        device.sync_status = "PENDING" if msg.pending_sync_count else "IDLE"
        device.last_seen_at = datetime.now(timezone.utc)

    now = datetime.now(timezone.utc)
    ack = {
        "type": "control_ack", "request_id": request_id,
        "inspection_id": msg.inspection_id, "command": msg.command,
        "status": "ACCEPTED", "cloud_time": _dt_iso(now),
        "message": "巡检任务已创建" if msg.command == "START" else "巡检结束已确认",
    }
    session.add(DeviceControlRequest(
        device_id=msg.device_id, request_id=request_id,
        inspection_id=msg.inspection_id, command=msg.command,
        status="ACCEPTED", ack_payload=ack,
    ))
    await session.commit()
    await mqtt_publisher.publish_downlink(msg.device_id, ack)
    return IngestResult(status=result_status, device_id=msg.device_id, data_id=msg.inspection_id)


async def ingest_status_message(session: AsyncSession, payload: Any, topic: str) -> IngestResult:
    match = _STATUS_TOPIC_RE.match(topic or "")
    if match is None:
        return IngestResult(status=INGEST_INVALID_TOPIC, reason=f"非法 status topic: {topic}")
    try:
        msg = DeviceStatusMessage.model_validate(payload)
    except ValidationError as exc:
        return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=match.group(1), reason=str(exc.errors())[:200])
    if msg.device_id != match.group(1):
        return IngestResult(status=INGEST_DEVICE_MISMATCH, device_id=match.group(1))
    device = await session.scalar(select(Device).where(
        Device.device_id == msg.device_id, Device.status == 1,
    ).with_for_update().execution_options(populate_existing=True))
    if device is None:
        return IngestResult(status=INGEST_UNKNOWN_DEVICE, device_id=msg.device_id)
    previous_time = (device.last_status_payload or {}).get("timestamp")
    try:
        if (msg.communication_status != "OFFLINE" and previous_time and msg.timestamp
                and _parse_dt(msg.timestamp) <= _parse_dt(previous_time)):
            return IngestResult(status=CONTROL_DUPLICATE, device_id=msg.device_id)
    except (ValueError, TypeError):
        return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=msg.device_id, reason="非法心跳时间")
    device.last_seen_at = datetime.now(timezone.utc)
    device.communication_status = msg.communication_status
    device.operating_status = msg.operating_status or device.operating_status
    device.sync_status = msg.sync_status
    device.pending_sync_count = msg.pending_sync_count
    device.last_status_payload = payload
    if msg.inspection_id:
        event = await session.scalar(select(InspectionEvent).where(
            InspectionEvent.inspection_id == msg.inspection_id,
            InspectionEvent.device_id == msg.device_id,
        ).with_for_update().execution_options(populate_existing=True))
        if event is not None and event.status not in end_confirmation.TERMINAL:
            # A V2 END heartbeat is display information, not completion proof.
            # An old pre-END zero heartbeat must not replace its pending phase.
            if event.status not in {"ENDING", "SYNCING"}:
                event.pending_sync_count = msg.pending_sync_count
                event.sync_status = msg.sync_status
            elif msg.pending_sync_count > 0:
                event.pending_sync_count = msg.pending_sync_count
                event.sync_status = "PENDING"
            if event.status == "RUNNING" and msg.communication_status == "OFFLINE":
                event.status = "RUNNING_OFFLINE"
            elif event.status == "RUNNING_OFFLINE" and msg.communication_status == "ONLINE":
                event.status = "RUNNING"
            end_command = await session.scalar(select(TaskCommand).where(
                TaskCommand.inspection_pk == event.id,
                TaskCommand.command_type == "END_INSPECTION",
            ))
            legacy_end = await session.scalar(select(DeviceControlRequest).where(
                DeviceControlRequest.inspection_id == event.inspection_id,
                DeviceControlRequest.device_id == event.device_id,
                DeviceControlRequest.command == "END",
                DeviceControlRequest.status == "ACCEPTED",
            ))
            if (event.status == "SYNCING" and msg.pending_sync_count == 0
                    and end_command is None and event.client_request_id is None and legacy_end is not None):
                event.status = "COMPLETED"
                event.sync_status = "SYNCED"
                event.pending_sync_count = 0
                event.ended_at = datetime.now(timezone.utc)
    await session.commit()
    return IngestResult(status="status_updated", device_id=msg.device_id, data_id=msg.inspection_id)


async def ingest_ack_message(session: AsyncSession, payload: Any, topic: str) -> IngestResult:
    match = _ACK_TOPIC_RE.match(topic or "")
    if match is None:
        return IngestResult(status=INGEST_INVALID_TOPIC, reason=f"非法 ack topic: {topic}")
    try:
        msg = DeviceAckMessage.model_validate(payload)
    except ValidationError as exc:
        return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=match.group(1), reason=str(exc.errors())[:200])
    if msg.device_id != match.group(1):
        return IngestResult(status=INGEST_DEVICE_MISMATCH, device_id=match.group(1))
    device = await session.scalar(select(Device).where(
        Device.device_id == msg.device_id, Device.status == 1,
    ).with_for_update().execution_options(populate_existing=True))
    if device is None:
        return IngestResult(status=INGEST_UNKNOWN_DEVICE, device_id=msg.device_id)
    device.last_seen_at = datetime.now(timezone.utc)
    device.communication_status = "ONLINE"
    command = await session.scalar(select(TaskCommand).where(
        TaskCommand.command_id == msg.command_id, TaskCommand.device_pk == device.id
    ).with_for_update().execution_options(populate_existing=True))
    if command is None:
        await session.commit()
        # V1.2 devices emitted informational ACKs without a persisted cloud
        # command. Keep accepting those while V2.0 commands use the state machine.
        return IngestResult(status="ack_received", device_id=msg.device_id, data_id=msg.command_id)
    event = await session.scalar(select(InspectionEvent).where(
        InspectionEvent.id == command.inspection_pk,
    ).with_for_update().execution_options(populate_existing=True))
    if (event is None or event.device_id != msg.device_id
            or (msg.inspection_id is not None and msg.inspection_id != event.inspection_id)
            or (msg.command is not None and msg.command != command.command_type)
            or (command.command_type == "END_INSPECTION"
                and (msg.inspection_id != event.inspection_id or msg.command != command.command_type))):
        return IngestResult(status=INGEST_DEVICE_MISMATCH, device_id=msg.device_id, data_id=msg.command_id)
    normalized = msg.status.upper()
    if (command.status in {"COMPLETED", "REJECTED", "FAILED", "CANCELLED", "EXPIRED"}
            or event.status in end_confirmation.TERMINAL):
        await session.commit()
        return IngestResult(status=CONTROL_DUPLICATE, device_id=msg.device_id, data_id=msg.command_id)
    evidence = msg.model_dump(mode="json")
    if normalized not in {"ACCEPTED", "COMPLETED", "REJECTED", "FAILED", "CANCELLED"}:
        return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=msg.device_id, reason="未知 ACK 状态")
    if command.command_type == "END_INSPECTION" and normalized in {"ACCEPTED", "COMPLETED"}:
        summary = end_confirmation.stopped_summary(evidence)
        if ((msg.summary is not None and summary is None)
                or (normalized == "COMPLETED" and (summary is None
                    or summary["pending_sync_count"] != 0 or msg.phase != "COMPLETED"))
                or (normalized == "ACCEPTED" and summary is not None and msg.phase != "SYNCING")):
            return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=msg.device_id, reason="非法 END 停止摘要/阶段")
        slot = "accepted_ack_payload" if normalized == "ACCEPTED" else "final_ack_payload"
        existing = getattr(command, slot)
        if end_confirmation.stopped_summary(existing):
            old = end_confirmation.stopped_summary(existing)
            if summary is None or any(old[key] != summary[key] for key in (
                "sampling_stopped", "last_data_id", "last_sequence", "sample_count"
            )):
                return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=msg.device_id, reason="END 停止摘要不可改变")
        else:
            setattr(command, slot, evidence)
        other = command.final_ack_payload if normalized == "ACCEPTED" else command.accepted_ack_payload
        other_summary = end_confirmation.stopped_summary(other)
        if summary and other_summary and any(summary[key] != other_summary[key] for key in (
            "sampling_stopped", "last_data_id", "last_sequence", "sample_count"
        )):
            await session.rollback()
            return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=msg.device_id, reason="END 两阶段摘要不一致")
        command.ack_payload = evidence
        command.acknowledged_at = datetime.now(timezone.utc)
        if normalized == "ACCEPTED":
            command.status = "ACCEPTED"
            event.status, event.sync_status = "SYNCING", "PENDING"
            if summary:
                event.pending_sync_count = summary["pending_sync_count"]
            device.operating_status = "SHUTDOWN"
        # A final ACK received first is evidence only, not a fabricated ACCEPTED.
        await end_confirmation.try_complete(session, command, event)
        await session.commit()
        return IngestResult(status="ack_received", device_id=msg.device_id, data_id=msg.command_id)
    if command.status in {"ACCEPTED", "EXECUTING"}:
        await session.commit()
        return IngestResult(status=CONTROL_DUPLICATE, device_id=msg.device_id, data_id=msg.command_id)
    if normalized == "COMPLETED":
        return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=msg.device_id, reason="START 需要 ACCEPTED 回执")
    command.ack_payload = evidence
    command.acknowledged_at = datetime.now(timezone.utc)
    if normalized == "ACCEPTED":
        command.status = "ACCEPTED"
        if command.command_type == "START_INSPECTION":
            if event.status in {"START_REQUESTED", "STARTING"}:
                event.status = "RUNNING"
                device.operating_status = "RUNNING"
            event.started_at = event.started_at or datetime.now(timezone.utc)
    elif normalized in {"REJECTED", "FAILED", "CANCELLED"}:
        command.status = normalized
        command.failure_reason = msg.reason_code or f"设备返回 {normalized}"
        if event is not None:
            event.status = "FAILED" if normalized != "CANCELLED" else "CANCELLED"
            event.failure_reason = command.failure_reason
            event.ended_at = datetime.now(timezone.utc)
    await session.commit()
    return IngestResult(status="ack_received", device_id=msg.device_id, data_id=msg.command_id)


def _parse_dt(value: str) -> datetime:
    """解析 ISO8601 时间串（容忍尾缀 Z）."""
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _dt_iso(value: Optional[datetime]) -> Optional[str]:
    """序列化时间为 ISO8601（UTC，尾缀 Z）."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def _resolve_owner(session: AsyncSession, device_id: str) -> tuple[Optional[Device], Optional[int]]:
    """解析设备与归属用户，返回 (device, owner_user_id)."""
    device = await session.scalar(
        select(Device).where(Device.device_id == device_id, Device.status == 1)
        .with_for_update().execution_options(populate_existing=True)
    )
    if device is None:
        return None, None
    binding = await session.scalar(
        select(DeviceBinding).where(
            DeviceBinding.device_id == device.id,
            DeviceBinding.status == 1,
        )
    )
    return device, (binding.user_id if binding else None)


async def ingest_message(
    session: AsyncSession, payload: Any, topic: str
) -> IngestResult:
    """处理一条 MQTT 消息，完成校验与结构化入库（commit 由调用方或本函数提交）.

    返回 IngestResult，其中 status 区分：inserted / duplicate / 各类失败原因。
    校验失败不会写入数据库，也不会抛出异常。
    """
    # 1. Topic 校验
    topic_device_id = parse_topic(topic)
    if topic_device_id is None:
        return IngestResult(status=INGEST_INVALID_TOPIC, reason=f"非法 topic: {topic}")

    # 2. JSON Schema 校验
    try:
        msg = MqttMessageV1.model_validate(payload)
    except ValidationError as exc:
        return IngestResult(
            status=INGEST_INVALID_SCHEMA,
            device_id=topic_device_id,
            reason=str(exc.errors())[:200],
        )

    # 3. device_id 一致性
    if msg.device_id != topic_device_id:
        return IngestResult(
            status=INGEST_DEVICE_MISMATCH,
            device_id=topic_device_id,
            data_id=msg.data_id,
            reason=f"topic({topic_device_id}) != payload({msg.device_id})",
        )

    # 4. 设备身份校验 + 5. 绑定关系校验（确定 owner）
    device, owner_user_id = await _resolve_owner(session, msg.device_id)
    if device is None:
        return IngestResult(
            status=INGEST_UNKNOWN_DEVICE, device_id=msg.device_id, data_id=msg.data_id
        )
    if owner_user_id is None:
        return IngestResult(
            status=INGEST_UNBOUND_DEVICE, device_id=msg.device_id, data_id=msg.data_id
        )

    # 6. data_id 幂等校验
    existing = await session.scalar(
        select(InspectionRecord.id).where(
            InspectionRecord.device_id == msg.device_id,
            InspectionRecord.data_id == msg.data_id,
        )
    )
    if existing is not None:
        return IngestResult(
            status=INGEST_DUPLICATE, device_id=msg.device_id, data_id=msg.data_id
        )

    # 7. 结构化写入
    captured_at = _parse_dt(msg.timestamp)
    device.last_seen_at = datetime.now(timezone.utc)
    device.communication_status = "ONLINE"
    event = None
    record = InspectionRecord(
        device_id=msg.device_id,
        data_id=msg.data_id,
        owner_user_id=owner_user_id,
        schema_version=msg.schema_version,
        captured_at=captured_at,
        raw_payload=json.dumps(payload, ensure_ascii=False),
        sequence=msg.sequence,
        field_id=msg.field_id,
        field_version=msg.field_version,
        run_mode=msg.run_mode,
        data_provenance=msg.data_provenance,
        flight_status=msg.flight_status,
    )
    if msg.inspection_id:
        event = await session.scalar(
            select(InspectionEvent).where(
                InspectionEvent.inspection_id == msg.inspection_id,
                InspectionEvent.device_id == msg.device_id,
                InspectionEvent.owner_user_id == owner_user_id,
            )
        )
        # Data may be delivered immediately after the device accepts START while
        # the ACK is still being committed on another MQTT topic.  Keep it bound
        # to the cloud-created task during these short transition states.
        if event is not None and event.status in {
            "CREATED", "START_REQUESTED", "STARTING", "RUNNING",
            "RUNNING_OFFLINE", "ENDING", "SYNCING",
        }:
            if msg.field_id and event.field_id and msg.field_id != event.field_id:
                return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=msg.device_id, data_id=msg.data_id,
                                    reason="field_id 与任务快照不一致")
            if msg.field_version and event.field_version and msg.field_version != event.field_version:
                return IngestResult(status=INGEST_INVALID_SCHEMA, device_id=msg.device_id, data_id=msg.data_id,
                                    reason="field_version 与任务快照不一致")
            record.event_id = event.id
            if event.status == "CREATED":
                event.status = "RUNNING"
                event.started_at = captured_at
    session.add(record)
    if (device.operating_status not in {"ERROR", "DISABLED"}
            and (event is None or event.status in {"CREATED", "RUNNING", "RUNNING_OFFLINE"})):
        device.operating_status = "RUNNING"
    await session.flush()  # 取得 record.id

    session.add(LocationRecord(
        inspection_id=record.id,
        latitude=msg.location.latitude,
        longitude=msg.location.longitude,
        altitude_msl_m=msg.location.altitude_msl_m,
        height_ellipsoid_m=msg.location.height_ellipsoid_m,
        fix_quality=msg.location.fix_quality,
        rtk_status=msg.location.rtk_status,
        satellites_used=msg.location.satellites_used,
        horizontal_accuracy_m=msg.location.horizontal_accuracy_m,
        vertical_accuracy_m=msg.location.vertical_accuracy_m,
        ground_speed_mps=msg.location.ground_speed_mps,
        course_over_ground_deg=msg.location.course_over_ground_deg,
        correction_age_s=msg.location.correction_age_s,
        position_valid=msg.location.position_valid,
        sampled_at=_parse_dt(msg.location.sampled_at) if msg.location.sampled_at else None,
    ))
    session.add(EnvironmentRecord(
        inspection_id=record.id,
        temperature=msg.environment.temperature,
        humidity=msg.environment.humidity,
        co2=msg.environment.co2,
        light=msg.environment.light,
        sampled_at=_parse_dt(msg.environment.sampled_at) if msg.environment.sampled_at else None,
        valid=msg.environment.valid,
    ))
    session.add(DeviceStatusRecord(
        inspection_id=record.id,
        cpu_usage=msg.device_status.cpu_usage,
        memory_usage=msg.device_status.memory_usage,
        temperature=msg.device_status.temperature,
        storage_usage=msg.device_status.storage_usage,
        network_status=msg.device_status.network_status,
    ))

    detection = DetectionRecord(
        inspection_id=record.id, has_target=msg.detection.has_target,
        sampled_at=_parse_dt(msg.detection.sampled_at) if msg.detection.sampled_at else None,
    )
    session.add(detection)
    await session.flush()
    for item in msg.detection.results:
        session.add(DetectionResult(
            detection_id=detection.id,
            class_name=item.class_name,
            confidence=item.confidence,
            bbox=list(item.bbox),
        ))

    latest = await session.scalar(select(DeviceLatestData).where(DeviceLatestData.device_pk == device.id))
    now = datetime.now(timezone.utc)
    if latest is None:
        session.add(DeviceLatestData(
            device_pk=device.id, owner_user_id=owner_user_id, inspection_pk=record.event_id,
            raw_payload=payload, received_at=now,
        ))
    elif (latest.owner_user_id != owner_user_id
          or captured_at >= _parse_dt(latest.raw_payload["timestamp"])):
        latest.owner_user_id = owner_user_id
        latest.inspection_pk = record.event_id
        latest.raw_payload = payload
        latest.received_at = now

    if record.event_id:
        await session.flush()
        await end_confirmation.recheck_after_data(session, record.event_id)

    await session.commit()
    return IngestResult(status=INGEST_INSERTED, device_id=msg.device_id, data_id=msg.data_id)


# ---- 查询 ----

async def list_inspections(
    session: AsyncSession,
    user_id: int,
    device_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """分页查询当前用户可访问的巡检记录摘要."""
    page = max(1, page)
    page_size = min(max(1, page_size), 200)

    conditions = [InspectionRecord.owner_user_id == user_id]
    if device_id:
        conditions.append(InspectionRecord.device_id == device_id)

    total = await session.scalar(
        select(func.count(InspectionRecord.id)).where(*conditions)
    ) or 0

    rows = (
        await session.execute(
            select(InspectionRecord)
            .where(*conditions)
            .order_by(InspectionRecord.received_at.desc(), InspectionRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = [
        {
            "id": r.id,
            "device_id": r.device_id,
            "data_id": r.data_id,
            "schema_version": r.schema_version,
            "sequence": r.sequence,
            "captured_at": _dt_iso(r.captured_at),
            "received_at": _dt_iso(r.received_at),
        }
        for r in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


async def _get_owned_inspection(
    session: AsyncSession, user_id: int, data_id: str
) -> InspectionRecord:
    """按 data_id 取记录并校验归属（非本人 → 403；不存在 → 404）."""
    record = await session.scalar(
        select(InspectionRecord)
        .options(
            selectinload(InspectionRecord.location),
            selectinload(InspectionRecord.environment),
            selectinload(InspectionRecord.device_status),
            selectinload(InspectionRecord.detection).selectinload(DetectionRecord.results),
            selectinload(InspectionRecord.images).selectinload(ImageRecord.cloud_detection),
        )
        .where(InspectionRecord.data_id == data_id)
    )
    if record is None:
        raise NotFoundError("巡检记录不存在")
    if record.owner_user_id != user_id:
        raise ForbiddenError("无权访问该巡检记录")
    return record


def _serialize_cloud_detection(cd: Optional[CloudDetection]) -> Optional[dict[str, Any]]:
    if cd is None:
        return None
    return {
        "status": cd.status,
        "model_name": cd.model_name,
        "model_version": cd.model_version,
        "weights_identifier": cd.weights_identifier,
        "processed_at": _dt_iso(cd.processed_at),
        "has_target": cd.has_target,
        "results": cd.results or [],
        "error_message": cd.error_message,
    }


async def get_inspection_full(
    session: AsyncSession, user_id: int, data_id: str
) -> dict[str, Any]:
    """返回最终完整 JSON：MQTT V1.0 + images + cloud_detection."""
    record = await _get_owned_inspection(session, user_id, data_id)

    mqtt: dict[str, Any] = {
        "schema_version": record.schema_version,
        "device_id": record.device_id,
        "data_id": record.data_id,
        "sequence": record.sequence,
        "timestamp": _dt_iso(record.captured_at),
        "location": None,
        "environment": None,
        "detection": {"has_target": False, "results": []},
        "device_status": None,
    }

    if record.location:
        loc = record.location
        mqtt["location"] = {
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "altitude_msl_m": loc.altitude_msl_m,
            "height_ellipsoid_m": loc.height_ellipsoid_m,
            "fix_quality": loc.fix_quality,
            "rtk_status": loc.rtk_status,
            "satellites_used": loc.satellites_used,
            "horizontal_accuracy_m": loc.horizontal_accuracy_m,
            "vertical_accuracy_m": loc.vertical_accuracy_m,
            "ground_speed_mps": loc.ground_speed_mps,
            "course_over_ground_deg": loc.course_over_ground_deg,
            "correction_age_s": loc.correction_age_s,
            "position_valid": loc.position_valid,
            "sampled_at": _dt_iso(loc.sampled_at),
        }
    if record.environment:
        env = record.environment
        mqtt["environment"] = {
            "temperature": env.temperature,
            "humidity": env.humidity,
            "co2": env.co2,
            "light": env.light,
            "sampled_at": _dt_iso(env.sampled_at),
            "valid": env.valid,
        }
    if record.device_status:
        st = record.device_status
        mqtt["device_status"] = {
            "cpu_usage": st.cpu_usage,
            "memory_usage": st.memory_usage,
            "temperature": st.temperature,
            "storage_usage": st.storage_usage,
            "network_status": st.network_status,
        }
    if record.detection:
        mqtt["detection"] = {
            "has_target": record.detection.has_target,
            "sampled_at": _dt_iso(record.detection.sampled_at),
            "results": [
                {"class": r.class_name, "confidence": r.confidence, "bbox": r.bbox}
                for r in record.detection.results
            ],
        }

    images: list[dict[str, Any]] = []
    primary_cloud: Optional[dict[str, Any]] = None
    for img in record.images:
        item = {
            "image_id": img.image_id,
            "image_type": img.image_type,
            "upload_status": img.upload_status,
            "content_type": img.content_type,
            "size_bytes": img.size_bytes,
            "url": f"{settings.API_PREFIX}/image/{img.image_id}/file",
            "cloud_detection": _serialize_cloud_detection(img.cloud_detection),
        }
        if img.image_type == "original" and primary_cloud is None:
            primary_cloud = item["cloud_detection"]
        images.append(item)

    return {
        **mqtt,
        "images": images,
        "cloud_detection": primary_cloud,
    }


async def get_inspection_stats(
    session: AsyncSession, user_id: int, device_id: Optional[str] = None
) -> dict[str, Any]:
    """统计当前用户巡检数据量（按设备可选过滤）."""
    conditions = [InspectionRecord.owner_user_id == user_id]
    if device_id:
        conditions.append(InspectionRecord.device_id == device_id)

    total = await session.scalar(
        select(func.count(InspectionRecord.id)).where(*conditions)
    ) or 0
    devices = (
        await session.execute(
            select(InspectionRecord.device_id, func.count(InspectionRecord.id))
            .where(InspectionRecord.owner_user_id == user_id)
            .group_by(InspectionRecord.device_id)
        )
    ).all()

    return {
        "total": total,
        "by_device": [{"device_id": d, "count": c} for d, c in devices],
    }
