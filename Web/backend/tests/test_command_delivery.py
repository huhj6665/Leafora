from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models.inspection import InspectionEvent
from app.models.task import TaskCommand
from app.schemas.task import InspectionStart
from app.services import command_delivery, inspection_service, mqtt_publisher, task_service
from app.core.config import settings
from tests.test_field_task_v2 import DEVICE_ID, setup


async def test_failed_publish_and_restart_retry_reuse_ids(session_factory, monkeypatch):
    user_id, _ = await setup(session_factory)
    published = []

    async def publish(device_id, payload):
        published.append(dict(payload))
        return len(published) > 1

    monkeypatch.setattr(mqtt_publisher, "publish_downlink", publish)
    body = InspectionStart(field_id="FIELD_A01", device_id=DEVICE_ID,
                           client_request_id="reliable-start-1", run_mode="FAST_TEST")
    async with session_factory() as db:
        first = await task_service.start_inspection(db, user_id, body)
        repeated = await task_service.start_inspection(db, user_id, body)
        assert first["inspection_id"] == repeated["inspection_id"]
        assert len(published) == 1  # bounded backoff even for repeated HTTP requests

    async with session_factory() as db:
        command = await db.scalar(select(TaskCommand))
        command.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        await command_delivery.retry_due_commands(db)
        await db.refresh(command)
        assert command.status == "DELIVERED"
        assert command.retry_count == 1
        assert published[0] == published[1]
        assert await db.scalar(select(func.count(InspectionEvent.id))) == 1

        # Lost device ACK after a successful publish also retries the same command.
        command.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        await task_service.start_inspection(db, user_id, body)
        assert published[2] == published[0]


async def test_fast_ack_is_not_overwritten_and_stops_retry(session_factory, monkeypatch):
    user_id, _ = await setup(session_factory)
    calls = 0

    async def publish(device_id, payload):
        nonlocal calls
        calls += 1
        async with session_factory() as ack_db:
            ack = {"device_id": device_id, "command_id": payload["command_id"],
                   "inspection_id": payload["inspection_id"], "command": payload["command"],
                   "status": "ACCEPTED", "phase": "RUNNING"}
            await inspection_service.ingest_ack_message(ack_db, ack, f"tld/device/{device_id}/ack")
        return True

    monkeypatch.setattr(mqtt_publisher, "publish_downlink", publish)
    async with session_factory() as db:
        result = await task_service.start_inspection(db, user_id, InspectionStart(
            field_id="FIELD_A01", device_id=DEVICE_ID, client_request_id="fast-ack-start-1",
            run_mode="FAST_TEST",
        ))
        assert result["status"] == "RUNNING"
        assert result["commands"][0]["status"] == "ACCEPTED"
        await command_delivery.retry_due_commands(db, datetime.now(timezone.utc) + timedelta(seconds=40))
        assert calls == 1


async def test_retry_budget_expiry_and_terminal_stop(session_factory, monkeypatch):
    user_id, _ = await setup(session_factory)
    calls = []

    async def unavailable(device_id, payload):
        calls.append(payload)
        return False

    monkeypatch.setattr(mqtt_publisher, "publish_downlink", unavailable)
    monkeypatch.setattr(settings, "MQTT_COMMAND_MAX_ATTEMPTS", 2)
    async with session_factory() as db:
        await task_service.start_inspection(db, user_id, InspectionStart(
            field_id="FIELD_A01", device_id=DEVICE_ID, client_request_id="retry-budget", run_mode="FAST_TEST",
        ))
        command = await db.scalar(select(TaskCommand))
        command.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        await command_delivery.retry_due_commands(db)
        await db.refresh(command)
        command.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        await command_delivery.retry_due_commands(db)
        assert len(calls) == 2
        command.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        await command_delivery.retry_due_commands(db)
        await db.refresh(command)
        assert command.status == "EXPIRED"
        await command_delivery.retry_due_commands(db)
        assert len(calls) == 2


async def test_final_evidence_first_does_not_expire_or_republish(session_factory, monkeypatch):
    from tests.test_communication_reliability import end_ack, end_task, running_task
    user_id, task = await running_task(session_factory)
    calls = []

    async def publish(device_id, payload):
        calls.append(payload)
        return True

    async with session_factory() as db:
        command_id = await end_task(db, user_id, task)
        await inspection_service.ingest_ack_message(db, end_ack(task, command_id, "COMPLETED"),
                                                     f"tld/device/{DEVICE_ID}/ack")
        command = await db.scalar(select(TaskCommand).where(TaskCommand.command_id == command_id))
        command.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        monkeypatch.setattr(mqtt_publisher, "publish_downlink", publish)
        await command_delivery.retry_due_commands(db)
        await db.refresh(command)
        assert command.status == "PENDING" and calls == []
        await inspection_service.ingest_ack_message(db, end_ack(task, command_id, "ACCEPTED"),
                                                     f"tld/device/{DEVICE_ID}/ack")
        await db.refresh(command)
        assert command.status == "COMPLETED"


async def test_end_failed_publish_same_request_redelivers_same_command(session_factory, monkeypatch):
    from tests.test_communication_reliability import end_ack, running_task
    user_id, task = await running_task(session_factory)
    published = []

    async def publish(device_id, payload):
        published.append(payload)
        return len(published) > 1

    monkeypatch.setattr(mqtt_publisher, "publish_downlink", publish)
    async with session_factory() as db:
        first = await task_service.end_inspection(db, user_id, task["inspection_id"], "END_FIXED_REQUEST")
        command_id = first["commands"][-1]["command_id"]
        repeat = await task_service.end_inspection(db, user_id, task["inspection_id"], "END_FIXED_REQUEST")
        assert repeat["commands"][-1]["command_id"] == command_id and len(published) == 1
        command = await db.scalar(select(TaskCommand).where(TaskCommand.command_id == command_id))
        command.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        await task_service.end_inspection(db, user_id, task["inspection_id"], "END_FIXED_REQUEST")
        assert published[0] == published[1]
        assert await db.scalar(select(func.count(InspectionEvent.id))) == 1
        await inspection_service.ingest_ack_message(db, end_ack(task, command_id, "ACCEPTED"),
                                                     f"tld/device/{DEVICE_ID}/ack")
        await command_delivery.retry_due_commands(db, datetime.now(timezone.utc) + timedelta(seconds=40))
        assert len(published) == 2
