"""Cloud-owned inspection lifecycle, live telemetry and spatial results."""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.core.config import settings
from app.models.device import Device, DeviceBinding
from app.models.field import Field
from app.models.inspection import DetectionRecord, ImageRecord, InspectionEvent, InspectionRecord
from app.models.task import DeviceLatestData, TaskCommand
from app.services import command_delivery, field_service, voronoi_service

ACTIVE_STATES = {"START_REQUESTED", "STARTING", "RUNNING", "RUNNING_OFFLINE", "ENDING", "SYNCING"}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return _aware(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def standard_device_state(device: Device, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    if device.status != 1:
        return "DISABLED"
    if (device.communication_status == "OFFLINE" or not device.last_seen_at
            or _aware(device.last_seen_at) < now - timedelta(seconds=10)):
        return "OFFLINE"
    if device.operating_status == "ERROR":
        return "ERROR"
    heartbeat = device.last_status_payload or {}
    modules = [str(heartbeat.get(key) or '').upper() for key in ("camera_status", "inference_status")]
    if any(value in {"ERROR", "FAILED", "UNAVAILABLE", "DISCONNECTED"} for value in modules):
        return "ERROR"
    gps = str(heartbeat.get("gps_fix") or '').upper()
    if (gps in {"NO_FIX", "INVALID", "ERROR"}
            or any(value in {"NOT_STARTED", "STARTING", "STARTUP", "NOT_READY"} for value in modules)):
        return "ONLINE_NOT_READY"
    if device.device_id == "TLD_SIM_002" and (
        gps not in {"GPS_FIX", "DGPS", "RTK_FLOAT", "RTK_FIXED"} or modules != ["READY", "READY"]
    ):
        return "ONLINE_NOT_READY"
    if device.pending_sync_count > 0 or device.sync_status not in {"IDLE", "SYNCED"}:
        return "SYNCING"
    if device.operating_status == "RUNNING":
        return "BUSY"
    if device.operating_status == "SHUTDOWN":
        return "READY"
    return "ONLINE_NOT_READY"


async def _owned_device(db: AsyncSession, user_id: int, device_id: str) -> Device:
    row = await db.scalar(
        select(Device).join(DeviceBinding, DeviceBinding.device_id == Device.id).where(
            Device.device_id == device_id, DeviceBinding.user_id == user_id,
            DeviceBinding.status == 1, Device.status == 1,
        )
    )
    if row is None:
        raise ForbiddenError("设备未绑定、已禁用或不属于当前用户")
    return row


async def _owned_event(db: AsyncSession, user_id: int, inspection_id: str) -> InspectionEvent:
    row = await db.scalar(select(InspectionEvent).where(InspectionEvent.inspection_id == inspection_id))
    if row is None:
        raise NotFoundError("巡检任务不存在")
    if row.owner_user_id != user_id:
        raise ForbiddenError("无权访问该巡检任务")
    return row


def _command_dict(row: Optional[TaskCommand]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    return {
        "command_id": row.command_id, "command": row.command_type, "status": row.status,
        "retry_count": row.retry_count, "created_at": _iso(row.created_at),
        "delivered_at": _iso(row.delivered_at), "acknowledged_at": _iso(row.acknowledged_at),
        "expires_at": _iso(row.expires_at), "failure_reason": row.failure_reason,
    }


async def _expire(db: AsyncSession, command: Optional[TaskCommand], event: InspectionEvent) -> None:
    if command and command.status in {"PENDING", "DELIVERED"} and _aware(command.expires_at) <= datetime.now(timezone.utc):
        await command_delivery.expire_command(db, command.id)
        await db.refresh(command)
        await db.refresh(event)


async def _event_dict(db: AsyncSession, event: InspectionEvent) -> dict[str, Any]:
    # Commands are updated by the MQTT consumer in a separate session.  Refresh
    # both sides so the HTTP response never combines a fresh event state with a
    # stale command state from this session's identity map.
    await db.refresh(event)
    commands = (await db.execute(
        select(TaskCommand).where(TaskCommand.inspection_pk == event.id).order_by(TaskCommand.created_at, TaskCommand.id)
    )).scalars().all()
    for command in commands:
        await db.refresh(command)
        await _expire(db, command, event)
    return {
        "inspection_id": event.inspection_id, "device_id": event.device_id,
        "field_id": event.field_id, "field_version": event.field_version,
        "field_snapshot": event.field_snapshot, "name": event.name, "status": event.status,
        "sync_status": event.sync_status, "pending_sync_count": event.pending_sync_count,
        "run_mode": event.run_mode, "data_provenance": event.data_provenance,
        "started_at": _iso(event.started_at), "ended_at": _iso(event.ended_at),
        "created_at": _iso(event.created_at), "failure_reason": event.failure_reason,
        "commands": [_command_dict(c) for c in commands],
    }


async def start_inspection(db: AsyncSession, user_id: int, body: Any) -> dict[str, Any]:
    existing = await db.scalar(select(InspectionEvent).where(
        InspectionEvent.owner_user_id == user_id,
        InspectionEvent.client_request_id == body.client_request_id,
    ))
    if existing is not None:
        commands = (await db.execute(select(TaskCommand.id).where(
            TaskCommand.inspection_pk == existing.id,
            TaskCommand.status.in_({"PENDING", "DELIVERED"}),
        ))).scalars().all()
        for command_pk in commands:
            await command_delivery.dispatch_command(db, command_pk)
        return await _event_dict(db, existing)

    field = await field_service.owned_field(db, user_id, body.field_id)
    if field.status != "READY":
        raise BusinessError("烟田当前不可用于巡检", code=409, status_code=409)
    device = await _owned_device(db, user_id, body.device_id)
    device_state = standard_device_state(device)
    if device_state != "READY":
        raise BusinessError(f"设备未就绪：{device_state}", code=409, status_code=409,
                            data={"device_state": device_state})
    conflict = await db.scalar(select(InspectionEvent.id).where(
        InspectionEvent.device_id == device.device_id, InspectionEvent.status.in_(ACTIVE_STATES)
    ))
    if conflict is not None:
        raise BusinessError("设备已有进行中的巡检", code=409, status_code=409)

    now = datetime.now(timezone.utc)
    inspection_id = f"INS_{uuid4().hex.upper()}"
    command_id = f"CMD_{uuid4().hex.upper()}"
    snap = field_service.snapshot(field)
    event = InspectionEvent(
        inspection_id=inspection_id, device_id=device.device_id, owner_user_id=user_id,
        name=(body.name or f"{field.name}巡检").strip(), location_name=field.name,
        status="START_REQUESTED", field_pk=field.id, field_id=field.field_id,
        field_version=field.version, field_snapshot=snap,
        client_request_id=body.client_request_id, run_mode=body.run_mode,
        data_provenance="SIMULATED" if body.run_mode != "REAL_DEVICE" else "DEVICE",
        sync_status="SYNCED", pending_sync_count=0,
    )
    db.add(event)
    await db.flush()
    expires_at = now + timedelta(seconds=settings.MQTT_COMMAND_TTL_SECONDS)
    payload = {
        "type": "inspection_command", "schema_version": "2.0", "command_id": command_id,
        "command": "START_INSPECTION", "inspection_id": inspection_id,
        "device_id": device.device_id, "field_id": field.field_id, "field_version": field.version,
        "field_snapshot": snap, "run_mode": body.run_mode,
        "timestamp": _iso(now), "expires_at": _iso(expires_at),
    }
    command = TaskCommand(
        command_id=command_id, inspection_pk=event.id, device_pk=device.id,
        command_type="START_INSPECTION", status="PENDING", payload=payload, expires_at=expires_at,
    )
    db.add(command)
    await db.commit()
    await command_delivery.dispatch_command(db, command.id)
    return await _event_dict(db, event)


async def end_inspection(db: AsyncSession, user_id: int, inspection_id: str, client_request_id: str) -> dict[str, Any]:
    event = await _owned_event(db, user_id, inspection_id)
    existing = await db.scalar(select(TaskCommand).where(
        TaskCommand.inspection_pk == event.id, TaskCommand.command_type == "END_INSPECTION"
    ))
    if existing is not None:
        await command_delivery.dispatch_command(db, existing.id)
        return await _event_dict(db, event)
    if event.status not in {"RUNNING", "RUNNING_OFFLINE"}:
        raise BusinessError(f"当前任务状态 {event.status} 不允许结束", code=409, status_code=409)
    device = await _owned_device(db, user_id, event.device_id)
    if standard_device_state(device) == "OFFLINE":
        raise BusinessError("设备离线，结束命令未下发", code=409, status_code=409)
    now = datetime.now(timezone.utc)
    command_id = f"CMD_{uuid4().hex.upper()}"
    expires_at = now + timedelta(seconds=settings.MQTT_COMMAND_TTL_SECONDS)
    payload = {
        "type": "inspection_command", "schema_version": "2.0", "command_id": command_id,
        "command": "END_INSPECTION", "inspection_id": inspection_id,
        "device_id": device.device_id, "field_id": event.field_id, "field_version": event.field_version,
        "client_request_id": client_request_id, "timestamp": _iso(now), "expires_at": _iso(expires_at),
    }
    command = TaskCommand(command_id=command_id, inspection_pk=event.id, device_pk=device.id,
                          command_type="END_INSPECTION", status="PENDING", payload=payload, expires_at=expires_at)
    db.add(command)
    event.status = "ENDING"
    await db.commit()
    await command_delivery.dispatch_command(db, command.id)
    return await _event_dict(db, event)


async def current_inspection(db: AsyncSession, user_id: int, device_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    conditions = [InspectionEvent.owner_user_id == user_id, InspectionEvent.status.in_(ACTIVE_STATES)]
    if device_id:
        conditions.append(InspectionEvent.device_id == device_id)
    event = await db.scalar(select(InspectionEvent).where(*conditions).order_by(InspectionEvent.created_at.desc()))
    return await _event_dict(db, event) if event else None


async def get_inspection(db: AsyncSession, user_id: int, inspection_id: str) -> dict[str, Any]:
    return await _event_dict(db, await _owned_event(db, user_id, inspection_id))


async def list_history(db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    rows = (await db.execute(select(InspectionEvent).where(
        InspectionEvent.owner_user_id == user_id
    ).order_by(InspectionEvent.created_at.desc()))).scalars().all()
    return [await _event_dict(db, row) for row in rows]


def _risk_level(score: float, valid: int) -> str:
    if valid < 3:
        return "INSUFFICIENT"
    if score < 15:
        return "LOW"
    if score < 35:
        return "ATTENTION"
    if score < 60:
        return "REVIEW"
    return "HIGH"


async def spatial_result(db: AsyncSession, user_id: int, inspection_id: str) -> dict[str, Any]:
    event = await _owned_event(db, user_id, inspection_id)
    records = (await db.execute(select(InspectionRecord).options(
        selectinload(InspectionRecord.location),
        selectinload(InspectionRecord.detection).selectinload(DetectionRecord.results),
        selectinload(InspectionRecord.images).selectinload(ImageRecord.cloud_detection),
    ).where(InspectionRecord.event_id == event.id).order_by(InspectionRecord.sequence))).scalars().all()
    snap = event.field_snapshot or {}
    transform = snap.get("transform_params") or {}
    polygon = snap.get("pixel_boundary") or []
    width = float(transform.get("image_width", 1600))
    height = float(transform.get("image_height", 1105))
    lng0, lat0 = float(transform.get("origin_longitude", 0)), float(transform.get("origin_latitude", 0))
    dlng, dlat = float(transform.get("longitude_per_pixel", 1)), float(transform.get("latitude_per_pixel", -1))
    track, disease_points = [], []
    samples: list[dict[str, Any]] = []
    for record in records:
        if (snap.get("calibration_status") == "SIMULATED"
                and (record.run_mode == "REAL_DEVICE" or record.data_provenance == "DEVICE")):
            # The demo transform is not a geographic calibration for hardware.
            # Raw WGS84 telemetry remains available through live/geographic APIs.
            continue
        if (not record.location or not record.location.position_valid
                or record.location.longitude is None or record.location.latitude is None):
            continue
        x = (record.location.longitude - lng0) / dlng if dlng else 0
        y = (record.location.latitude - lat0) / dlat if dlat else 0
        edge = list(record.detection.results) if record.detection else []
        cloud = [item for image in record.images for item in (
            image.cloud_detection.results if image.cloud_detection and image.cloud_detection.results else []
        )]
        confidences = [float(item.confidence) for item in edge] + [float(item.get("confidence", 0)) for item in cloud]
        image_items = [{"image_id": image.image_id, "url": f"/api/image/{image.image_id}/file"} for image in record.images]
        point = {"x": round(x, 2), "y": round(y, 2), "lng": record.location.longitude,
                 "lat": record.location.latitude,
                 "x_pct": round(100 * x / width, 3) if width else 0,
                 "y_pct": round(100 * y / height, 3) if height else 0,
                 "sequence": record.sequence, "captured_at": _iso(record.captured_at)}
        track.append(point)
        samples.append({**point, "confidence": max(confidences, default=0), "images": image_items})
        if confidences:
            disease_points.append({**point, "confidence": max(confidences), "images": image_items})
    cells = voronoi_service.clipped_voronoi(
        str(event.field_id or snap.get("field_id") or "UNASSIGNED"),
        int(event.field_version or snap.get("version") or 0),
        polygon,
    )
    grouped: list[list[dict[str, Any]]] = [[] for _ in cells]
    for sample in samples:
        if cells:
            grouped[voronoi_service.assign_cell(sample["x"], sample["y"], cells)].append(sample)
    grids = []
    for index, cell in enumerate(cells):
        group = grouped[index]
        valid = len(group)
        suspicious = sum(1 for sample in group if sample["confidence"] > 0)
        score = round(100 * sum(sample["confidence"] for sample in group) / valid, 1) if valid else 0.0
        cell_polygon = cell["polygon"]
        min_x, max_x = min(point[0] for point in cell_polygon), max(point[0] for point in cell_polygon)
        min_y, max_y = min(point[1] for point in cell_polygon), max(point[1] for point in cell_polygon)
        rounded_polygon = [[round(point[0], 2), round(point[1], 2)] for point in cell_polygon]
        grids.append({
            "cell_id": cell["cell_id"],
            "seed": [round(cell["seed"][0], 2), round(cell["seed"][1], 2)],
            "polygon": rounded_polygon,
            "polygon_percent": [[round(100 * point[0] / width, 3), round(100 * point[1] / height, 3)]
                                for point in cell_polygon] if width and height else [],
            # Keep the old rectangle fields as the cell's bounding box for V1 clients.
            "x": round(min_x, 2), "y": round(min_y, 2),
            "width": round(max_x - min_x, 2), "height": round(max_y - min_y, 2),
            "x_pct": round(100 * min_x / width, 3) if width else 0,
            "y_pct": round(100 * min_y / height, 3) if height else 0,
            "width_pct": round(100 * (max_x - min_x) / width, 3) if width else 0,
            "height_pct": round(100 * (max_y - min_y) / height, 3) if height else 0,
            "sample_count": len(group), "valid_sample_count": valid,
            "suspicious_count": suspicious, "risk_score": score,
            "risk_level": _risk_level(score, valid),
            "images": [image for sample in group for image in sample["images"]],
        })
    return {
        "inspection_id": inspection_id, "field": snap, "track": track,
        "risk_grids": grids, "disease_points": disease_points,
        "risk_formula": "100 × Σ(每个有效采样点的最高置信度) ÷ 有效采样点数；少于3个有效样本为数据不足",
        "risk_thresholds": {"LOW": "<15", "ATTENTION": "15–<35", "REVIEW": "35–<60", "HIGH": ">=60"},
    }


def _display_from_payloads(payloads: list[dict]) -> dict[str, Any]:
    latest = payloads[0] if payloads else {}
    display = {k: v for k, v in latest.items()}
    for block, keys in {"environment": ("temperature", "humidity", "co2", "light"),
                        "device_status": ("cpu_usage", "memory_usage", "temperature", "storage_usage")}.items():
        latest_block = dict(latest.get(block) or {})
        for key in keys:
            if latest_block.get(key) is None or (block == "environment" and not latest_block.get("valid", True)):
                continue
            values = [p.get(block, {}).get(key) for p in payloads
                      if isinstance(p.get(block, {}).get(key), (int, float))
                      and math.isfinite(p[block][key])
                      and (block != "environment" or p[block].get("valid", True))]
            if values:
                median = statistics.median(values[:3])
                latest_block[key] = round(0.65 * float(values[0]) + 0.35 * float(median), 3)
        display[block] = latest_block
    return display


async def live_by_device(db: AsyncSession, user_id: int, device_id: str, *, inspection_pk: Optional[int] = None) -> dict[str, Any]:
    device = await _owned_device(db, user_id, device_id)
    latest = await db.scalar(select(DeviceLatestData).where(DeviceLatestData.device_pk == device.id))
    if inspection_pk is not None:
        # Task live must not borrow the latest telemetry of a different task.
        latest = await db.scalar(select(InspectionRecord).where(
            InspectionRecord.device_id == device_id, InspectionRecord.owner_user_id == user_id,
            InspectionRecord.event_id == inspection_pk,
        ).order_by(InspectionRecord.captured_at.desc(), InspectionRecord.id.desc()).limit(1))
    if latest is None or latest.owner_user_id != user_id:
        return {"device_id": device_id, "raw": None, "display": None, "received_at": None,
                "age_ms": None, "link_state": "NO_DATA", "device_state": standard_device_state(device)}
    raw = json.loads(latest.raw_payload) if isinstance(latest.raw_payload, str) else latest.raw_payload
    event_id = inspection_pk if inspection_pk is not None else latest.inspection_pk
    recent = (await db.execute(select(InspectionRecord.raw_payload).where(
        InspectionRecord.device_id == device_id, InspectionRecord.owner_user_id == user_id,
        InspectionRecord.event_id == event_id,
    ).order_by(InspectionRecord.captured_at.desc(), InspectionRecord.id.desc()).limit(3))).scalars().all()
    payloads = [raw] + [json.loads(item) for item in recent if item and json.loads(item).get("data_id") != raw.get("data_id")]
    age_ms = max(0, int((datetime.now(timezone.utc) - _aware(latest.received_at)).total_seconds() * 1000))
    link_state = "LIVE" if age_ms <= 3000 else "DELAYED" if age_ms <= 10000 else "DISCONNECTED"
    return {"device_id": device_id, "raw": raw, "display": _display_from_payloads(payloads),
            "received_at": _iso(latest.received_at), "age_ms": age_ms, "link_state": link_state,
            "device_state": standard_device_state(device)}


async def live_by_inspection(db: AsyncSession, user_id: int, inspection_id: str) -> dict[str, Any]:
    event = await _owned_event(db, user_id, inspection_id)
    result = await live_by_device(db, user_id, event.device_id, inspection_pk=event.id)
    result["inspection_id"] = inspection_id
    result["task_status"] = event.status
    result["field_id"] = event.field_id
    return result
