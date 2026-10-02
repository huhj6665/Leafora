"""产品化 V1.0：巡检事件、地图与分析接口测试。"""
from tests.helpers import make_device, valid_payload
from app.services import inspection_service

DEVICE_ID = "TLD_PLATFORM_001"


async def _account(client, username: str):
    await client.post("/api/auth/register", json={"username": username, "password": "secret123"})
    login = await client.post("/api/auth/login", json={"username": username, "password": "secret123"})
    return login.json()["data"]


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


async def test_event_lifecycle_ingest_map_and_analysis(client, session_factory):
    async with session_factory() as db:
        await make_device(db, device_id=DEVICE_ID)
    account = await _account(client, "platform_owner")
    headers = _auth(account["access_token"])
    assert (await client.post("/api/device/bind", json={"device_id": DEVICE_ID}, headers=headers)).status_code == 200

    created = await client.post(
        "/api/platform/events",
        json={"device_id": DEVICE_ID, "name": "北区巡检", "location_name": "A3 地块"},
        headers=headers,
    )
    assert created.status_code == 200
    event = created.json()["data"]
    assert event["status"] == "CREATED"
    inspection_id = event["inspection_id"]

    started = await client.patch(
        f"/api/platform/events/{inspection_id}/status",
        json={"status": "RUNNING"}, headers=headers,
    )
    assert started.status_code == 200

    payload = valid_payload(device_id=DEVICE_ID)
    payload["inspection_id"] = inspection_id
    async with session_factory() as db:
        result = await inspection_service.ingest_message(db, payload, f"tld/device/{DEVICE_ID}/data")
        assert result.ok

    detail = await client.get(f"/api/platform/events/{inspection_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["sample_count"] == 1
    assert len(body["track"]) == 1
    assert body["risk"]["target_count"] == 1
    assert body["environment_summary"] == {
        "temperature": 26.5, "humidity": 48.2, "co2": 420.0, "light": 356.0,
        "sampled_at": "2026-09-22T05:30:20Z", "valid_count": 1,
    }

    compact = await client.get(
        f"/api/platform/events/{inspection_id}?include_series=false", headers=headers
    )
    assert compact.status_code == 200
    assert compact.json()["data"]["track"] == []
    assert compact.json()["data"]["environment"] == []
    assert compact.json()["data"]["environment_summary"]["temperature"] == 26.5

    map_result = await client.get("/api/platform/map", headers=headers)
    assert map_result.status_code == 200
    assert len(map_result.json()["data"]["tracks"]) == 1
    assert map_result.json()["data"]["sampling"] == "douglas-peucker"

    analysis = await client.get("/api/platform/analysis/overview", headers=headers)
    assert analysis.status_code == 200
    assert analysis.json()["data"]["metrics"]["samples"] == 1

    completed = await client.patch(
        f"/api/platform/events/{inspection_id}/status",
        json={"status": "COMPLETED"}, headers=headers,
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["status"] == "COMPLETED"


async def test_event_access_isolation_and_transition_guard(client, session_factory):
    async with session_factory() as db:
        await make_device(db, device_id=DEVICE_ID)
    owner = await _account(client, "platform_owner_2")
    other = await _account(client, "platform_other")
    owner_headers = _auth(owner["access_token"])
    await client.post("/api/device/bind", json={"device_id": DEVICE_ID}, headers=owner_headers)
    event = (await client.post(
        "/api/platform/events", json={"device_id": DEVICE_ID, "name": "权限巡检"}, headers=owner_headers
    )).json()["data"]

    forbidden = await client.get(
        f"/api/platform/events/{event['inspection_id']}", headers=_auth(other["access_token"])
    )
    assert forbidden.status_code == 403

    invalid = await client.patch(
        f"/api/platform/events/{event['inspection_id']}/status",
        json={"status": "COMPLETED"}, headers=owner_headers,
    )
    assert invalid.status_code == 409


async def test_assistant_uses_structured_fallback(client):
    account = await _account(client, "assistant_user")
    response = await client.post(
        "/api/platform/assistant/ask",
        json={"question": "我应该先看什么？"},
        headers=_auth(account["access_token"]),
    )
    assert response.status_code == 200
    assert response.json()["data"]["provider"] == "local"
    assert "巡检" in response.json()["data"]["answer"]
