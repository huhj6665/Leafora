"""Field ownership, calibration and immutable task-snapshot helpers."""
from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.models.field import Field
from app.models.inspection import InspectionEvent


def pixel_to_geo(field: Field, x: float, y: float) -> list[float]:
    p = field.transform_params
    return [
        round(float(p["origin_longitude"]) + x * float(p["longitude_per_pixel"]), 8),
        round(float(p["origin_latitude"]) + y * float(p["latitude_per_pixel"]), 8),
    ]


def _geo_boundary(pixel_boundary: list, transform: dict) -> dict:
    coordinates = [[
        round(float(transform["origin_longitude"]) + float(x) * float(transform["longitude_per_pixel"]), 8),
        round(float(transform["origin_latitude"]) + float(y) * float(transform["latitude_per_pixel"]), 8),
    ] for x, y in pixel_boundary]
    if coordinates and coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])
    return {"type": "Polygon", "coordinates": [coordinates]}


def snapshot(field: Field) -> dict[str, Any]:
    return {
        "field_id": field.field_id,
        "name": field.name,
        "version": field.version,
        "coordinate_system": field.coordinate_system,
        "data_source": field.data_source,
        "calibration_status": field.calibration_status,
        "base_map_url": f"/api/fields/{field.field_id}/base-map" if field.base_map_path else None,
        "pixel_boundary": field.pixel_boundary,
        "geo_boundary": field.geo_boundary,
        "control_points": field.control_points,
        "transform_params": field.transform_params,
    }


async def owned_field(db: AsyncSession, user_id: int, field_id: str) -> Field:
    row = await db.scalar(select(Field).where(Field.field_id == field_id))
    if row is None:
        raise NotFoundError("烟田不存在")
    if row.owner_user_id != user_id:
        raise ForbiddenError("无权访问该烟田")
    return row


async def create_field(db: AsyncSession, user_id: int, body: Any) -> dict[str, Any]:
    if len(body.pixel_boundary) < 3:
        raise BusinessError("烟田边界至少需要三个点")
    transform = {
        "method": "AFFINE_SIMULATED",
        "image_width": body.image_width,
        "image_height": body.image_height,
        "origin_longitude": body.origin_longitude,
        "origin_latitude": body.origin_latitude,
        "longitude_per_pixel": body.longitude_per_pixel,
        "latitude_per_pixel": body.latitude_per_pixel,
    }
    field_id = f"FIELD_{uuid4().hex[:16].upper()}"
    row = Field(
        field_id=field_id, owner_user_id=user_id, name=body.name.strip(),
        description=body.description, pixel_boundary=body.pixel_boundary,
        geo_boundary=_geo_boundary(body.pixel_boundary, transform),
        control_points=[], transform_params=transform,
        data_source="USER_CALIBRATION", calibration_status="SIMULATED",
    )
    db.add(row)
    await db.commit()
    return await detail(db, user_id, field_id)


async def update_field(db: AsyncSession, user_id: int, field_id: str, values: dict) -> dict[str, Any]:
    row = await owned_field(db, user_id, field_id)
    changed = False
    for key in ("name", "description", "status"):
        if key in values and values[key] is not None and getattr(row, key) != values[key]:
            setattr(row, key, values[key].strip() if isinstance(values[key], str) else values[key])
            changed = True
    if values.get("pixel_boundary") is not None:
        if len(values["pixel_boundary"]) < 3:
            raise BusinessError("烟田边界至少需要三个点")
        row.pixel_boundary = values["pixel_boundary"]
        row.geo_boundary = _geo_boundary(row.pixel_boundary, row.transform_params)
        changed = True
    if changed:
        row.version += 1
        await db.commit()
    return await detail(db, user_id, field_id)


async def list_fields(db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    rows = (await db.execute(
        select(Field).where(Field.owner_user_id == user_id).order_by(Field.created_at.desc())
    )).scalars().all()
    items = []
    for row in rows:
        count = await db.scalar(select(func.count(InspectionEvent.id)).where(InspectionEvent.field_pk == row.id)) or 0
        last = await db.scalar(select(func.max(InspectionEvent.created_at)).where(InspectionEvent.field_pk == row.id))
        items.append({**snapshot(row), "status": row.status, "description": row.description,
                      "inspection_count": count, "last_inspection_at": last})
    return items


async def detail(db: AsyncSession, user_id: int, field_id: str) -> dict[str, Any]:
    row = await owned_field(db, user_id, field_id)
    count = await db.scalar(select(func.count(InspectionEvent.id)).where(InspectionEvent.field_pk == row.id)) or 0
    last = await db.scalar(select(func.max(InspectionEvent.created_at)).where(InspectionEvent.field_pk == row.id))
    return {**snapshot(row), "status": row.status, "description": row.description,
            "inspection_count": count, "last_inspection_at": last}


async def versions(db: AsyncSession, user_id: int, field_id: str) -> list[dict[str, Any]]:
    """Return the current field plus immutable versions captured by tasks."""
    row = await owned_field(db, user_id, field_id)
    events = (await db.execute(select(InspectionEvent).where(
        InspectionEvent.owner_user_id == user_id,
        InspectionEvent.field_id == field_id,
        InspectionEvent.field_snapshot.is_not(None),
    ).order_by(InspectionEvent.created_at.desc()))).scalars().all()
    result = [{"version": row.version, "source": "CURRENT", "captured_at": row.updated_at,
               "snapshot": snapshot(row)}]
    seen = {row.version}
    for event in events:
        if event.field_version in seen:
            continue
        seen.add(event.field_version)
        result.append({"version": event.field_version, "source": "INSPECTION_SNAPSHOT",
                       "captured_at": event.created_at, "inspection_id": event.inspection_id,
                       "snapshot": event.field_snapshot})
    return result
