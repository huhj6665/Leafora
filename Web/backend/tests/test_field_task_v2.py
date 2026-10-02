"""Field, V2 task command, V1.3 live data and spatial result tests."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models.device import Device
from app.models.field import Field
from app.models.inspection import InspectionEvent
from app.models.task import TaskCommand
from app.services import inspection_service
from app.services.jwt_service import create_access_token
from tests.helpers import make_device, make_user, valid_payload

DEVICE_ID = "TLD_JETSON_001"


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def demo_field(user_id: int) -> Field:
    pixels = [[100, 100], [900, 100], [900, 700], [100, 700], [100, 100]]
    transform = {"image_width": 1000, "image_height": 800, "origin_longitude": 113.0,
                 "origin_latitude": 23.5, "longitude_per_pixel": .000001,
                 "latitude_per_pixel": -.000001}
    return Field(field_id="FIELD_A01", owner_user_id=user_id, name="演示烟田 A-01", status="READY",
                 data_source="DEMO_IMPORT", calibration_status="SIMULATED", coordinate_system="WGS84",
                 base_map_path=None, pixel_boundary=pixels,
                 geo_boundary={"type": "Polygon", "coordinates": [[[113, 23.5]]]},
                 control_points=[], transform_params=transform, version=1)


async def setup(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        device = await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        device.last_seen_at = datetime.now(timezone.utc)
        device.communication_status = "ONLINE"
        device.operating_status = "SHUTDOWN"
        db.add(demo_field(user.id))
        await db.commit()
        return user.id, create_access_token(user.id, token_version=user.token_version)


async def test_start_ack_v13_live_end_and_sync_completion(client, session_factory):
    user_id, token = await setup(session_factory)
    body = {"field_id": "FIELD_A01", "device_id": DEVICE_ID,
            "client_request_id": "START_REQ_0001", "run_mode": "FAST_TEST"}
    first = await client.post("/api/inspections/start", json=body, headers=headers(token))
    repeated = await client.post("/api/inspections/start", json=body, headers=headers(token))
    assert first.status_code == repeated.status_code == 200
    task = first.json()["data"]
    assert task["inspection_id"] == repeated.json()["data"]["inspection_id"]
    assert task["status"] == "START_REQUESTED"
    assert task["field_snapshot"]["version"] == 1
    listed = await client.get("/api/platform/events", headers=headers(token))
    assert listed.json()["data"]["items"][0]["field_name"] == "演示烟田 A-01"

    command_id = task["commands"][0]["command_id"]
    async with session_factory() as db:
        assert await db.scalar(select(func.count(TaskCommand.id))) == 1
        ack = {"type": "command_ack", "schema_version": "2.0", "device_id": DEVICE_ID,
               "command_id": command_id, "inspection_id": task["inspection_id"],
               "command": "START_INSPECTION", "status": "ACCEPTED", "phase": "RUNNING"}
        accepted = await inspection_service.ingest_ack_message(db, ack, f"tld/device/{DEVICE_ID}/ack")
        duplicate = await inspection_service.ingest_ack_message(db, ack, f"tld/device/{DEVICE_ID}/ack")
        assert accepted.status == "ack_received"
        assert duplicate.status == inspection_service.CONTROL_DUPLICATE

        payload = valid_payload(DEVICE_ID, "DATA_V13_001")
        payload.update({"schema_version": "1.3", "sequence": 0, "inspection_id": task["inspection_id"],
                        "field_id": "FIELD_A01", "field_version": 1,
                        "run_mode": "FAST_TEST", "data_provenance": "SIMULATED",
                        "flight_status": {"progress": .4, "phase": "SURVEYING"}})
        payload["location"].update({"longitude": 113.0005, "latitude": 23.4996})
        assert (await inspection_service.ingest_message(db, payload, f"tld/device/{DEVICE_ID}/data")).status == "inserted"

    live = await client.get(f"/api/devices/{DEVICE_ID}/live", headers=headers(token))
    spatial = await client.get(f"/api/inspections/{task['inspection_id']}/spatial", headers=headers(token))
    assert live.json()["data"]["raw"]["data_id"] == "DATA_V13_001"
    assert live.json()["data"]["link_state"] == "LIVE"
    assert spatial.json()["data"]["track"][0]["x"] == 500.0
    assert spatial.json()["data"]["track"][0]["x_pct"] == 50.0
    assert spatial.json()["data"]["track"][0]["y_pct"] == 50.0
    assert all("x_pct" in cell and "width_pct" in cell for cell in spatial.json()["data"]["risk_grids"])
    assert any(cell["risk_level"] == "INSUFFICIENT" for cell in spatial.json()["data"]["risk_grids"])

    ended = await client.post(f"/api/inspections/{task['inspection_id']}/end",
                              json={"client_request_id": "END_REQ_0001"}, headers=headers(token))
    assert ended.status_code == 200
    end_command = ended.json()["data"]["commands"][-1]
    async with session_factory() as db:
        device = await db.scalar(select(Device).where(Device.device_id == DEVICE_ID))
        device.pending_sync_count = 2
        device.sync_status = "PENDING"
        await db.commit()
        await inspection_service.ingest_ack_message(db, {
            "type": "command_ack", "device_id": DEVICE_ID, "command_id": end_command["command_id"],
            "inspection_id": task["inspection_id"], "command": "END_INSPECTION", "status": "ACCEPTED",
            "phase": "SYNCING", "summary": {"sampling_stopped": True, "last_data_id": "DATA_V13_001",
                "last_sequence": 0, "sample_count": 1, "pending_sync_count": 2},
        }, f"tld/device/{DEVICE_ID}/ack")
        event = await db.scalar(select(InspectionEvent).where(InspectionEvent.inspection_id == task["inspection_id"]))
        assert event.status == "SYNCING"
        await inspection_service.ingest_status_message(db, {
            "type": "device_status", "device_id": DEVICE_ID, "inspection_id": task["inspection_id"],
            "operating_status": "SHUTDOWN", "sync_status": "SYNCED", "pending_sync_count": 0,
        }, f"tld/device/{DEVICE_ID}/status")
        await db.refresh(event)
        assert event.status == "SYNCING"  # Heartbeat zero is not END evidence.
        await inspection_service.ingest_ack_message(db, {
            "device_id": DEVICE_ID, "command_id": end_command["command_id"],
            "inspection_id": task["inspection_id"], "command": "END_INSPECTION",
            "status": "COMPLETED", "phase": "COMPLETED",
            "summary": {"sampling_stopped": True, "last_data_id": "DATA_V13_001",
                "last_sequence": 0, "sample_count": 1, "pending_sync_count": 0},
        }, f"tld/device/{DEVICE_ID}/ack")
        await db.refresh(event)
        assert event.status == "COMPLETED"


async def test_start_rejects_offline_device(client, session_factory):
    user_id, token = await setup(session_factory)
    async with session_factory() as db:
        device = await db.scalar(select(Device).where(Device.device_id == DEVICE_ID))
        device.last_seen_at = datetime.now(timezone.utc) - timedelta(seconds=11)
        await db.commit()
    response = await client.post("/api/inspections/start", json={
        "field_id": "FIELD_A01", "device_id": DEVICE_ID,
        "client_request_id": "START_OFFLINE_1", "run_mode": "FAST_TEST",
    }, headers=headers(token))
    assert response.status_code == 409
    assert response.json()["data"]["device_state"] == "OFFLINE"


async def test_field_api_enforces_owner(client, session_factory):
    _, first_token = await setup(session_factory)
    async with session_factory() as db:
        second = await make_user(db, "other")
        second_token = create_access_token(second.id, token_version=second.token_version)
    assert (await client.get("/api/fields", headers=headers(first_token))).json()["data"][0]["field_id"] == "FIELD_A01"
    assert (await client.get("/api/fields/FIELD_A01", headers=headers(second_token))).status_code == 403


async def test_rejected_ack_fails_task_and_command(client, session_factory):
    _, token = await setup(session_factory)
    created = (await client.post("/api/inspections/start", json={
        "field_id": "FIELD_A01", "device_id": DEVICE_ID,
        "client_request_id": "START_REJECT_1", "run_mode": "FAST_TEST",
    }, headers=headers(token))).json()["data"]
    command_id = created["commands"][0]["command_id"]
    async with session_factory() as db:
        await inspection_service.ingest_ack_message(db, {
            "type": "command_ack", "device_id": DEVICE_ID, "command_id": command_id,
            "inspection_id": created["inspection_id"], "command": "START_INSPECTION",
            "status": "REJECTED", "reason_code": "FIELD_UNAVAILABLE",
        }, f"tld/device/{DEVICE_ID}/ack")
    status = (await client.get(f"/api/inspections/{created['inspection_id']}/status",
                               headers=headers(token))).json()["data"]
    assert status["status"] == "FAILED"
    assert status["commands"][0]["status"] == "REJECTED"


async def test_command_timeout_is_reported_on_status_poll(client, session_factory):
    _, token = await setup(session_factory)
    created = (await client.post("/api/inspections/start", json={
        "field_id": "FIELD_A01", "device_id": DEVICE_ID,
        "client_request_id": "START_TIMEOUT_1", "run_mode": "FAST_TEST",
    }, headers=headers(token))).json()["data"]
    async with session_factory() as db:
        command = await db.scalar(select(TaskCommand).where(TaskCommand.command_id == created["commands"][0]["command_id"]))
        command.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    status = (await client.get(f"/api/inspections/{created['inspection_id']}/status",
                               headers=headers(token))).json()["data"]
    assert status["status"] == "FAILED"
    assert status["commands"][0]["status"] == "EXPIRED"
