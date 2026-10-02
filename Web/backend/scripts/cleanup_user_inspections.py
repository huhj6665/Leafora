"""Scoped, repeatable inspection cleanup with a mandatory local JSON snapshot."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.database.session import AsyncSessionLocal
from app.models.identity import IdentityType, UserIdentity
from app.models.inspection import ImageRecord, InspectionEvent, InspectionRecord
from app.models.protocol import DeviceControlRequest
from app.models.task import TaskCommand


async def run(phone: str, execute: bool) -> None:
    async with AsyncSessionLocal() as db:
        identity = await db.scalar(select(UserIdentity).where(
            UserIdentity.identity_type == IdentityType.PHONE.value,
            UserIdentity.identifier == phone,
        ))
        if identity is None:
            raise RuntimeError("目标手机号账号不存在，未执行任何清理。")
        user_id = identity.user_id
        events = (await db.execute(select(InspectionEvent).where(
            InspectionEvent.owner_user_id == user_id
        ))).scalars().all()
        event_ids = [row.id for row in events]
        inspection_ids = [row.inspection_id for row in events]
        records = (await db.execute(select(InspectionRecord).where(
            InspectionRecord.owner_user_id == user_id
        ))).scalars().all()
        record_ids = [row.id for row in records]
        images = (await db.execute(select(ImageRecord).where(
            ImageRecord.inspection_id.in_(record_ids)
        ))).scalars().all() if record_ids else []
        command_count = await db.scalar(select(func.count(TaskCommand.id)).where(
            TaskCommand.inspection_pk.in_(event_ids)
        )) if event_ids else 0
        legacy_count = await db.scalar(select(func.count(DeviceControlRequest.id)).where(
            DeviceControlRequest.inspection_id.in_(inspection_ids)
        )) if inspection_ids else 0
        counts = {"events": len(events), "records": len(records), "images": len(images),
                  "task_commands": int(command_count or 0), "legacy_control_acks": int(legacy_count or 0)}
        print(json.dumps({"mode": "execute" if execute else "dry-run", "phone": phone, "counts": counts}, ensure_ascii=False))
        if not execute:
            print("Dry-run only; no database rows or files were changed.")
            return

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = WEB_ROOT / "local" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"inspection-cleanup-{phone}-{stamp}.json"
        backup = {
            "created_at": datetime.now(timezone.utc).isoformat(), "phone": phone, "user_id": user_id,
            "counts": counts,
            "events": [{"inspection_id": row.inspection_id, "device_id": row.device_id,
                        "field_id": row.field_id, "field_version": row.field_version,
                        "status": row.status, "field_snapshot": row.field_snapshot} for row in events],
            "records": [{"data_id": row.data_id, "device_id": row.device_id,
                         "inspection_event_id": row.event_id, "schema_version": row.schema_version,
                         "raw_payload": row.raw_payload} for row in records],
            "images": [{"image_id": row.image_id, "storage_key": row.storage_key} for row in images],
        }
        temporary = backup_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(backup, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(backup_path)

        if event_ids:
            await db.execute(delete(TaskCommand).where(TaskCommand.inspection_pk.in_(event_ids)))
        if inspection_ids:
            await db.execute(delete(DeviceControlRequest).where(DeviceControlRequest.inspection_id.in_(inspection_ids)))
        if record_ids:
            await db.execute(delete(InspectionRecord).where(InspectionRecord.id.in_(record_ids)))
        if event_ids:
            await db.execute(delete(InspectionEvent).where(InspectionEvent.id.in_(event_ids)))
        await db.commit()

        storage_root = (BACKEND_ROOT / "storage").resolve()
        deleted_files = 0
        for image in images:
            path = (storage_root / image.storage_key).resolve()
            if storage_root in path.parents and path.is_file():
                path.unlink()
                deleted_files += 1
        print(json.dumps({"backup": str(backup_path), "deleted_files": deleted_files,
                          "preserved": ["user", "identities", "devices", "bindings", "fields"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", required=True, help="明确指定需要清理的账号；默认仅预览")
    parser.add_argument("--execute", action="store_true", help="执行清理；省略时仅 dry-run")
    args = parser.parse_args()
    asyncio.run(run(args.phone, args.execute))
