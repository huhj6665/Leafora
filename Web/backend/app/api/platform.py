"""V1.0 产品化平台 API：事件、GIS、分析与 AI 助手。"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.inspection_event import AssistantQuestion, InspectionEventCreate, InspectionEventStatusUpdate
from app.services import ai_service, analysis_service, event_service, map_service
from app.utils.response import ok

router = APIRouter(prefix="/platform", tags=["智能巡检平台"])


@router.post("/events", summary="创建巡检事件")
async def create_event(
    body: InspectionEventCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await event_service.create_event(db, user.id, body.device_id, body.name, body.location_name))


@router.get("/events", summary="巡检事件列表")
async def list_events(
    status: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await event_service.list_events(db, user.id, status, device_id, page, page_size))


@router.get("/events/{inspection_id}", summary="巡检事件详情")
async def event_detail(
    inspection_id: str,
    include_series: bool = Query(True, description="保留旧轨迹/环境序列；详情首屏可关闭以减小响应"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await event_service.get_event_detail(db, user.id, inspection_id, include_series=include_series))


@router.patch("/events/{inspection_id}/status", summary="推进巡检事件状态")
async def event_status(
    inspection_id: str,
    body: InspectionEventStatusUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await event_service.update_status(db, user.id, inspection_id, body.status, body.failure_reason))


@router.get("/map", summary="GIS 巡检图层")
async def map_data(
    inspection_id: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await map_service.get_map_data(db, user.id, inspection_id))


@router.get("/analysis/overview", summary="分析总览")
async def analysis_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await analysis_service.overview(db, user.id))


@router.post("/assistant/ask", summary="智能助手问答")
async def assistant_ask(
    body: AssistantQuestion,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 只把结构化分析摘要传给 AI；AIService 不接触 db。
    context = await analysis_service.overview(db, user.id)
    if body.inspection_id:
        context["event"] = await event_service.get_event_detail(db, user.id, body.inspection_id)
        context["event"].pop("images", None)
        context["event"].pop("track", None)
    return ok(await ai_service.answer(body.question, context))
