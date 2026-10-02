"""Assistant contract, ownership, idempotency and provider execution regressions."""
import asyncio
import io
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.core.config import settings
from app.main import app
from app.models.assistant import AssistantConversation, AssistantDocument, AssistantEvent, AssistantMessage, AssistantRun
from app.models.field import Field
from app.models.inspection import InspectionEvent
from app.services import assistant_files, assistant_providers, assistant_service as service
from app.services.assistant_tools import ToolExecutor
from app.schemas.assistant import RunCreate
from tests.helpers import make_user

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "")
    monkeypatch.setattr(settings, "QWEATHER_API_KEY", "")
    monkeypatch.setattr(settings, "QWEATHER_PRIVATE_KEY_PATH", "")
    monkeypatch.setattr(settings, "ASSISTANT_STORAGE_ROOT", str(tmp_path / "files"))
    monkeypatch.setattr(service, "schedule", lambda *_: None)
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def setup_user(factory):
    async with factory() as db:
        owner = await make_user(db, "owner")
        other = await make_user(db, "other")
    app.dependency_overrides[get_current_user] = lambda: owner
    return owner, other


async def conversation(client):
    response = await client.post("/api/platform/assistant/conversations", json={})
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def run_body(question="总结我的巡检", key="request-0001"):
    return {"question": question, "client_request_id": key}


async def test_conversation_persistence_rename_and_owner_isolation(client, session_factory):
    owner, other = await setup_user(session_factory)
    cid = await conversation(client)
    response = await client.patch(f"/api/platform/assistant/conversations/{cid}", json={"title": "田间周报"})
    assert response.json()["data"]["title"] == "田间周报"
    assert len((await client.get("/api/platform/assistant/conversations?q=周报")).json()["data"]) == 1
    app.dependency_overrides[get_current_user] = lambda: other
    assert (await client.get(f"/api/platform/assistant/conversations/{cid}")).status_code == 404
    assert (await client.delete(f"/api/platform/assistant/conversations/{cid}")).status_code == 404
    assert (await client.get("/api/platform/assistant/conversations")).json()["data"] == []


async def test_run_idempotency_conflict_and_conversation_lock(client, session_factory):
    await setup_user(session_factory)
    cid = await conversation(client)
    route = f"/api/platform/assistant/conversations/{cid}/runs"
    first = (await client.post(route, json=run_body())).json()["data"]
    retry = (await client.post(route, json=run_body())).json()["data"]
    assert first["id"] == retry["id"]
    assert (await client.post(route, json=run_body("不同问题"))).status_code == 409
    assert (await client.post(route, json=run_body(key="request-0002"))).status_code == 409
    async with session_factory() as db:
        assert await db.scalar(select(func.count(AssistantMessage.id))) == 2


async def test_local_run_events_export_and_cancellation(client, session_factory):
    await setup_user(session_factory)
    cid = await conversation(client)
    rid = (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json=run_body())).json()["data"]["id"]
    await service.execute_run(session_factory, rid)
    run = (await client.get(f"/api/platform/assistant/runs/{rid}")).json()["data"]
    assert run["status"] == "COMPLETED"
    assert "0 次巡检" in run["message"]["content"]
    assert run["message"]["evidence"]
    detail = (await client.get(f"/api/platform/assistant/conversations/{cid}")).json()["data"]
    assert detail["messages"][-1]["run_id"] == rid
    stream = await client.get(f"/api/platform/assistant/runs/{rid}/events")
    assert "event: done" in stream.text and "event: evidence" in stream.text
    assert (await client.get(f"/api/platform/assistant/runs/{rid}/events?after=99999")).text == "retry: 1500\n\n"
    export = await client.get(f"/api/platform/assistant/runs/{rid}/export")
    assert "总结我的巡检" in export.text
    assert (await client.get(f"/api/platform/assistant/runs/{rid}/export?format=csv")).status_code == 200
    assert (await client.post(f"/api/platform/assistant/runs/{rid}/cancel")).json()["data"]["status"] == "COMPLETED"


async def test_cancel_queued_and_soft_delete_conversation(client, session_factory):
    await setup_user(session_factory)
    cid = await conversation(client)
    rid = (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json=run_body())).json()["data"]["id"]
    assert (await client.post(f"/api/platform/assistant/runs/{rid}/cancel")).json()["data"]["status"] == "CANCELLED"
    assert (await client.delete(f"/api/platform/assistant/conversations/{cid}")).status_code == 200
    async with session_factory() as db:
        assert await db.scalar(select(func.count(AssistantEvent.id))) == 0
        assert await db.scalar(select(func.count(AssistantRun.id))) == 0


