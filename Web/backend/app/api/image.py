"""图片文件访问接口.

按 image_id 返回图片文件（仅限归属用户），返回字节流而非绝对路径。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.inspection import ImageRecord, InspectionRecord
from app.models.user import User
from app.services.image_storage import resolve_path

router = APIRouter(prefix="/image", tags=["图片"])


@router.get("/{image_id}/file", summary="获取图片文件")
async def get_image_file(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    image = await db.scalar(
        select(ImageRecord).where(ImageRecord.image_id == image_id)
    )
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")

    # 归属校验：图片所属巡检记录的 owner 必须是当前用户
    owner_id = await db.scalar(
        select(InspectionRecord.owner_user_id).where(
            InspectionRecord.id == image.inspection_id
        )
    )
    if owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该图片")

    try:
        path = resolve_path(image.storage_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片文件不存在") from exc

    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片文件不存在")

    return FileResponse(path, media_type=image.content_type or "application/octet-stream")
