"""设备管理业务服务.

当前为简单实现（设备绑定/解绑），未来接入真实 Jetson 设备、
二维码扫码绑定等能力时在此扩展。
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError
from app.models.device import Device, DeviceBinding
from app.models.inspection import DeviceStatusRecord, InspectionEvent, InspectionRecord
from app.models.protocol import DevicePairingSession
from app.services import mqtt_publisher
from app.services.protocol_tokens import new_token, token_hash, token_matches
from app.services.task_service import standard_device_state

PAIRING_TTL_SECONDS = 300
PAIRING_MAX_ATTEMPTS = 5


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def list_user_devices(db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    """返回用户当前已绑定的设备列表."""
    result = await db.execute(
        select(DeviceBinding, Device)
        .join(Device, Device.id == DeviceBinding.device_id)
        .where(DeviceBinding.user_id == user_id, DeviceBinding.status == 1)
    )
    devices: list[dict[str, Any]] = []
    for binding, device in result.all():
        readiness = device.last_status_payload or {}
        latest = (await db.execute(
            select(DeviceStatusRecord, InspectionRecord.captured_at)
            .join(InspectionRecord, InspectionRecord.id == DeviceStatusRecord.inspection_id)
            .where(InspectionRecord.device_id == device.device_id, InspectionRecord.owner_user_id == user_id)
            .order_by(InspectionRecord.captured_at.desc()).limit(1)
        )).first()
        inspection_count = await db.scalar(
            select(func.count(InspectionRecord.id)).where(
                InspectionRecord.device_id == device.device_id,
                InspectionRecord.owner_user_id == user_id,
            )
        ) or 0
        current_event = await db.scalar(
            select(InspectionEvent).where(
                InspectionEvent.device_id == device.device_id,
                InspectionEvent.owner_user_id == user_id,
                InspectionEvent.status.in_((
                    "START_REQUESTED", "STARTING", "RUNNING", "RUNNING_OFFLINE", "ENDING", "SYNCING",
                )),
            ).order_by(InspectionEvent.created_at.desc())
        )
        last_seen = device.last_seen_at
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        is_online = bool(last_seen and last_seen >= datetime.now(timezone.utc) - timedelta(seconds=10))
        devices.append(
            {
                "id": device.id,
                "device_id": device.device_id,
                "device_name": device.device_name,
                "status": device.status,
                "operating_status": "DISABLED" if device.status == 0 else device.operating_status,
                "communication_status": "ONLINE" if is_online else "OFFLINE",
                "standard_state": standard_device_state(device),
                "gps_fix": readiness.get("gps_fix"),
                "rtk_status": readiness.get("rtk_status"),
                "camera_status": readiness.get("camera_status"),
                "inference_status": readiness.get("inference_status"),
                "last_seen_at": device.last_seen_at,
                "cpu_temperature": latest[0].temperature if latest else None,
                "cpu_usage": latest[0].cpu_usage if latest else None,
                "memory_usage": latest[0].memory_usage if latest else None,
                "storage_usage": readiness.get("storage_usage", latest[0].storage_usage if latest else None),
                "network_status": latest[0].network_status if latest else None,
                "inspection_count": inspection_count,
                "sync_status": device.sync_status,
                "pending_sync_count": device.pending_sync_count,
                "current_inspection_id": current_event.inspection_id if current_event else None,
                "current_inspection_name": current_event.name if current_event else None,
                "current_inspection_status": current_event.status if current_event else None,
                "bind_time": binding.bind_time,
            }
        )
    return devices


async def bind_device(db: AsyncSession, user_id: int, device_code: str) -> dict[str, Any]:
    """将设备绑定到用户.

    参数:
        device_code: 设备编号（如 TLD001），非数据库自增主键。
    """
    device = await db.scalar(
        select(Device).where(Device.device_id == device_code)
    )
    if device is None:
        raise NotFoundError("设备不存在")

    # 检查设备是否已被绑定（部分唯一索引同样兜底）
    active = await db.scalar(
        select(DeviceBinding).where(
            DeviceBinding.device_id == device.id,
            DeviceBinding.status == 1,
        )
    )
    if active is not None:
        # 已绑定到当前用户：幂等返回，不重复创建绑定记录
        if active.user_id == user_id:
            return {"device_id": device.device_id, "bound": True, "already_bound": True}
        # 绑定到其他用户：拒绝覆盖归属，不做自动转绑
        raise BusinessError("设备已被其他用户绑定", code=409, status_code=409)

    binding = DeviceBinding(
        user_id=user_id,
        device_id=device.id,
        status=1,
        bind_time=datetime.now(timezone.utc),
    )
    db.add(binding)
    await db.commit()
    return {"device_id": device.device_id, "bound": True, "already_bound": False}


async def unbind_device(
    db: AsyncSession, user_id: int, device_code: str
) -> dict[str, Any]:
    """解绑用户与设备."""
    device = await db.scalar(
        select(Device).where(Device.device_id == device_code)
    )
    if device is None:
        raise NotFoundError("设备不存在")

    binding = await db.scalar(
        select(DeviceBinding).where(
            DeviceBinding.device_id == device.id,
            DeviceBinding.user_id == user_id,
            DeviceBinding.status == 1,
        )
    )
    if binding is None:
        raise BusinessError("设备未绑定到当前用户")

    active_event = await db.scalar(select(InspectionEvent).where(
        InspectionEvent.device_id == device.device_id,
        InspectionEvent.owner_user_id == user_id,
        InspectionEvent.status.in_((
            "START_REQUESTED", "STARTING", "RUNNING", "RUNNING_OFFLINE", "ENDING", "SYNCING",
        )),
    ))
    if active_event is not None:
        raise BusinessError("设备仍有关联中的巡检任务，暂不能解除绑定", code=409, status_code=409)
    if device.pending_sync_count > 0:
        raise BusinessError("设备仍有待同步数据，暂不能解除绑定", code=409, status_code=409)

    binding.status = 0
    binding.unbind_time = datetime.now(timezone.utc)
    await db.commit()
    return {"device_id": device.device_id, "bound": False}


async def create_pairing_session(db: AsyncSession, device: Device) -> dict[str, Any]:
    """Create a new short-lived pairing token; only its digest is persisted."""
    now = datetime.now(timezone.utc)
    # A device displays only one live QR. Invalidating older sessions also makes
    # screenshots safe after a refresh.
    rows = (await db.execute(
        select(DevicePairingSession).where(
            DevicePairingSession.device_pk == device.id,
            DevicePairingSession.status == "PENDING",
        )
    )).scalars().all()
    for old in rows:
        old.status = "CANCELLED"
    plain = new_token()
    session_id = f"PAIR_{new_token()[:24]}"
    expires_at = now + timedelta(seconds=PAIRING_TTL_SECONDS)
    db.add(DevicePairingSession(
        pairing_session_id=session_id,
        device_pk=device.id,
        token_hash=token_hash(plain),
        expires_at=expires_at,
    ))
    await db.commit()
    return {
        "pairing_session_id": session_id,
        "pairing_token": plain,
        "device_id": device.device_id,
        "expires_at": _iso(expires_at),
    }


async def get_pairing_status(
    db: AsyncSession, device: Device, pairing_session_id: str
) -> dict[str, Any]:
    row = await db.scalar(select(DevicePairingSession).where(
        DevicePairingSession.pairing_session_id == pairing_session_id,
        DevicePairingSession.device_pk == device.id,
    ))
    if row is None:
        raise NotFoundError("配对会话不存在")
    if row.status == "PENDING" and _aware(row.expires_at) <= datetime.now(timezone.utc):
        row.status = "EXPIRED"
        await db.commit()
    return {
        "pairing_session_id": row.pairing_session_id,
        "device_id": device.device_id,
        "status": row.status,
        "expires_at": _iso(row.expires_at),
        "consumed_at": _iso(row.consumed_at),
    }


async def confirm_pairing(
    db: AsyncSession, user_id: int, session_id: str, plain_token: str, device_id: str
) -> dict[str, Any]:
    """Atomically validate, bind and consume a pairing session."""
    row = await db.scalar(
        select(DevicePairingSession)
        .where(DevicePairingSession.pairing_session_id == session_id)
        .with_for_update()
    )
    if row is None:
        raise NotFoundError("配对会话不存在")
    device = await db.get(Device, row.device_pk)
    if device is None or device.device_id != device_id or device.status != 1:
        raise BusinessError("设备与配对会话不匹配", code=409, status_code=409)
    now = datetime.now(timezone.utc)
    if row.status == "PENDING" and _aware(row.expires_at) <= now:
        row.status = "EXPIRED"
        await db.commit()
    if row.status != "PENDING":
        raise BusinessError(f"配对会话状态为 {row.status}", code=409, status_code=409)
    if not token_matches(plain_token, row.token_hash):
        row.attempts += 1
        if row.attempts >= PAIRING_MAX_ATTEMPTS:
            row.status = "CANCELLED"
        await db.commit()
        raise BusinessError("配对凭证无效", code=401, status_code=401)

    active = await db.scalar(select(DeviceBinding).where(
        DeviceBinding.device_id == device.id, DeviceBinding.status == 1
    ).with_for_update())
    already_bound = active is not None and active.user_id == user_id
    if active is not None and not already_bound:
        raise BusinessError("设备已被其他用户绑定", code=409, status_code=409)
    if active is None:
        db.add(DeviceBinding(user_id=user_id, device_id=device.id, status=1, bind_time=now))
    row.status = "CONFIRMED"
    row.confirmed_user_id = user_id
    row.consumed_at = now
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise BusinessError("配对会话已被消费或设备已绑定", code=409, status_code=409) from exc

    payload = {
        "type": "pairing_result", "event": "PAIRING_CONFIRMED",
        "pairing_session_id": session_id, "device_id": device.device_id,
        "status": "CONFIRMED", "cloud_time": _iso(now),
    }
    await mqtt_publisher.publish_downlink(device.device_id, payload)
    return {"device_id": device.device_id, "bound": True, "already_bound": already_bound, "status": "CONFIRMED"}
