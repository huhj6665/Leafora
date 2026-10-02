"""V2.0 mini-program task control and Web read APIs."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.task import InspectionEnd, InspectionStart
from app.services import task_service
from app.utils.response import ok

router = APIRouter(tags=["巡检任务 V2"])


@router.post("/inspections/start")
async def start(body: InspectionStart, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await task_service.start_inspection(db, user.id, body))


@router.post("/inspections/{inspection_id}/end")
async def end(inspection_id: str, body: InspectionEnd, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await task_service.end_inspection(db, user.id, inspection_id, body.client_request_id))


@router.get("/inspections/current")
async def current(device_id: Optional[str] = Query(None), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await task_service.current_inspection(db, user.id, device_id))


@router.get("/inspections/history")
async def history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await task_service.list_history(db, user.id))


@router.get("/inspections/{inspection_id}")
async def detail(inspection_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await task_service.get_inspection(db, user.id, inspection_id))


@router.get("/inspections/{inspection_id}/status")
async def status(inspection_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await task_service.get_inspection(db, user.id, inspection_id))


@router.get("/inspections/{inspection_id}/spatial")
async def spatial(inspection_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await task_service.spatial_result(db, user.id, inspection_id))


@router.get("/inspections/{inspection_id}/live")
async def inspection_live(inspection_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await task_service.live_by_inspection(db, user.id, inspection_id))


@router.get("/devices/{device_id}/live")
async def device_live(device_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await task_service.live_by_device(db, user.id, device_id))
