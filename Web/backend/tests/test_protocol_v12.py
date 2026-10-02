"""Protocol V1.2 authentication, pairing, QR login and ACK regression tests."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.protocol import DeviceControlRequest, DevicePairingSession, WebLoginSession
from app.models.inspection import InspectionEvent
from app.services import inspection_service
from app.services.sms import get_sms_provider
from tests.helpers import make_device, make_user, valid_payload

PHONE = "13800002222"
DEVICE_ID = "TLD_JETSON_001"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def device_headers() -> dict[str, str]:
    return {"X-Device-ID": DEVICE_ID, "X-Device-Secret": "dev-secret"}


async def phone_login(client, phone: str = PHONE) -> dict:
    await client.post("/api/auth/send-phone-code", json={"phone": phone})
    code = get_sms_provider().get_code(phone)
    response = await client.post("/api/auth/login-phone", json={"phone": phone, "code": code})
    assert response.status_code == 200
    return response.json()["data"]


async def test_phone_password_set_login_and_reset(client):
    login = await phone_login(client)
    await client.post("/api/auth/phone-password/send-code", json={"phone": PHONE})
    code = get_sms_provider().get_code(PHONE)
    set_result = await client.post(
        "/api/auth/phone-password/set",
        json={"phone": PHONE, "code": code, "new_password": "leafora123"},
        headers=auth(login["access_token"]),
    )
    assert set_result.status_code == 200
    password_login = await client.post(
        "/api/auth/login-phone-password", json={"phone": PHONE, "password": "leafora123"}
    )
    assert password_login.status_code == 200

    await client.post("/api/auth/phone-password/send-code", json={"phone": PHONE})
    reset_code = get_sms_provider().get_code(PHONE)
    reset = await client.post(
        "/api/auth/phone-password/reset",
        json={"phone": PHONE, "code": reset_code, "new_password": "newleaf456"},
    )
    assert reset.status_code == 200
    old = await client.post("/api/auth/login-phone-password", json={"phone": PHONE, "password": "leafora123"})
    new = await client.post("/api/auth/login-phone-password", json={"phone": PHONE, "password": "newleaf456"})
    assert old.status_code == 401
    assert new.status_code == 200


async def test_dynamic_pairing_success_single_use_and_hash_only(client, session_factory):
    async with session_factory() as db:
        await make_device(db, device_id=DEVICE_ID)
    login = await phone_login(client)
    created = await client.post("/api/device/pairing-sessions", headers=device_headers())
    assert created.status_code == 200
    pairing = created.json()["data"]
    async with session_factory() as db:
        row = await db.scalar(select(DevicePairingSession))
        assert row.token_hash != pairing["pairing_token"]
        assert len(row.token_hash) == 64

    body = {
        "pairing_session_id": pairing["pairing_session_id"],
        "pairing_token": pairing["pairing_token"],
        "device_id": DEVICE_ID,
    }
    confirmed = await client.post("/api/device/pairing/confirm", json=body, headers=auth(login["access_token"]))
    repeated = await client.post("/api/device/pairing/confirm", json=body, headers=auth(login["access_token"]))
    status = await client.get(
        f"/api/device/pairing-sessions/{pairing['pairing_session_id']}", headers=device_headers()
    )
    assert confirmed.status_code == 200
    assert repeated.status_code == 409
    assert status.json()["data"]["status"] == "CONFIRMED"


async def test_pairing_expired_and_wrong_device_are_rejected(client, session_factory):
    async with session_factory() as db:
        await make_device(db, device_id=DEVICE_ID)
    login = await phone_login(client)
    pairing = (await client.post("/api/device/pairing-sessions", headers=device_headers())).json()["data"]
    async with session_factory() as db:
        row = await db.scalar(select(DevicePairingSession))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    body = {"pairing_session_id": pairing["pairing_session_id"], "pairing_token": pairing["pairing_token"], "device_id": DEVICE_ID}
    assert (await client.post("/api/device/pairing/confirm", json=body, headers=auth(login["access_token"]))).status_code == 409


async def test_pairing_concurrent_consumers_only_one_wins(client, session_factory):
    async with session_factory() as db:
        await make_device(db, device_id=DEVICE_ID)
    first_user = await phone_login(client, "13800003331")
    second_user = await phone_login(client, "13800003332")
    pairing = (await client.post("/api/device/pairing-sessions", headers=device_headers())).json()["data"]
    body = {"pairing_session_id": pairing["pairing_session_id"], "pairing_token": pairing["pairing_token"], "device_id": DEVICE_ID}
    results = await asyncio.gather(
        client.post("/api/device/pairing/confirm", json=body, headers=auth(first_user["access_token"])),
        client.post("/api/device/pairing/confirm", json=body, headers=auth(second_user["access_token"])),
    )
    assert sorted(response.status_code for response in results) == [200, 409]


async def test_web_qr_login_one_time_and_cross_session_attack(client):
    login = await phone_login(client)
    first = (await client.post("/api/auth/qr-sessions")).json()["data"]
    second = (await client.post("/api/auth/qr-sessions")).json()["data"]
    attack = await client.post(
        f"/api/auth/qr-sessions/{first['login_session_id']}/confirm",
        json={"scan_token": second["scan_token"]}, headers=auth(login["access_token"]),
    )
    assert attack.status_code == 401
    confirmed = await client.post(
        f"/api/auth/qr-sessions/{first['login_session_id']}/confirm",
        json={"scan_token": first["scan_token"]}, headers=auth(login["access_token"]),
    )
    assert confirmed.status_code == 200
    exchanged = await client.get(
        f"/api/auth/qr-sessions/{first['login_session_id']}", params={"poll_token": first["poll_token"]}
    )
    replay = await client.get(
        f"/api/auth/qr-sessions/{first['login_session_id']}", params={"poll_token": first["poll_token"]}
    )
    assert exchanged.json()["data"]["access_token"]
    assert replay.json()["data"]["status"] == "CONSUMED"
    assert "access_token" not in replay.json()["data"]


async def test_web_qr_expiry_cancel_and_poll_token_isolation(client, session_factory):
    expired = (await client.post("/api/auth/qr-sessions")).json()["data"]
    async with session_factory() as db:
        row = await db.scalar(select(WebLoginSession).where(WebLoginSession.login_session_id == expired["login_session_id"]))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    polled = await client.get(
        f"/api/auth/qr-sessions/{expired['login_session_id']}", params={"poll_token": expired["poll_token"]}
    )
    assert polled.json()["data"]["status"] == "EXPIRED"

    cancellable = (await client.post("/api/auth/qr-sessions")).json()["data"]
    wrong = await client.get(
        f"/api/auth/qr-sessions/{cancellable['login_session_id']}", params={"poll_token": expired["poll_token"]}
    )
    assert wrong.status_code == 401
    cancelled = await client.delete(
        f"/api/auth/qr-sessions/{cancellable['login_session_id']}", params={"poll_token": cancellable["poll_token"]}
    )
    assert cancelled.json()["data"]["status"] == "CANCELLED"


async def test_start_request_id_ack_is_idempotent(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        payload = {
            "type": "inspection_control", "schema_version": "1.1",
            "request_id": "REQ_ACK_001", "command": "START",
            "inspection_id": "INS_ACK_001", "device_id": DEVICE_ID,
            "timestamp": "2026-09-27T08:00:00Z",
        }
        first = await inspection_service.ingest_control_message(db, payload, f"tld/device/{DEVICE_ID}/control")
        second = await inspection_service.ingest_control_message(db, payload, f"tld/device/{DEVICE_ID}/control")
        rows = (await db.execute(select(DeviceControlRequest))).scalars().all()
        assert first.status == inspection_service.CONTROL_STARTED
        assert second.status == inspection_service.CONTROL_DUPLICATE
        assert len(rows) == 1
        assert rows[0].ack_payload["status"] == "ACCEPTED"


async def test_end_enters_syncing_until_status_reports_empty_queue(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        base = {"type": "inspection_control", "schema_version": "1.1", "inspection_id": "INS_SYNC_001", "device_id": DEVICE_ID, "timestamp": "2026-09-27T08:00:00Z"}
        await inspection_service.ingest_control_message(
            db, {**base, "request_id": "REQ_SYNC_START", "command": "START"},
            f"tld/device/{DEVICE_ID}/control",
        )
        ended = await inspection_service.ingest_control_message(
            db, {**base, "request_id": "REQ_SYNC_END", "command": "END", "pending_sync_count": 3},
            f"tld/device/{DEVICE_ID}/control",
        )
        assert ended.status == inspection_service.CONTROL_COMPLETED
        status = await inspection_service.ingest_status_message(
            db,
            {"type": "device_status", "device_id": DEVICE_ID, "inspection_id": "INS_SYNC_001", "sync_status": "SYNCED", "pending_sync_count": 0},
            f"tld/device/{DEVICE_ID}/status",
        )
        assert status.status == "status_updated"
        event = await db.scalar(select(InspectionEvent).where(InspectionEvent.inspection_id == "INS_SYNC_001"))
        assert event.status == "COMPLETED"
        assert event.pending_sync_count == 0
        ack = await inspection_service.ingest_ack_message(
            db,
            {"type": "command_ack", "device_id": DEVICE_ID, "command_id": "CMD_001", "status": "APPLIED"},
            f"tld/device/{DEVICE_ID}/ack",
        )
        assert ack.status == "ack_received"


async def test_v12_nullable_hardware_fields_and_sequence(session_factory):
    async with session_factory() as db:
        user = await make_user(db)
        await make_device(db, device_id=DEVICE_ID, owner_user_id=user.id)
        payload = valid_payload(DEVICE_ID)
        payload["schema_version"] = "1.2"
        payload["sequence"] = 7
        payload["location"].update({"height_ellipsoid_m": None, "horizontal_accuracy_m": None, "correction_age_s": None, "sampled_at": payload["timestamp"]})
        payload["environment"].update({"temperature": None, "co2": None, "valid": False})
        payload["detection"]["sampled_at"] = payload["timestamp"]
        payload["device_status"].update({"cpu_usage": None, "temperature": None})
        result = await inspection_service.ingest_message(db, payload, f"tld/device/{DEVICE_ID}/data")
        assert result.status == inspection_service.INGEST_INSERTED
        full = await inspection_service.get_inspection_full(db, user.id, payload["data_id"])
        assert full["sequence"] == 7
        assert full["environment"]["temperature"] is None
        assert full["environment"]["valid"] is False
