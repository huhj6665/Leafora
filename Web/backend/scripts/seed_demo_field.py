"""Idempotently import the A-01 demo field for a phone user."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database.session import AsyncSessionLocal
from app.models.field import Field
from app.models.identity import IdentityType, UserIdentity

FIELD_ID = "FIELD_A01"
PIXELS = [
    [203, 548], [252, 523], [438, 501], [492, 500], [525, 526],
    [773, 553], [999, 579], [1041, 704], [1078, 858], [1118, 1097],
    [137, 1097], [132, 1015], [148, 875], [166, 733], [181, 632], [203, 548],
]
TRANSFORM = {
    "method": "AFFINE_SIMULATED", "image_width": 1600, "image_height": 1105,
    "origin_longitude": 113.123, "origin_latitude": 23.4565,
    "longitude_per_pixel": 0.000001, "latitude_per_pixel": -0.0000008,
}


def to_geo(x: float, y: float) -> list[float]:
    return [round(TRANSFORM["origin_longitude"] + x * TRANSFORM["longitude_per_pixel"], 8),
            round(TRANSFORM["origin_latitude"] + y * TRANSFORM["latitude_per_pixel"], 8)]


async def seed(phone: str) -> None:
    async with AsyncSessionLocal() as db:
        identity = await db.scalar(select(UserIdentity).where(
            UserIdentity.identity_type == IdentityType.PHONE.value,
            UserIdentity.identifier == phone,
        ))
        if identity is None:
            raise RuntimeError(f"手机号 {phone} 对应账号不存在；请先通过验证码登录创建正式账号。")
        row = await db.scalar(select(Field).where(Field.field_id == FIELD_ID))
        control_pixels = [PIXELS[i] for i in (0, 2, 4, 6, 9, 10, 13, 14)]
        values = {
            "owner_user_id": identity.user_id, "name": "演示烟田 A-01",
            "description": "紧贴底图下方最大绿色烟草田；WGS84 坐标为固定可复现的模拟校准数据。",
            "status": "READY", "data_source": "DEMO_IMPORT", "calibration_status": "SIMULATED",
            "coordinate_system": "WGS84", "base_map_path": "storage/fields/demo-field-a01.jpg",
            "pixel_boundary": PIXELS,
            "geo_boundary": {"type": "Polygon", "coordinates": [[to_geo(x, y) for x, y in PIXELS]]},
            "control_points": [{"pixel": p, "wgs84": to_geo(*p)} for p in control_pixels],
            "transform_params": {**TRANSFORM, "inverse": {
                "x": "(longitude-origin_longitude)/longitude_per_pixel",
                "y": "(latitude-origin_latitude)/latitude_per_pixel",
            }},
        }
        if row is None:
            row = Field(field_id=FIELD_ID, version=1, **values)
            db.add(row)
            action = "created"
        else:
            changed = any(getattr(row, key) != value for key, value in values.items())
            if changed:
                for key, value in values.items():
                    setattr(row, key, value)
                row.version += 1
                action = f"updated-to-v{row.version}"
            else:
                action = f"unchanged-v{row.version}"
        await db.commit()
        print(f"Demo field {FIELD_ID}: {action}; owner resolved from phone; simulated calibration clearly marked.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", required=True, help="已登录创建的正式手机号账号；不提供个人账号默认值")
    args = parser.parse_args()
    asyncio.run(seed(args.phone))
