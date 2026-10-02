"""Authenticated field management API."""
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database.session import get_db
from app.models.user import User
from app.schemas.field import FieldCreate, FieldUpdate
from app.services import field_service
from app.utils.response import ok

router = APIRouter(prefix="/fields", tags=["烟田管理"])
BACKEND_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = (BACKEND_ROOT / "storage").resolve()


@router.get("")
async def list_fields(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await field_service.list_fields(db, user.id))


@router.post("")
async def create_field(body: FieldCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await field_service.create_field(db, user.id, body))


@router.get("/{field_id}")
async def field_detail(field_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await field_service.detail(db, user.id, field_id))


@router.patch("/{field_id}")
async def update_field(field_id: str, body: FieldUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await field_service.update_field(db, user.id, field_id, body.model_dump(exclude_unset=True)))


@router.get("/{field_id}/versions")
async def field_versions(field_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await field_service.versions(db, user.id, field_id))


@router.get("/{field_id}/base-map")
async def field_base_map(field_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await field_service.owned_field(db, user.id, field_id)
    if not row.base_map_path:
        raise NotFoundError("烟田底图不存在")
    path = (BACKEND_ROOT / row.base_map_path).resolve()
    if STORAGE_ROOT not in path.parents or not path.is_file():
        raise NotFoundError("烟田底图不存在")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=300"})