async def test_run_ownership_and_input_validation(client, session_factory):
    owner, other = await setup_user(session_factory)
    cid = await conversation(client)
    assert (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json=run_body("  "))).status_code == 400
    assert (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json={**run_body(), "user_id": owner.id})).status_code == 422
    rid = (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json=run_body())).json()["data"]["id"]
    app.dependency_overrides[get_current_user] = lambda: other
    for tail in ("", "/events", "/export"):
        assert (await client.get(f"/api/platform/assistant/runs/{rid}{tail}")).status_code == 404
    assert (await client.post(f"/api/platform/assistant/runs/{rid}/cancel")).status_code == 404


async def test_private_documents_search_and_delete(client, session_factory):
    owner, other = await setup_user(session_factory)
    content = "烟草旺长期资料：先查看有效环境样本，再结合当地生育期评估。".encode()
    first = (await client.post("/api/platform/assistant/attachments", files={"file": ("我的烟草.txt", content, "text/plain")})).json()["data"]
    duplicate = (await client.post("/api/platform/assistant/attachments", files={"file": ("重复.txt", content, "text/plain")})).json()["data"]
    assert first["id"] == duplicate["id"]
    async with session_factory() as db:
        assert await assistant_files.search(db, owner.id, "烟草旺长期")
        assert not await assistant_files.search(db, other.id, "烟草旺长期")
    app.dependency_overrides[get_current_user] = lambda: other
    assert (await client.get(f"/api/platform/assistant/attachments/{first['id']}")).status_code == 404
    app.dependency_overrides[get_current_user] = lambda: owner
    assert (await client.delete(f"/api/platform/assistant/attachments/{first['id']}")).status_code == 200
    async with session_factory() as db:
        assert not await assistant_files.search(db, owner.id, "烟草旺长期")


async def test_attachment_types_and_docx(client, session_factory):
    await setup_user(session_factory)
    assert (await client.post("/api/platform/assistant/attachments", files={"file": ("fake.png", b"not an image")})).status_code == 400
    assert (await client.post("/api/platform/assistant/attachments", files={"file": ("attack.html", b"<script>1</script>")})).status_code == 400
    from docx import Document
    doc = Document()
    doc.add_paragraph("烟田文档中的巡检说明")
    buffer = io.BytesIO()
    doc.save(buffer)
    response = await client.post("/api/platform/assistant/attachments", files={"file": ("资料.docx", buffer.getvalue())})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["chunk_count"] == 1


async def test_image_consent_and_scanned_pdf(client, session_factory):
    await setup_user(session_factory)
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "green").save(buffer, format="PNG")
    aid = (await client.post("/api/platform/assistant/attachments", files={"file": ("leaf.png", buffer.getvalue())})).json()["data"]["id"]
    cid = await conversation(client)
    response = await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json={**run_body(), "attachment_ids": [aid]})
    assert response.status_code == 400
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    blank = io.BytesIO()
    writer.write(blank)
    response = await client.post("/api/platform/assistant/attachments", files={"file": ("扫描.pdf", blank.getvalue())})
    assert response.status_code == 400 and "OCR" in response.text


async def test_stale_run_recovers_without_external_retry(client, session_factory):
    await setup_user(session_factory)
    cid = await conversation(client)
    rid = (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json=run_body())).json()["data"]["id"]
    async with session_factory() as db:
        run = await db.get(AssistantRun, rid)
        run.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        await db.commit()
    detail = (await client.get(f"/api/platform/assistant/conversations/{cid}")).json()["data"]
    assert detail["active_run_id"] is None
    assert detail["messages"][-1]["status"] == "INTERRUPTED"


