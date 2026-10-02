"""巡检数据接口.

提供：
    - 巡检记录列表 / 统计 / 完整 JSON 查询
    - 图片上传（关联 data_id）
    - 云端推理重试
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_device, get_current_user
from app.database.session import get_db
from app.models.device import Device
from app.models.user import User
from app.services import image_service, inspection_service
from app.utils.response import ok

router = APIRouter(prefix="/inspection", tags=["巡检数据"])


@router.get("/list", summary="巡检记录列表")
async def list_inspections(
    device_id: Optional[str] = Query(None, description="按设备过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await inspection_service.list_inspections(
        db, current_user.id, device_id=device_id, page=page, page_size=page_size
    )
    return ok(data)


@router.get("/stats", summary="巡检数据统计")
async def inspection_stats(
    device_id: Optional[str] = Query(None, description="按设备过滤"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await inspection_service.get_inspection_stats(db, current_user.id, device_id)
    return ok(data)


@router.get("/{data_id}", summary="巡检记录完整 JSON")
async def get_inspection(
    data_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await inspection_service.get_inspection_full(db, current_user.id, data_id)
    return ok(data)


@router.post("/upload-image", summary="上传图片并关联巡检记录")
async def upload_image(
    device_id: str = Form(..., description="设备编号"),
    data_id: str = Form(..., description="巡检数据唯一ID"),
    image: UploadFile = File(..., description="图片文件（JPEG/PNG）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    content = await image.read()
    declared = image.content_type or None
    data = await image_service.upload_image(
        db, current_user, device_id, data_id, content, declared, image.filename
    )
    return ok(data)


@router.post("/device-upload", summary="设备 HTTP 图片上传（设备认证）")
async def device_upload(
    data_id: str = Form(..., description="巡检数据唯一ID"),
    inspection_id: str | None = Form(None, description="巡检事件ID（V2 设备必传，兼容旧设备可空）"),
    timestamp: str | None = Form(None, description="图片对应采样时间（ISO8601）"),
    image_id: str | None = Form(None, description="图片幂等ID（客户端 UUID，可选）"),
    image: UploadFile = File(..., description="图片文件（JPEG/PNG）"),
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
):
    """虚拟设备 / Jetson 通过 X-Device-ID + X-Device-Secret 认证后上传图片.

    图片仅能关联到本设备自身的巡检记录，服务端再次校验 device_id，不信任请求体。
    """
    content = await image.read()
    declared = image.content_type or None
    data = await image_service.device_upload_image(
        db, device, data_id, image_id, content, declared, image.filename,
        inspection_id=inspection_id, captured_at=timestamp,
    )
    return ok(data)


@router.post("/{data_id}/reprocess", summary="重新提交云端推理")
async def reprocess(
    data_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await image_service.reprocess_image(db, current_user.id, data_id)
    return ok(data)
