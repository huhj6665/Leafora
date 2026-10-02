"""Read-only database verification for one virtual-device inspection."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy import distinct, func, select

os.environ["DEBUG"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import AsyncSessionLocal
from app.models.inspection import CloudDetection, ImageRecord, InspectionEvent, InspectionRecord
from app.models.protocol import DeviceControlRequest


async def verify(inspection_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        event = await session.scalar(
            select(InspectionEvent).where(InspectionEvent.inspection_id == inspection_id)
        )
        if event is None:
            raise RuntimeError(f"巡检事件不存在：{inspection_id}")
        record_count = int(
            await session.scalar(
                select(func.count()).select_from(InspectionRecord).where(
                    InspectionRecord.event_id == event.id
                )
            )
            or 0
        )
        unique_data_count = int(
            await session.scalar(
                select(func.count(distinct(InspectionRecord.data_id))).where(
                    InspectionRecord.event_id == event.id
                )
            )
            or 0
        )
        image_count = int(
            await session.scalar(
                select(func.count())
                .select_from(ImageRecord)
                .join(InspectionRecord, InspectionRecord.id == ImageRecord.inspection_id)
                .where(InspectionRecord.event_id == event.id)
            )
            or 0
        )
        completed_detection_count = int(
            await session.scalar(
                select(func.count())
                .select_from(CloudDetection)
                .join(InspectionRecord, InspectionRecord.id == CloudDetection.inspection_id)
                .where(
                    InspectionRecord.event_id == event.id,
                    CloudDetection.status == "completed",
                )
            )
            or 0
        )
        controls = (
            await session.execute(
                select(DeviceControlRequest.command, DeviceControlRequest.request_id).where(
                    DeviceControlRequest.inspection_id == inspection_id
                )
            )
        ).all()
        return {
            "inspection_id": inspection_id,
            "device_id": event.device_id,
            "status": event.status,
            "sync_status": event.sync_status,
            "pending_sync_count": event.pending_sync_count,
            "record_count": record_count,
            "unique_data_count": unique_data_count,
            "duplicate_data_count": record_count - unique_data_count,
            "image_count": image_count,
            "cloud_completed_count": completed_detection_count,
            "control_commands": sorted(row.command for row in controls),
            "unique_control_request_count": len({row.request_id for row in controls}),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="只读核验虚拟巡检的数据库闭环")
    parser.add_argument("inspection_id")
    parser.add_argument("--expected-samples", type=int, default=0)
    parser.add_argument("--expected-images", type=int, default=0)
    args = parser.parse_args()
    result = asyncio.run(verify(args.inspection_id))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    ok = (
        result["status"] == "COMPLETED"
        and result["pending_sync_count"] == 0
        and result["duplicate_data_count"] == 0
        and result["record_count"] >= args.expected_samples
        and result["image_count"] >= args.expected_images
        and result["control_commands"] == ["END", "START"]
        and result["unique_control_request_count"] == 2
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