async def test_agent_tool_rounds_and_registered_evidence(client, session_factory, monkeypatch):
    await setup_user(session_factory)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "test-key")
    calls = []
    async def fake(messages, tools):
        calls.append(messages.copy())
        if len(calls) == 1:
            yield {"kind": "complete", "message": {"role": "assistant", "content": None,
                   "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "list_fields", "arguments": "{}"}}]}, "usage": {"total_tokens": 10}}
        else:
            yield {"kind": "delta", "text": "当前没有烟田。[E1] 错误引用[E999]"}
            yield {"kind": "complete", "message": {"role": "assistant", "content": "当前没有烟田。[E1] 错误引用[E999]"}, "usage": {"total_tokens": 20}}
    monkeypatch.setattr(assistant_providers, "model_stream", fake)
    cid = await conversation(client)
    rid = (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json=run_body("查看田块"))).json()["data"]["id"]
    await service.execute_run(session_factory, rid)
    result = (await client.get(f"/api/platform/assistant/runs/{rid}")).json()["data"]
    assert result["status"] == "COMPLETED"
    assert result["usage"]["total_tokens"] == 30
    assert "来源未核实" in result["message"]["content"]
    assert any(m["role"] == "tool" for m in calls[1])


async def test_provider_failure_keeps_partial_output(client, session_factory, monkeypatch):
    await setup_user(session_factory)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "test-key")
    async def fake(*_):
        yield {"kind": "delta", "text": "已生成的内容"}
        raise assistant_providers.ProviderError("模型暂时不可用")
    monkeypatch.setattr(assistant_providers, "model_stream", fake)
    cid = await conversation(client)
    rid = (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json=run_body())).json()["data"]["id"]
    await service.execute_run(session_factory, rid)
    result = (await client.get(f"/api/platform/assistant/runs/{rid}")).json()["data"]
    assert result["status"] == "FAILED"
    assert "已生成的内容" in result["message"]["content"]
    assert result["message"]["evidence"]


async def test_tool_permissions_unknown_args_and_disabled_network(session_factory):
    owner, other = await setup_user(session_factory)
    async with session_factory() as db:
        event = InspectionEvent(inspection_id="INS_OTHER", device_id="OTHER", owner_user_id=other.id, name="其他用户")
        db.add(event)
        await db.commit()
        executor = ToolExecutor(db, owner.id, {"web_enabled": False})
        assert "error" in await executor.execute("get_inspection_summary", '{"inspection_id":"INS_OTHER"}')
        assert "error" in await executor.execute("list_fields", '{"user_id":123}')
        assert "error" in await executor.execute("execute_sql", '{"sql":"DELETE"}')
        assert "error" in await executor.execute("search_web", '{"query":"烟草"}')
        assert "error" in await executor.execute("read_authorized_image", '{"image_id":"unknown"}')


async def test_empty_statistics_and_cross_field_comparison(session_factory):
    owner, _ = await setup_user(session_factory)
    async with session_factory() as db:
        db.add_all([InspectionEvent(inspection_id="INS_A", device_id="D", owner_user_id=owner.id, name="A", field_id="A"),
                    InspectionEvent(inspection_id="INS_B", device_id="D", owner_user_id=owner.id, name="B", field_id="B")])
        await db.commit()
        executor = ToolExecutor(db, owner.id, {})
        result = await executor.execute("get_inspection_summary", '{"inspection_id":"INS_A"}')
        assert "error" not in result, result
        assert result["data"]["environment"]["sample_count"] == 0
        assert result["data"]["environment"]["metrics"]["temperature"]["mean"] is None
        assert "error" in await executor.execute("compare_inspections", '{"first_id":"INS_A","second_id":"INS_B"}')


async def test_daily_quota(client, session_factory, monkeypatch):
    await setup_user(session_factory)
    monkeypatch.setattr(settings, "ASSISTANT_MAX_DAILY_RUNS", 0)
    cid = await conversation(client)
    assert (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json=run_body())).status_code == 429


async def test_model_fragmented_tool_stream(monkeypatch):
    packets = [
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "list_fields", "arguments": "{"}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "}"}}]}}]},
        {"choices": [], "usage": {"total_tokens": 42}},
    ]
    response_text = "\n\n".join("data: " + json.dumps(x) for x in packets) + "\n\ndata: [DONE]\n\n"
    original = httpx.AsyncClient
    def handler(request):
        body = json.loads(request.content)
        assert body["thinking"]["type"] == "disabled"
        return httpx.Response(200, text=response_text, headers={"content-type": "text/event-stream"})
    monkeypatch.setattr(assistant_providers.httpx, "AsyncClient", lambda **_: original(transport=httpx.MockTransport(handler)))
    output = [packet async for packet in assistant_providers.model_stream([{"role": "user", "content": "问题"}], [])]
    assert output[-1]["message"]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert output[-1]["usage"]["total_tokens"] == 42


