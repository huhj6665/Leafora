"""设备管理接口（预留框架）.

当前仅提供接口结构与简单业务逻辑，实际设备接入
（Jetson / MQTT / HTTP 图片上传等）将在后续阶段扩展。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_device, get_current_user
from app.models.device import Device
from app.database.session import get_db
from app.models.user import User
from app.schemas.device import BindRequest, PairingConfirmRequest, UnbindRequest
from app.services import device_service
from app.utils.response import ok

router = APIRouter(prefix="/device", tags=["设备"])


@router.get("/list", summary="获取当前用户的设备列表")
async def list_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户已绑定的设备列表（需要 JWT）."""
    data = await device_service.list_user_devices(db, current_user.id)
    return ok(data)


@router.post("/bind", summary="绑定设备")
async def bind_device(
    req: BindRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """将设备绑定到当前用户（需要 JWT）."""
    data = await device_service.bind_device(db, current_user.id, req.device_id)
    return ok(data)


@router.post("/unbind", summary="解绑设备")
async def unbind_device(
    req: UnbindRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解绑当前用户与设备（需要 JWT）."""
    data = await device_service.unbind_device(db, current_user.id, req.device_id)
    return ok(data)


@router.post("/pairing-sessions", summary="设备申请动态配对会话")
async def create_pairing_session(
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
):
    return ok(await device_service.create_pairing_session(db, device))


@router.get("/pairing-sessions/{pairing_session_id}", summary="设备查询配对状态")
async def pairing_session_status(
    pairing_session_id: str,
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
):
    return ok(await device_service.get_pairing_status(db, device, pairing_session_id))


@router.post("/pairing/confirm", summary="用户确认动态配对")
async def confirm_pairing(
    req: PairingConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await device_service.confirm_pairing(
        db, user.id, req.pairing_session_id, req.pairing_token, req.device_id
    ))
