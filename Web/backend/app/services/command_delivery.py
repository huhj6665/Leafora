"""Persisted, bounded command delivery shared by HTTP and the existing consumer."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.device import Device
from app.models.inspection import InspectionEvent
from app.models.task import TaskCommand
from app.services import mqtt_publisher

RETRYABLE = {"PENDING", "DELIVERED"}
TERMINAL_EVENTS = {"COMPLETED", "FAILED", "CANCELLED"}


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def expire_command(db: AsyncSession, command_id: int, now=None) -> bool:
    now = now or datetime.now(timezone.utc)
    result = await db.execute(update(TaskCommand).where(
        TaskCommand.id == command_id, TaskCommand.status.in_(RETRYABLE),
        TaskCommand.expires_at <= now, TaskCommand.final_ack_payload.is_(None),
    ).values(status="EXPIRED", failure_reason="设备未在命令有效期内确认")
      .execution_options(synchronize_session=False))
    if result.rowcount:
        command = await db.get(TaskCommand, command_id, populate_existing=True)
        await db.execute(update(InspectionEvent).where(
            InspectionEvent.id == command.inspection_pk,
            InspectionEvent.status.not_in(TERMINAL_EVENTS),
        ).values(status="FAILED", failure_reason=command.failure_reason, ended_at=now))
    await db.commit()
    return bool(result.rowcount)


async def dispatch_command(db: AsyncSession, command_id: int, now=None) -> bool:
    """Claim before publishing; crashes and PUBACK/ACK races reuse the same IDs."""
    now = now or datetime.now(timezone.utc)
    command = await db.get(TaskCommand, command_id, populate_existing=True)
    if command is None or command.status not in RETRYABLE or command.final_ack_payload is not None:
        await db.rollback()
        return False
    if aware(command.expires_at) <= now:
        await expire_command(db, command_id, now)
        return False
    event = await db.get(InspectionEvent, command.inspection_pk, populate_existing=True)
    if event is None or event.status in TERMINAL_EVENTS:
        await db.execute(update(TaskCommand).where(
            TaskCommand.id == command_id, TaskCommand.status.in_(RETRYABLE),
        ).values(status="CANCELLED"))
        await db.commit()
        return False
    attempts = command.delivery_attempts
    delay = min(settings.MQTT_COMMAND_RETRY_MAX_SECONDS,
                settings.MQTT_COMMAND_RETRY_BASE_SECONDS * 2 ** min(attempts, 10))
    # A lease longer than the publisher's PUBACK wait also excludes concurrent
    # HTTP and worker claims. If a process dies, the persisted lease expires.
    next_attempt = now + timedelta(seconds=max(15, delay))
    claimed = await db.execute(update(TaskCommand).where(
        TaskCommand.id == command_id, TaskCommand.status.in_(RETRYABLE),
        TaskCommand.final_ack_payload.is_(None),
        TaskCommand.expires_at > now,
        TaskCommand.delivery_attempts == attempts,
        TaskCommand.delivery_attempts < settings.MQTT_COMMAND_MAX_ATTEMPTS,
        or_(TaskCommand.next_attempt_at.is_(None), TaskCommand.next_attempt_at <= now),
    ).values(delivery_attempts=attempts + 1, retry_count=attempts,
             next_attempt_at=next_attempt).execution_options(synchronize_session=False))
    payload = dict(command.payload)
    device = await db.get(Device, command.device_pk)
    device_id = device.device_id if device else None
    await db.commit()
    if not claimed.rowcount or device_id is None:
        return False
    published = await mqtt_publisher.publish_downlink(device_id, payload)
    if published:
        result = await db.execute(update(TaskCommand).where(
            TaskCommand.id == command_id, TaskCommand.status == "PENDING",
        ).values(status="DELIVERED", delivered_at=now))
        if result.rowcount and command.command_type == "START_INSPECTION":
            await db.execute(update(InspectionEvent).where(
                InspectionEvent.id == command.inspection_pk,
                InspectionEvent.status == "START_REQUESTED",
            ).values(status="STARTING"))
        await db.commit()
    return published


async def retry_due_commands(db: AsyncSession, now=None) -> int:
    now = now or datetime.now(timezone.utc)
    ids = (await db.execute(select(TaskCommand.id).where(
        TaskCommand.status.in_(RETRYABLE),
        TaskCommand.final_ack_payload.is_(None),
        or_(TaskCommand.expires_at <= now, and_(
            TaskCommand.delivery_attempts < settings.MQTT_COMMAND_MAX_ATTEMPTS,
            or_(TaskCommand.next_attempt_at.is_(None), TaskCommand.next_attempt_at <= now),
        )),
    ).order_by(TaskCommand.created_at).limit(20))).scalars().all()
    await db.rollback()
    for command_id in ids:
        await dispatch_command(db, command_id, now)
    return len(ids)