async def test_capabilities_no_secret(client, session_factory):
    await setup_user(session_factory)
    response = await client.get("/api/platform/assistant/capabilities")
    assert "API_KEY" not in response.text and "PRIVATE_KEY" not in response.text
    assert response.json()["data"]["model_configured"] is False


async def test_statistics_excludes_invalid_values_and_keeps_detection_sources(session_factory):
    from app.models.inspection import (InspectionRecord, EnvironmentRecord, DetectionRecord, DetectionResult,
                                       ImageRecord, CloudDetection)
    owner, other = await setup_user(session_factory)
    async with session_factory() as db:
        event = InspectionEvent(inspection_id="INS_STATS", device_id="D", owner_user_id=owner.id, name="统计测试")
        db.add(event)
        await db.flush()
        for i, temperature in enumerate((20, 30, 999, None)):
            record = InspectionRecord(event_id=event.id, owner_user_id=owner.id, device_id="D", data_id=f"data-{i}", captured_at=service.now())
            db.add(record)
            await db.flush()
            db.add(EnvironmentRecord(inspection_id=record.id, temperature=temperature, humidity=50,
                                     valid=i != 2, sampled_at=service.now()))
            if i == 0:
                edge = DetectionRecord(inspection_id=record.id, has_target=True)
                image = ImageRecord(inspection_id=record.id, image_id="IMG_STATS", storage_key="unused.jpg")
                db.add_all([edge, image])
                await db.flush()
                db.add(DetectionResult(detection_id=edge.id, class_name="Frogeye", confidence=.9, bbox=[1, 2, 3, 4]))
                db.add(CloudDetection(image_id=image.id, inspection_id=record.id, status="completed", results=[{"class": "Mosaic"}]))
        await db.commit()
        executor = ToolExecutor(db, owner.id, {})
        result = await executor.execute("get_inspection_summary", '{"inspection_id":"INS_STATS"}')
        assert "error" not in result, result
        metrics = result["data"]["environment"]["metrics"]["temperature"]
        assert metrics["mean"] == 25 and metrics["valid_count"] == 2 and metrics["missing_count"] == 2
        assert len(result["data"]["environment"]["series"]) == 3
        assert result["data"]["detection"]["edge_classes"] == {"Frogeye": 1}
        assert result["data"]["detection"]["cloud_classes"] == {"Mosaic": 1}
        assert "error" in await ToolExecutor(db, other.id, {}).execute("get_inspection_summary", '{"inspection_id":"INS_STATS"}')


async def test_weather_partial_results_hourly_and_no_private_search(session_factory, monkeypatch):
    owner, _ = await setup_user(session_factory)
    calls = []
    async def fake(path, params):
        calls.append((path, params))
        if path.startswith("/geo/"):
            return {"location": [{"name": "北京", "lat": "39.923", "lon": "116.413"}]}
        if "/daily/" in path:
            raise assistant_providers.ProviderError("模拟无每日权限")
        return {"hours": [], "humidity": .7, "metadata": {"attributions": ["https://developer.qweather.com/attribution.html"]}}
    monkeypatch.setattr(assistant_providers, "weather_request", fake)
    async with session_factory() as db:
        db.add(InspectionEvent(inspection_id="INS_PRIVATE", device_id="D", owner_user_id=owner.id, name="私人试验三号田"))
        await db.commit()
        executor = ToolExecutor(db, owner.id, {"web_enabled": True, "question": "查看北京天气"})
        assert "error" in await executor.execute("get_weather", json.dumps({"latitude": 39.923, "longitude": 116.413, "location_name": "北京"}))
        assert "error" in await executor.execute("resolve_location", '{"query":"虚构的地区"}')
        assert "error" not in await executor.execute("resolve_location", '{"query":"北京"}')
        result = await executor.execute("get_weather", json.dumps({"latitude": 39.923, "longitude": 116.413, "location_name": "北京"}))
        assert "error" not in result, result
        assert result["data"]["forecast"] is None and "forecast" in result["data"]["errors"]
        assert any("/hourly/39.92/116.41" in path and params["hours"] == 24 for path, params in calls)
        assert result["data"]["current"]["humidity"] == .7
        for query in ("私人试验三号田的烟草", "FIELD_123的病害", "39.9234,116.4133", "13800138000烟草"):
            assert "error" in await executor.execute("search_web", json.dumps({"query": query}))


