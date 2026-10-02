"""巡检事件生命周期与详情聚合服务。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.models.device import Device, DeviceBinding
from app.models.inspection import (
    CloudDetection,
    DetectionRecord,
    ImageRecord,
    InspectionEvent,
    InspectionRecord,
)


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def _owned_event(db: AsyncSession, user_id: int, inspection_id: str) -> InspectionEvent:
    event = await db.scalar(
        select(InspectionEvent).where(InspectionEvent.inspection_id == inspection_id)
    )
    if event is None:
        raise NotFoundError("巡检事件不存在")
    if event.owner_user_id != user_id:
        raise ForbiddenError("无权访问该巡检事件")
    return event


async def create_event(
    db: AsyncSession, user_id: int, device_id: str, name: str, location_name: Optional[str]
) -> dict[str, Any]:
    bound = await db.scalar(
        select(DeviceBinding)
        .join(Device, Device.id == DeviceBinding.device_id)
        .where(
            DeviceBinding.user_id == user_id,
            DeviceBinding.status == 1,
            Device.device_id == device_id,
            Device.status == 1,
        )
    )
    if bound is None:
        raise ForbiddenError("设备未绑定、已禁用或不属于当前用户")
    event = InspectionEvent(
        inspection_id=str(uuid4()),
        device_id=device_id,
        owner_user_id=user_id,
        name=name.strip(),
        location_name=location_name.strip() if location_name else None,
        status="CREATED",
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return serialize_event(event, 0, 0, 0)


async def update_status(
    db: AsyncSession,
    user_id: int,
    inspection_id: str,
    target: str,
    failure_reason: Optional[str] = None,
) -> dict[str, Any]:
    event = await _owned_event(db, user_id, inspection_id)
    if event.client_request_id is not None:
        raise BusinessError("云端命令任务只能由设备回执推进状态", code=409, status_code=409)
    allowed = {
        "CREATED": {"RUNNING", "CANCELLED"},
        "RUNNING": {"COMPLETED", "FAILED", "CANCELLED"},
        "COMPLETED": set(),
        "FAILED": set(),
        "CANCELLED": set(),
    }
    if target not in allowed.get(event.status, set()):
        raise BusinessError(f"不允许从 {event.status} 变更为 {target}", code=409, status_code=409)
    now = datetime.now(timezone.utc)
    event.status = target
    if target == "RUNNING":
        event.started_at = event.started_at or now
    else:
        event.ended_at = now
    event.failure_reason = failure_reason if target == "FAILED" else None
    await db.commit()
    return await get_event_detail(db, user_id, inspection_id)


def serialize_event(
    event: InspectionEvent, sample_count: int, image_count: int, target_count: int
) -> dict[str, Any]:
    snapshot = event.field_snapshot or {}
    return {
        "inspection_id": event.inspection_id,
        "device_id": event.device_id,
        "field_id": event.field_id,
        "field_version": event.field_version,
        "field_name": snapshot.get("name") if event.field_id else None,
        "run_mode": event.run_mode,
        "data_provenance": event.data_provenance,
        "name": event.name,
        "location_name": event.location_name,
        "status": event.status,
        "started_at": _iso(event.started_at),
        "ended_at": _iso(event.ended_at),
        "created_at": _iso(event.created_at),
        "failure_reason": event.failure_reason,
        "sync_status": event.sync_status,
        "pending_sync_count": event.pending_sync_count,
        "sample_count": sample_count,
        "image_count": image_count,
        "target_count": target_count,
    }


async def list_events(
    db: AsyncSession,
    user_id: int,
    status: Optional[str] = None,
    device_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    page, page_size = max(page, 1), min(max(page_size, 1), 100)
    conditions = [InspectionEvent.owner_user_id == user_id]
    if status:
        conditions.append(InspectionEvent.status == status)
    if device_id:
        conditions.append(InspectionEvent.device_id == device_id)
    total = await db.scalar(select(func.count(InspectionEvent.id)).where(*conditions)) or 0
    events = (await db.execute(
        select(InspectionEvent)
        .where(*conditions)
        .order_by(InspectionEvent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()
    event_ids = [event.id for event in events]
    records_by_event: dict[int, list[InspectionRecord]] = {event_id: [] for event_id in event_ids}
    if event_ids:
        records = (await db.execute(
            select(InspectionRecord)
            .options(
                selectinload(InspectionRecord.images).selectinload(ImageRecord.cloud_detection),
                selectinload(InspectionRecord.detection).selectinload(DetectionRecord.results),
            )
            .where(InspectionRecord.event_id.in_(event_ids))
        )).scalars().all()
        for record in records:
            if record.event_id is not None:
                records_by_event[record.event_id].append(record)

    items = []
    for event in events:
        records = records_by_event[event.id]
        image_count = sum(len(r.images) for r in records)
        target_count = sum(len(r.detection.results) if r.detection else 0 for r in records)
        for record in records:
            for image in record.images:
                if image.cloud_detection and image.cloud_detection.results:
                    target_count += len(image.cloud_detection.results)
        items.append(serialize_event(event, len(records), image_count, target_count))
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def _risk(targets: list[dict[str, Any]]) -> dict[str, Any]:
    if not targets:
        return {"score": 0, "level": "LOW", "target_count": 0, "avg_confidence": 0}
    confidences = [max(0.0, min(float(t.get("confidence", 0)), 1.0)) for t in targets]
    areas = []
    for target in targets:
        box = target.get("bbox") or []
        if len(box) == 4:
            areas.append(max(0.0, float(box[2]) - float(box[0])) * max(0.0, float(box[3]) - float(box[1])))
    area_factor = min(sum(areas) / 1_000_000, 1.0)
    density_factor = min(len(targets) / 12, 1.0)
    score = round(100 * (0.4 * density_factor + 0.35 * (sum(confidences) / len(confidences)) + 0.25 * area_factor), 1)
    level = "HIGH" if score >= 70 else "MEDIUM" if score >= 38 else "LOW"
    return {
        "score": score,
        "level": level,
        "target_count": len(targets),
        "avg_confidence": round(sum(confidences) / len(confidences), 3),
        "disclaimer": "平台风险评分仅用于巡检辅助，不构成专业农业诊断。",
    }


async def get_event_detail(
    db: AsyncSession, user_id: int, inspection_id: str, include_series: bool = True
) -> dict[str, Any]:
    event = await _owned_event(db, user_id, inspection_id)
    load_options = [
        selectinload(InspectionRecord.environment),
        selectinload(InspectionRecord.device_status),
        selectinload(InspectionRecord.detection).selectinload(DetectionRecord.results),
        selectinload(InspectionRecord.images).selectinload(ImageRecord.cloud_detection),
    ]
    if include_series:
        load_options.append(selectinload(InspectionRecord.location))
    records = (await db.execute(
        select(InspectionRecord)
        .options(*load_options)
        .where(InspectionRecord.event_id == event.id)
        .order_by(InspectionRecord.captured_at)
    )).scalars().all()
    track, environment, images, targets = [], [], [], []
    environment_summary = {
        "temperature": None, "humidity": None, "co2": None, "light": None,
        "sampled_at": None, "valid_count": 0,
    }
    latest_status = None
    for record in records:
        if (include_series and record.location and record.location.position_valid
                and record.location.longitude is not None and record.location.latitude is not None):
            track.append({
                "lng": record.location.longitude,
                "lat": record.location.latitude,
                "time": _iso(record.captured_at),
                "data_id": record.data_id,
            })
        if record.environment and record.environment.valid and record.environment.sampled_at is not None:
            environment_summary = {
                "temperature": record.environment.temperature,
                "humidity": record.environment.humidity,
                "co2": record.environment.co2,
                "light": record.environment.light,
                "sampled_at": _iso(record.environment.sampled_at),
                "valid_count": int(environment_summary["valid_count"]) + 1,
            }
        if include_series and record.environment:
            environment.append({
                "time": _iso(record.environment.sampled_at),
                "temperature": record.environment.temperature,
                "humidity": record.environment.humidity,
                "co2": record.environment.co2,
                "light": record.environment.light,
                "valid": record.environment.valid,
            })
        if record.device_status:
            latest_status = {
                "cpu_usage": record.device_status.cpu_usage,
                "memory_usage": record.device_status.memory_usage,
                "temperature": record.device_status.temperature,
                "storage_usage": record.device_status.storage_usage,
                "network_status": record.device_status.network_status,
            }
        edge_targets = [
            {"class": r.class_name, "confidence": r.confidence, "bbox": r.bbox, "source": "edge"}
            for r in (record.detection.results if record.detection else [])
        ]
        targets.extend(edge_targets)
        # Generated annotation files encode the source ID in their storage key,
        # not in their random image_id. Resolve only within this owned sample.
        annotated_sources = {
            f"images/annotated/{image.image_id}_ann.jpg": image.cloud_detection
            for image in record.images if image.image_type == "original"
        }
        for image in record.images:
            cloud = image.cloud_detection
            cloud_targets = list(cloud.results or []) if cloud and cloud.status == "completed" else []
            targets.extend(cloud_targets)
            # Borrow for display only: do not count the same targets twice.
            if cloud is None and image.image_type == "annotated":
                cloud = annotated_sources.get(image.storage_key)
            images.append({
                "image_id": image.image_id,
                "data_id": record.data_id,
                "captured_at": _iso(record.captured_at),
                "image_type": image.image_type,
                "url": f"/api/image/{image.image_id}/file",
                "cloud_detection": {
                    "status": cloud.status,
                    "has_target": cloud.has_target,
                    "results": cloud.results or [],
                } if cloud else None,
            })
    summary = serialize_event(event, len(records), len(images), len(targets))
    return {
        **summary,
        "track": track,
        "environment": environment,
        "environment_summary": environment_summary,
        "images": images,
        "device_status": latest_status,
        "risk": _risk(targets),
    }
