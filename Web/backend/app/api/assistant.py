"""JWT-only Web assistant APIs; independent of task control endpoints."""
import asyncio
import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError
from app.database.assistant import get_assistant_db as get_db, engine
from app.models.assistant import (AssistantConversation, AssistantDocument, AssistantEvent,
                                  AssistantFieldContext, AssistantMessage, AssistantRun)
from app.models.user import User
from app.schemas.assistant import ConversationCreate, ConversationUpdate, FieldContextUpdate, RunCreate
from app.services import assistant_files, assistant_providers, assistant_service as service, field_service
from app.utils.response import ok

router = APIRouter(prefix="/platform/assistant", tags=["农业助手"])


async def shutdown():
    tasks = list(service.TASKS.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await engine.dispose()


@router.get("/capabilities")
async def capabilities(user: User = Depends(get_current_user)):
    return ok(assistant_providers.capabilities())


@router.get("/conversations")
async def conversations(q: str = Query("", max_length=100), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AssistantConversation).where(
        AssistantConversation.owner_user_id == user.id, AssistantConversation.title.contains(q))
        .order_by(AssistantConversation.updated_at.desc()).limit(100))).scalars().all()
    return ok([service.conversation_dict(row) for row in rows])


@router.post("/conversations")
async def create_conversation(body: ConversationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    context = body.context.model_dump()
    await service.validate_context(db, user.id, context)
    row = AssistantConversation(id=service.identifier("CON_"), owner_user_id=user.id,
                                title=body.title, context=context)
    db.add(row)
    await db.commit()
    return ok(service.conversation_dict(row))


@router.get("/conversations/{cid}")
async def conversation_detail(cid: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await service.detail(db, user.id, cid))


@router.patch("/conversations/{cid}")
async def update_conversation(cid: str, body: ConversationUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await service.owned_conversation(db, user.id, cid)
    if body.context is not None:
        await service.validate_context(db, user.id, body.context.model_dump())
        if row.active_run_id:
            raise ConflictError("请等待当前回答完成后再切换分析对象")
        row.context = body.context.model_dump()
    if body.title is not None:
        row.title = body.title
    row.updated_at = service.now()
    await db.commit()
    await db.refresh(row)
    return ok(service.conversation_dict(row))


@router.delete("/conversations/{cid}")
async def delete_conversation(cid: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await service.owned_conversation(db, user.id, cid)
    if row.active_run_id:
        await service.cancel(db, user.id, row.active_run_id)
    # Explicit child deletion also works on SQLite without FK pragma; no business tables touched.
    run_ids = select(AssistantRun.id).where(AssistantRun.conversation_id == cid)
    await db.execute(delete(AssistantEvent).where(AssistantEvent.run_id.in_(run_ids)))
    await db.execute(delete(AssistantRun).where(AssistantRun.conversation_id == cid))
    await db.execute(delete(AssistantMessage).where(AssistantMessage.conversation_id == cid))
    await db.delete(row)
    await db.commit()
    return ok({"deleted": True})


@router.post("/conversations/{cid}/runs")
async def create_run(cid: str, body: RunCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result, created = await service.create_run(db, user.id, cid, body)
    if created:
        service.schedule(async_sessionmaker(db.bind, expire_on_commit=False, autoflush=False), result["id"])
    return ok(result)


@router.get("/runs/{rid}")
async def run_detail(rid: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    run = await service.owned_run(db, user.id, rid)
    conversation = await service.owned_conversation(db, user.id, run.conversation_id)
    await service.recover_stale(db, conversation)
    await db.refresh(run)
    message = await db.get(AssistantMessage, run.assistant_message_id)
    return ok({"id": rid, "status": run.status, "error": run.error, "model": run.model,
               "usage": run.usage, "message": service.message_dict(message)})


@router.post("/runs/{rid}/cancel")
async def cancel_run(rid: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await service.cancel(db, user.id, rid))


@router.get("/runs/{rid}/events")
async def events(rid: str, after: int = Query(0, ge=0), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    run = await service.owned_run(db, user.id, rid)
    conversation = await service.owned_conversation(db, user.id, run.conversation_id)
    await service.recover_stale(db, conversation)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    uid = user.id
    await db.commit()

    async def stream():
        sequence, quiet = after, 0
        yield "retry: 1500\n\n"
        while True:
            async with factory() as session:
                current = await session.scalar(select(AssistantRun).where(AssistantRun.id == rid, AssistantRun.owner_user_id == uid))
                if current is None:
                    return
                conv = await session.get(AssistantConversation, current.conversation_id)
                if conv:
                    await service.recover_stale(session, conv)
                    await session.refresh(current)
                rows = (await session.execute(select(AssistantEvent).where(AssistantEvent.run_id == rid,
                                 AssistantEvent.sequence > sequence).order_by(AssistantEvent.sequence).limit(100))).scalars().all()
                terminal = current.status in service.TERMINAL
            for event in rows:
                sequence = event.sequence
                yield f"id: {sequence}\nevent: {event.kind}\ndata: {json.dumps(event.payload, ensure_ascii=False)}\n\n"
            if terminal and len(rows) < 100:
                return
            quiet = 0 if rows else quiet + 1
            if quiet >= 20:
                yield ": heartbeat\n\n"
                quiet = 0
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})


@router.get("/attachments")
async def attachments(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AssistantDocument).where(AssistantDocument.owner_user_id == user.id,
             AssistantDocument.deleted_at.is_(None)).order_by(AssistantDocument.created_at.desc()).limit(100))).scalars().all()
    return ok([assistant_files.document_dict(r) for r in rows])


@router.post("/attachments")
async def upload(file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = await file.read(20 * 1024 * 1024 + 1)
    await file.close()
    return ok(await assistant_files.save_attachment(db, user.id, file.filename or "attachment", data))


@router.get("/attachments/{aid}")
async def attachment(aid: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await assistant_files.owned_document(db, user.id, aid)
    return FileResponse(assistant_files.path_for(row.storage_key), media_type=row.mime_type, filename=row.title)


@router.delete("/attachments/{aid}")
async def delete_attachment(aid: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await assistant_files.owned_document(db, user.id, aid)
    row.deleted_at = service.now()
    await db.commit()
    return ok({"deleted": True, "recoverable": True})


@router.get("/field-context/{field_id}")
async def field_context(field_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await field_service.owned_field(db, user.id, field_id)
    row = await db.scalar(select(AssistantFieldContext).where(AssistantFieldContext.owner_user_id == user.id,
                                                           AssistantFieldContext.field_id == field_id))
    return ok(row.context if row else FieldContextUpdate().model_dump())


@router.patch("/field-context/{field_id}")
async def update_field_context(field_id: str, body: FieldContextUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await field_service.owned_field(db, user.id, field_id)
    row = await db.scalar(select(AssistantFieldContext).where(AssistantFieldContext.owner_user_id == user.id,
                                                           AssistantFieldContext.field_id == field_id))
    if not row:
        row = AssistantFieldContext(owner_user_id=user.id, field_id=field_id)
        db.add(row)
    row.context = body.model_dump()
    await db.commit()
    return ok(row.context)


@router.get("/runs/{rid}/export")
async def export(rid: str, format: str = Query("md", pattern="^(md|csv)$"), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    run = await service.owned_run(db, user.id, rid)
    message = await db.get(AssistantMessage, run.assistant_message_id)
    question = await db.get(AssistantMessage, run.user_message_id)
    if format == "md":
        content = f"# Leafora 分析记录\n\n问题：{question.content}\n\n{message.content}\n\n## 来源\n\n"
        content += "\n".join(f"- [{e['id']}] {e['title']} · {e['retrieved_at']}" + (f" · {e['url']}" if e.get("url") else "") for e in message.evidence)
        media = "text/markdown; charset=utf-8"
    else:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["来源编号", "来源标题", "查询时间", "字段", "值"])
        def safe(value):
            value = str(value)
            return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
        def flatten(value, prefix=""):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield from flatten(item, f"{prefix}.{key}" if prefix else key)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    yield from flatten(item, f"{prefix}[{i}]")
            else:
                yield prefix, value
        for e in message.evidence:
            for key, value in flatten(e.get("data")):
                writer.writerow([safe(x) for x in (e["id"], e["title"], e["retrieved_at"], key, value)])
        content, media = "\ufeff" + out.getvalue(), "text/csv; charset=utf-8"
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="leafora-{rid}.{format}"'})