async def test_cancel_live_run_preserves_short_partial_answer(client, session_factory, monkeypatch):
    await setup_user(session_factory)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "test-key")
    entered = asyncio.Event()
    async def fake(*_):
        yield {"kind": "delta", "text": "保留未完成的回答"}
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(assistant_providers, "model_stream", fake)
    cid = await conversation(client)
    rid = (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json=run_body())).json()["data"]["id"]
    task = asyncio.create_task(service.execute_run(session_factory, rid))
    service.TASKS[rid] = task
    try:
        await asyncio.wait_for(entered.wait(), 5)
        result = await client.post(f"/api/platform/assistant/runs/{rid}/cancel")
        assert result.json()["data"]["status"] == "CANCELLED"
        detail = (await client.get(f"/api/platform/assistant/runs/{rid}")).json()["data"]
        assert detail["message"]["content"] == "保留未完成的回答"
        assert (await client.get(f"/api/platform/assistant/conversations/{cid}")).json()["data"]["active_run_id"] is None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        service.TASKS.pop(rid, None)


async def test_public_knowledge_import_is_idempotent_and_searchable(session_factory):
    from pathlib import Path
    from scripts.import_assistant_knowledge import import_manifest, validate_manifest
    owner, _ = await setup_user(session_factory)
    rows = validate_manifest(Path(__file__).resolve().parents[1] / "knowledge" / "assistant_starter.json")
    async with session_factory() as db:
        assert await import_manifest(db, rows) == (3, 0)
        assert await import_manifest(db, rows) == (0, 3)
        hits = await assistant_files.search(db, owner.id, "烟草钾肥土壤酸化")
        assert any("caas.cn" in (hit["url"] or "") for hit in hits)
        assert not any(hit["private"] for hit in hits)


async def test_frozen_migration_preserves_existing_data(tmp_path):
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine, inspect, text
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0008_agricultural_assistant.py"
    spec = importlib.util.spec_from_file_location("assistant_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, nickname TEXT)"))
        db.execute(text("INSERT INTO users VALUES (1, 'kept')"))
        migration.op = Operations(MigrationContext.configure(db))
        migration.upgrade()
        assert len([name for name in inspect(db).get_table_names() if name.startswith("assistant_")]) == 6
        assert db.scalar(text("SELECT nickname FROM users")) == "kept"
        migration.downgrade()
        assert inspect(db).get_table_names() == ["users"]
        assert db.scalar(text("SELECT nickname FROM users")) == "kept"
    engine.dispose()


async def test_timeout_preserves_short_output(client, session_factory, monkeypatch):
    await setup_user(session_factory)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ASSISTANT_RUN_TIMEOUT_SECONDS", 1)
    async def fake(*_):
        yield {"kind": "delta", "text": "已生成的短回答"}
        await asyncio.Event().wait()
    monkeypatch.setattr(assistant_providers, "model_stream", fake)
    cid = await conversation(client)
    rid = (await client.post(f"/api/platform/assistant/conversations/{cid}/runs", json=run_body())).json()["data"]["id"]
    await service.execute_run(session_factory, rid)
    result = (await client.get(f"/api/platform/assistant/runs/{rid}")).json()["data"]
    assert result["status"] == "FAILED" and "超时" in result["error"]
    assert result["message"]["content"] == "已生成的短回答"


async def test_context_ownership_and_saved_background(client, session_factory):
    owner, other = await setup_user(session_factory)
    async with session_factory() as db:
        for user in (owner, other):
            db.add(Field(field_id=f"FIELD_{user.id}", owner_user_id=user.id, name=f"烟田{user.id}",
                         pixel_boundary=[], geo_boundary={}, control_points=[], transform_params={}))
        await db.commit()
    assert (await client.post('/api/platform/assistant/conversations', json={"context":{"field_id":f"FIELD_{other.id}"}})).status_code == 403
    route = f'/api/platform/assistant/field-context/FIELD_{owner.id}'
    background = {"crop":"烟草", "variety":"试验品种", "growth_stage":"旺长期", "location":"北京"}
    assert (await client.patch(route, json=background)).status_code == 200
    assert (await client.get(route)).json()["data"] == background
    assert (await client.get(f'/api/platform/assistant/field-context/FIELD_{other.id}')).status_code == 403
    cid = await conversation(client)
    assert (await client.post(f'/api/platform/assistant/conversations/{cid}/runs', json={**run_body(), "context":{"field_id":f"FIELD_{other.id}"}})).status_code == 403
