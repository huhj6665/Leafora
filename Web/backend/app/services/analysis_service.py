"""面向前端的结构化分析服务。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, DeviceBinding
from app.models.inspection import DetectionRecord, DetectionResult, EnvironmentRecord, InspectionEvent, InspectionRecord


async def overview(db: AsyncSession, user_id: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    event_total = await db.scalar(select(func.count(InspectionEvent.id)).where(InspectionEvent.owner_user_id == user_id)) or 0
    active = await db.scalar(select(func.count(InspectionEvent.id)).where(InspectionEvent.owner_user_id == user_id, InspectionEvent.status == "RUNNING")) or 0
    sample_total = await db.scalar(select(func.count(InspectionRecord.id)).where(InspectionRecord.owner_user_id == user_id)) or 0
    week_samples = await db.scalar(select(func.count(InspectionRecord.id)).where(InspectionRecord.owner_user_id == user_id, InspectionRecord.captured_at >= now - timedelta(days=7))) or 0
    device_total = await db.scalar(select(func.count(DeviceBinding.id)).where(DeviceBinding.user_id == user_id, DeviceBinding.status == 1)) or 0
    target_total = await db.scalar(
        select(func.count(DetectionResult.id))
        .join(DetectionRecord, DetectionRecord.id == DetectionResult.detection_id)
        .join(InspectionRecord, InspectionRecord.id == DetectionRecord.inspection_id)
        .where(InspectionRecord.owner_user_id == user_id)
    ) or 0
    env_rows = (await db.execute(
        select(EnvironmentRecord, InspectionRecord.captured_at)
        .join(InspectionRecord, InspectionRecord.id == EnvironmentRecord.inspection_id)
        .where(InspectionRecord.owner_user_id == user_id, EnvironmentRecord.valid.is_(True),
               EnvironmentRecord.sampled_at.is_not(None))
        .order_by(InspectionRecord.captured_at.desc()).limit(48)
    )).all()
    trends = [{
        "time": captured.isoformat() if captured else None,
        "temperature": env.temperature,
        "humidity": env.humidity,
        "co2": env.co2,
        "light": env.light,
    } for env, captured in reversed(env_rows)]
    recent_events = (await db.execute(
        select(InspectionEvent).where(InspectionEvent.owner_user_id == user_id)
        .order_by(InspectionEvent.created_at.desc()).limit(5)
    )).scalars().all()
    return {
        "metrics": {
            "events": event_total,
            "active_events": active,
            "samples": sample_total,
            "week_samples": week_samples,
            "devices": device_total,
            "targets": target_total,
        },
        "environment_trends": trends,
        "recent_events": [{
            "inspection_id": e.inspection_id,
            "name": e.name,
            "status": e.status,
            "device_id": e.device_id,
            "started_at": e.started_at.isoformat() if e.started_at else None,
        } for e in recent_events],
    }
