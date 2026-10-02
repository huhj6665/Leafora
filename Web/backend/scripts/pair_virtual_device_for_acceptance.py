"""Pair TLD_JETSON_001 through the frozen dynamic-pairing HTTP flow.

This development-only helper reuses the owner of historical TLD_SIM_001 so no
formal username account or hard-coded password is introduced.  JWT and device
credentials remain process-local and are never printed.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values
from sqlalchemy import select

os.environ["DEBUG"] = "false"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models.device import Device, DeviceBinding
from app.models.user import User
from app.services.jwt_service import create_access_token

TARGET_DEVICE_ID = "TLD_JETSON_001"
LEGACY_DEVICE_ID = "TLD_SIM_001"


async def resolve_owner() -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        target = await session.scalar(
            select(Device).where(Device.device_id == TARGET_DEVICE_ID)
        )
        if target is None:
            raise RuntimeError("TLD_JETSON_001 尚未登记，请先运行 migrate_virtual_device.ps1")
        existing = await session.scalar(
            select(DeviceBinding).where(
                DeviceBinding.device_id == target.id,
                DeviceBinding.status == 1,
            )
        )
        if existing is not None:
            return existing.user_id, target.id

        legacy_owner = await session.scalar(
            select(DeviceBinding)
            .join(Device, Device.id == DeviceBinding.device_id)
            .where(
                Device.device_id == LEGACY_DEVICE_ID,
                DeviceBinding.status == 1,
            )
        )
        if legacy_owner is None:
            raise RuntimeError(
                "历史设备没有可复用的正式用户绑定；请先由手机号用户完成一次动态配对。"
            )
        return legacy_owner.user_id, target.id


async def run() -> str:
    if not settings.ENABLE_DEV_TOOLS:
        raise RuntimeError("ENABLE_DEV_TOOLS=false，拒绝运行开发验收脚本。")
    user_id, target_id = await resolve_owner()
    async with AsyncSessionLocal() as session:
        already_bound = await session.scalar(
            select(DeviceBinding).where(
                DeviceBinding.device_id == target_id,
                DeviceBinding.status == 1,
            )
        )
        user = await session.get(User, user_id)
        if user is None:
            raise RuntimeError("目标用户不存在。")
        token = create_access_token(user.id, token_version=user.token_version)
    if already_bound is not None:
        return "ALREADY_BOUND"

    mock_env = dotenv_values(WEB_ROOT / "scripts" / "mock_jetson" / ".env")
    device_secret = (mock_env.get("MOCK_DEVICE_SECRET") or "").strip()
    if not device_secret:
        raise RuntimeError("scripts/mock_jetson/.env 未配置 MOCK_DEVICE_SECRET。")
    api_base = os.environ.get("ACCEPTANCE_API_BASE_URL", "http://127.0.0.1:8000/api").rstrip("/")
    device_headers = {
        "X-Device-ID": TARGET_DEVICE_ID,
        "X-Device-Secret": device_secret,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        created = await client.post(
            f"{api_base}/device/pairing-sessions", headers=device_headers
        )
        created.raise_for_status()
        pairing = created.json()["data"]
        confirmed = await client.post(
            f"{api_base}/device/pairing/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "device_id": TARGET_DEVICE_ID,
                "pairing_session_id": pairing["pairing_session_id"],
                "pairing_token": pairing["pairing_token"],
            },
        )
        confirmed.raise_for_status()
    return "PAIRED"


def main() -> int:
    status = asyncio.run(run())
    print(f"Virtual device dynamic pairing: {status}; credentials and JWT were not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
