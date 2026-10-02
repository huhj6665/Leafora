"""Hardware nulls and durable, task-scoped V0.3 END evidence."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.device import Device
from app.models.inspection import EnvironmentRecord, InspectionEvent, LocationRecord
from app.models.task import TaskCommand
from app.schemas.task import InspectionStart
from app.services import analysis_service, event_service, inspection_service, map_service, task_service
from tests.helpers import valid_payload
from tests.test_field_task_v2 import DEVICE_ID, setup

ACK_TOPIC = f"tld/device/{DEVICE_ID}/ack"
STATUS_TOPIC = f"tld/device/{DEVICE_ID}/status"
DATA_TOPIC = f"tld/device/{DEVICE_ID}/data"


async def running_task(factory):
    user_id, _ = await setup(factory)
    async with factory() as db:
        task = await task_service.start_inspection(db, user_id, InspectionStart(
            field_id="FIELD_A01", device_id=DEVICE_ID, client_request_id="reliability-start",
            run_mode="FAST_TEST",
        ))
        await inspection_service.ingest_ack_message(db, {
            "device_id": DEVICE_ID, "command_id": task["commands"][0]["command_id"],
            "command": "START_INSPECTION", "inspection_id": task["inspection_id"], "status": "ACCEPTED",
        }, ACK_TOPIC)
    return user_id, task


def sample(task, index, **extra):
    payload = valid_payload(DEVICE_ID, f"DATA_RELIABLE_{index}")
    payload.update(inspection_id=task["inspection_id"], sequence=index, schema_version="1.3",
                   field_id="FIELD_A01", field_version=1, run_mode="REAL_DEVICE", data_provenance="DEVICE",
                   timestamp=f"2026-10-01T08:00:{index:02d}Z", **extra)
    payload["location"].update(longitude=113.0005, latitude=23.4996)
    return payload


async def end_task(db, user_id, task):
    ended = await task_service.end_inspection(db, user_id, task["inspection_id"], "reliable-end")
    return ended["commands"][-1]["command_id"]


def end_ack(task, command_id, stage, count=0, last=None, pending=0):
    return {"device_id": DEVICE_ID, "command_id": command_id, "inspection_id": task["inspection_id"],
            "command": "END_INSPECTION", "status": stage,
            "phase": "SYNCING" if stage == "ACCEPTED" else "COMPLETED",
            "summary": {"sampling_stopped": True, "last_data_id": f"DATA_RELIABLE_{last}" if count else None,
                        "last_sequence": last if count else None, "sample_count": count,
                        "pending_sync_count": pending}}


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2", "1.3"])
async def test_hardware_null_storage_raw_live_stats_and_spatial(session_factory, version):
    user_id, task = await running_task(session_factory)
    async with session_factory() as db:
        payload = sample(task, 0)
        payload["schema_version"] = version
        payload["location"].update(latitude=None, longitude=None, position_valid=False)
        payload["environment"].update(temperature=None, humidity=None, co2=None, light=None,
                                      sampled_at=None, valid=False)
        assert (await inspection_service.ingest_message(db, payload, DATA_TOPIC)).status == "inserted"
        loc = await db.scalar(select(LocationRecord))
        env = await db.scalar(select(EnvironmentRecord))
        assert loc.latitude is loc.longitude is env.sampled_at is env.temperature is None
        full = await inspection_service.get_inspection_full(db, user_id, payload["data_id"])
        assert full["environment"]["sampled_at"] is None
        live = await task_service.live_by_inspection(db, user_id, task["inspection_id"])
        assert live["raw"] == payload
        assert live["display"]["environment"]["temperature"] is None
        spatial = await task_service.spatial_result(db, user_id, task["inspection_id"])
        assert spatial["track"] == spatial["disease_points"] == []
        mapped = await map_service.get_map_data(db, user_id, task["inspection_id"])
        assert mapped["tracks"] == mapped["disease_points"] == []
        detail = await event_service.get_event_detail(db, user_id, task["inspection_id"])
        assert detail["environment_summary"]["valid_count"] == 0
        assert (await analysis_service.overview(db, user_id))["environment_trends"] == []


@pytest.mark.parametrize("block,changes", [
    ("location", {"latitude": None}), ("location", {"longitude": float("nan")}),
    ("location", {"latitude": 91}), ("environment", {"sampled_at": None}),
    ("environment", {"sampled_at": "not-a-date"}),
    ("environment", {"temperature": float("inf")}),
])
async def test_inconsistent_valid_hardware_block_rejected(session_factory, block, changes):
    _, task = await running_task(session_factory)
    async with session_factory() as db:
        payload = sample(task, 0)
        payload[block].update(changes)
        assert (await inspection_service.ingest_message(db, payload, DATA_TOPIC)).status == "invalid_schema"


async def test_live_unknown_not_filled_from_previous_or_other_task(session_factory):
    user_id, task = await running_task(session_factory)
    async with session_factory() as db:
        await inspection_service.ingest_message(db, sample(task, 0), DATA_TOPIC)
        unknown = sample(task, 1)
        unknown["environment"].update(temperature=None, co2=None, valid=False)
        await inspection_service.ingest_message(db, unknown, DATA_TOPIC)
        live = await task_service.live_by_device(db, user_id, DEVICE_ID)
        assert live["display"]["environment"]["temperature"] is None
        assert live["display"]["environment"]["humidity"] == unknown["environment"]["humidity"]
        # Late replay of an older sample must not overwrite the newer live JSON.
        older = sample(task, 2)
        older["timestamp"] = "2026-10-01T07:00:00Z"
        await inspection_service.ingest_message(db, older, DATA_TOPIC)
        assert (await task_service.live_by_device(db, user_id, DEVICE_ID))["raw"] == unknown
        other = InspectionEvent(inspection_id="INS_OTHER", device_id=DEVICE_ID,
                                owner_user_id=user_id, name="other", status="RUNNING")
        db.add(other)
        await db.commit()
        other_payload = sample({"inspection_id": other.inspection_id}, 3)
        await inspection_service.ingest_message(db, other_payload, DATA_TOPIC)
        assert (await task_service.live_by_inspection(db, user_id, task["inspection_id"]))["raw"] == unknown


async def test_end_old_zero_and_legacy_control_cannot_complete_v2(session_factory):
    user_id, task = await running_task(session_factory)
    async with session_factory() as db:
        command_id = await end_task(db, user_id, task)
        legacy_ack = end_ack(task, command_id, "ACCEPTED")
        del legacy_ack["summary"]
        await inspection_service.ingest_ack_message(db, legacy_ack, ACK_TOPIC)
        await inspection_service.ingest_status_message(db, {
            "device_id": DEVICE_ID, "inspection_id": task["inspection_id"],
            "sync_status": "SYNCED", "pending_sync_count": 0,
        }, STATUS_TOPIC)
        state = await task_service.get_inspection(db, user_id, task["inspection_id"])
        assert state["status"] == "SYNCING" and state["sync_status"] == "PENDING"
        result = await inspection_service.ingest_control_message(db, {
            "type": "inspection_control", "device_id": DEVICE_ID,
            "inspection_id": task["inspection_id"], "command": "END",
        }, f"tld/device/{DEVICE_ID}/control")
        assert result.status == "control_invalid_transition"


async def test_final_first_restart_gap_and_late_data_complete(session_factory):
    user_id, task = await running_task(session_factory)
    async with session_factory() as db:
        command_id = await end_task(db, user_id, task)
        final = end_ack(task, command_id, "COMPLETED", 3, 2)
        await inspection_service.ingest_ack_message(db, final, ACK_TOPIC)
        state = await task_service.get_inspection(db, user_id, task["inspection_id"])
        assert state["status"] == "ENDING"
        assert state["commands"][-1]["status"] == "PENDING"
    # A new session represents process recovery from persisted ACK evidence.
    async with session_factory() as db:
        accepted = end_ack(task, command_id, "ACCEPTED", 3, 2, pending=3)
        await inspection_service.ingest_ack_message(db, accepted, ACK_TOPIC)
        await inspection_service.ingest_message(db, sample(task, 2), DATA_TOPIC)
        await inspection_service.ingest_message(db, sample(task, 0), DATA_TOPIC)
        assert (await task_service.get_inspection(db, user_id, task["inspection_id"]))["status"] == "SYNCING"
        # A different task's zero status is not evidence for this one.
        await inspection_service.ingest_status_message(db, {
            "device_id": DEVICE_ID, "inspection_id": "INS_OTHER",
            "sync_status": "SYNCED", "pending_sync_count": 0,
        }, STATUS_TOPIC)
        await inspection_service.ingest_message(db, sample(task, 1), DATA_TOPIC)
        state = await task_service.get_inspection(db, user_id, task["inspection_id"])
        assert state["status"] == "COMPLETED" and state["commands"][-1]["status"] == "COMPLETED"
        for ack in (accepted, final, {**accepted, "status": "REJECTED"}):
            assert (await inspection_service.ingest_ack_message(db, ack, ACK_TOPIC)).status == "control_duplicate"
        await inspection_service.ingest_status_message(db, {
            "device_id": DEVICE_ID, "inspection_id": task["inspection_id"],
            "sync_status": "PENDING", "pending_sync_count": 8, "operating_status": "RUNNING",
        }, STATUS_TOPIC)
        state = await task_service.get_inspection(db, user_id, task["inspection_id"])
        assert state["status"] == "COMPLETED" and state["pending_sync_count"] == 0


async def test_zero_samples_requires_both_proofs_and_rejects_mismatch(session_factory):
    user_id, task = await running_task(session_factory)
    async with session_factory() as db:
        command_id = await end_task(db, user_id, task)
        accepted = end_ack(task, command_id, "ACCEPTED")
        wrong = {**accepted, "inspection_id": "INS_WRONG"}
        assert (await inspection_service.ingest_ack_message(db, wrong, ACK_TOPIC)).status == "device_mismatch"
        wrong = {**accepted, "command": "START_INSPECTION"}
        assert (await inspection_service.ingest_ack_message(db, wrong, ACK_TOPIC)).status == "device_mismatch"
        await inspection_service.ingest_ack_message(db, accepted, ACK_TOPIC)
        assert (await task_service.get_inspection(db, user_id, task["inspection_id"]))["status"] == "SYNCING"
        conflict = end_ack(task, command_id, "COMPLETED", 1, 0)
        assert (await inspection_service.ingest_ack_message(db, conflict, ACK_TOPIC)).status == "invalid_schema"
        await inspection_service.ingest_ack_message(db, end_ack(task, command_id, "COMPLETED"), ACK_TOPIC)
        assert (await task_service.get_inspection(db, user_id, task["inspection_id"]))["status"] == "COMPLETED"


async def test_null_hardware_samples_still_count_for_end_proof(session_factory):
    user_id, task = await running_task(session_factory)
    async with session_factory() as db:
        payload = sample(task, 0)
        payload["location"].update(latitude=None, longitude=None, position_valid=False)
        payload["environment"].update(sampled_at=None, valid=False)
        await inspection_service.ingest_message(db, payload, DATA_TOPIC)
        command_id = await end_task(db, user_id, task)
        for status in ("ACCEPTED", "COMPLETED"):
            await inspection_service.ingest_ack_message(db, end_ack(task, command_id, status, 1, 0), ACK_TOPIC)
        assert (await task_service.get_inspection(db, user_id, task["inspection_id"]))["status"] == "COMPLETED"


def test_real_device_readiness_checks_modules_and_gps():
    device = Device(device_id="TLD_SIM_002", status=1, last_seen_at=datetime.now(timezone.utc),
                    communication_status="ONLINE", operating_status="SHUTDOWN", pending_sync_count=0,
                    sync_status="IDLE", last_status_payload={})
    assert task_service.standard_device_state(device) == "ONLINE_NOT_READY"
    device.last_status_payload = {"gps_fix": "GPS_FIX", "camera_status": "READY", "inference_status": "READY"}
    assert task_service.standard_device_state(device) == "READY"
    device.last_status_payload["camera_status"] = "ERROR"
    assert task_service.standard_device_state(device) == "ERROR"
    device.last_status_payload.update(camera_status="READY", gps_fix="NO_FIX")
    assert task_service.standard_device_state(device) == "ONLINE_NOT_READY"
    device.communication_status = "OFFLINE"
    assert task_service.standard_device_state(device) == "OFFLINE"


async def test_old_heartbeat_cannot_revert_ready_modules(session_factory):
    await setup(session_factory)
    async with session_factory() as db:
        status = {"device_id": DEVICE_ID, "timestamp": "2026-10-01T08:00:02Z",
                  "operating_status": "STARTUP", "camera_status": "ERROR"}
        await inspection_service.ingest_status_message(db, status, STATUS_TOPIC)
        old = {**status, "timestamp": "2026-10-01T08:00:01Z", "operating_status": "SHUTDOWN", "camera_status": "READY"}
        assert (await inspection_service.ingest_status_message(db, old, STATUS_TOPIC)).status == "control_duplicate"
        device = await db.scalar(select(Device).where(Device.device_id == DEVICE_ID))
        assert task_service.standard_device_state(device) == "ERROR"


async def test_real_coordinates_never_use_simulated_field_calibration(session_factory):
    user_id, task = await running_task(session_factory)
    async with session_factory() as db:
        payload = sample(task, 0)
        await inspection_service.ingest_message(db, payload, DATA_TOPIC)
        spatial = await task_service.spatial_result(db, user_id, task["inspection_id"])
        assert spatial["field"]["calibration_status"] == "SIMULATED"
        assert spatial["track"] == spatial["disease_points"] == []
        assert all(cell["valid_sample_count"] == 0 for cell in spatial["risk_grids"])
        # Valid physical WGS84 remains queryable, not erased or relabelled.
        geographic = await map_service.get_map_data(db, user_id, task["inspection_id"])
        assert geographic["tracks"][0]["points"][0]["lng"] == payload["location"]["longitude"]
        assert (await task_service.live_by_inspection(db, user_id, task["inspection_id"]))["raw"] == payload
