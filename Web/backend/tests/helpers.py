"""测试共享辅助函数：构建用户/设备/巡检记录与合法 MQTT V1.0 payload."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, DeviceBinding
from app.models.user import User


def valid_payload(device_id: str = "TLD_SIM_001", data_id: str | None = None) -> dict:
    """构造一份合法 TLD MQTT V1.0 payload."""
    data_id = data_id or uuid.uuid4().hex
    return {
        "schema_version": "1.0",
        "device_id": device_id,
        "data_id": data_id,
        "timestamp": "2026-09-22T05:30:22.000Z",
        "location": {
            "latitude": 39.12345678,
            "longitude": 117.12345678,
            "altitude_msl_m": 25.5,
            "height_ellipsoid_m": 42.1,
            "fix_quality": 4,
            "rtk_status": "FIXED",
            "satellites_used": 22,
            "horizontal_accuracy_m": 0.018,
            "vertical_accuracy_m": 0.031,
            "ground_speed_mps": 2.35,
            "course_over_ground_deg": 135.6,
            "correction_age_s": 1.2,
            "position_valid": True,
        },
        "environment": {
            "temperature": 26.5,
            "humidity": 48.2,
            "co2": 420,
            "light": 356,
            "sampled_at": "2026-09-22T05:30:20.000Z",
        },
        "detection": {
            "has_target": True,
            "results": [
                {"class": "Frogeye", "confidence": 0.93, "bbox": [120, 80, 250, 300]}
            ],
        },
        "device_status": {
            "cpu_usage": 35,
            "memory_usage": 42,
            "temperature": 55,
        },
    }


async def make_user(session: AsyncSession, nickname: str = "dev_user") -> User:
    user = User(nickname=nickname, status=1)
    session.add(user)
    await session.flush()
    await session.commit()
    return user


async def make_device(
    session: AsyncSession,
    device_id: str = "TLD_SIM_001",
    device_name: str = "TLD Simulator",
    owner_user_id: int | None = None,
) -> Device:
    device = Device(
        device_id=device_id, device_name=device_name, device_secret="dev-secret", status=1
    )
    session.add(device)
    await session.flush()
    if owner_user_id is not None:
        session.add(DeviceBinding(user_id=owner_user_id, device_id=device.id, status=1))
    await session.commit()
    return device
