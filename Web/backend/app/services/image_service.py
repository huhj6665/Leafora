"""图片上传与云端推理编排服务.

上传流程：
    校验图片 → 确认巡检记录存在 → 确认当前用户有权访问 → 保存图片
    → 创建 image record → 建立 data_id 关联 → 创建推理任务（cloud_detection）
    → 尽力调用模型服务（失败不回滚上传）。

关键约束：
    - 图片只允许关联到当前用户自己的巡检记录（服务端再次校验 device_id / 归属）。
    - 模型服务未启动 / 权重缺失时，图片上传仍成功，推理任务置 model_unavailable。
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.models.device import Device
from app.models.inspection import CloudDetection, ImageRecord, InspectionEvent, InspectionRecord
from app.models.user import User
from app.services import model_client
from app.services.image_storage import InvalidImageError, extension_for, save_bytes, validate_image

logger = logging.getLogger("app.image")

# RT-DETR-L 在 CPU 首次加载以及连续图片排队时可能超过 10 秒。图片已先幂等入库，
# 这里允许一次推理请求有足够时间完成，仍不会让模型故障回滚原图上传。
MODEL_SUBMIT_TIMEOUT = 60.0

# 推理状态枚举（与 cloud_detection.status 对应）
STATUS_WAITING_IMAGE = "waiting_image"
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_MODEL_UNAVAILABLE = "model_unavailable"
STATUS_NOT_REQUIRED = "not_required"


async def _get_owned_record(
    session: AsyncSession, user_id: int, device_id: str, data_id: str
) -> InspectionRecord:
    record = await session.scalar(
        select(InspectionRecord).where(
            InspectionRecord.device_id == device_id,
            InspectionRecord.data_id == data_id,
        )
    )
    if record is None:
        raise NotFoundError("巡检记录不存在")
    if record.owner_user_id != user_id:
        raise ForbiddenError("无权访问该巡检记录")
    return record


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_results(results: Any) -> list[dict[str, Any]]:
    """归一化模型检测结果，统一类别字段为 ``class``.

    兼容模型服务可能返回的 class / class_name / name 等别名，避免前端 class 列为空。
    只做字段名映射，不根据置信度或坐标猜测类别、不填入预设值。
    """
    normalized: list[dict[str, Any]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        class_name = (
            item.get("class")
            or item.get("class_name")
            or item.get("name")
            or item.get("cls")
            or ""
        )
        normalized.append(
            {
                "class": class_name,
                "confidence": item.get("confidence"),
                "bbox": item.get("bbox", []),
            }
        )
    return normalized


async def _apply_cloud_result(
    session: AsyncSession,
    cd: CloudDetection,
    result: dict[str, Any],
    record: InspectionRecord,
    original_image_id: str,
) -> None:
    """把模型服务返回结果写入 cloud_detection（含标注图落库）."""
    status = result.get("status", STATUS_FAILED)
    cd.status = status

    if status == STATUS_COMPLETED:
        cd.model_name = result.get("model_name") or cd.model_name
        cd.model_version = result.get("model_version") or cd.model_version
        cd.weights_identifier = result.get("weights_identifier")
        cd.processed_at = _now()
        cd.has_target = bool(result.get("has_target", False))
        cd.results = _normalize_results(result.get("results"))
        cd.error_message = None

        annotated_b64 = result.get("annotated_image_base64")
        if annotated_b64:
            try:
                ann_bytes = base64.b64decode(annotated_b64)
                ann_key = f"images/annotated/{original_image_id}_ann.jpg"
                save_bytes(ann_key, ann_bytes)
                session.add(ImageRecord(
                    image_id=uuid.uuid4().hex,
                    inspection_id=record.id,
                    image_type="annotated",
                    storage_key=ann_key,
                    content_type="image/jpeg",
                    size_bytes=len(ann_bytes),
                    upload_status="completed",
                ))
            except Exception as exc:  # noqa: BLE001 - 标注图失败不阻断推理结果
                logger.warning("ANNOTATED_SAVE_FAILED err=%s", exc)
    elif status == STATUS_MODEL_UNAVAILABLE:
        cd.error_message = result.get("reason") or "model unavailable"
    elif status == STATUS_FAILED:
        cd.error_message = result.get("reason") or "inference failed"


async def upload_image(
    session: AsyncSession,
    user: User,
    device_id: str,
    data_id: str,
    content: bytes,
    declared_content_type: str | None,
    filename: str | None = None,
) -> dict[str, Any]:
    """上传一张图片并关联巡检记录，创建云端推理任务."""
    # 1. 校验图片
    try:
        real_type = validate_image(content, declared_content_type)
    except InvalidImageError as exc:
        raise BusinessError(str(exc), code=400, status_code=400) from exc

    # 2. 确认巡检记录存在 + 3. 归属校验（服务端再次校验，不信任前端）
    record = await _get_owned_record(session, user.id, device_id, data_id)

    # 4. 保存图片 + 创建 image record + 建立 data_id 关联
    image_id = uuid.uuid4().hex
    ext = extension_for(real_type)
    storage_key = f"images/original/{image_id}.{ext}"
    save_bytes(storage_key, content)

    image = ImageRecord(
        image_id=image_id,
        inspection_id=record.id,
        image_type="original",
        storage_key=storage_key,
        content_type=real_type,
        size_bytes=len(content),
        upload_status="completed",
    )
    session.add(image)
    await session.flush()

    # 5. 创建推理任务（cloud_detection）
    cd = CloudDetection(
        image_id=image.id,
        inspection_id=record.id,
        status=STATUS_PENDING,
    )
    session.add(cd)
    await session.flush()

    # 6. 先提交，保证图片上传成功落库（模型不可用也不回滚）
    await session.commit()

    # 7. 尽力调用模型服务（失败仅置状态，不回滚上传）
    result = await model_client.submit_image(
        content, real_type, device_id, data_id, timeout=MODEL_SUBMIT_TIMEOUT
    )
    await _apply_cloud_result(session, cd, result, record, image_id)
    await session.commit()

    return {
        "image_id": image_id,
        "image_type": "original",
        "upload_status": "completed",
        "cloud_detection": {
            "status": cd.status,
            "model_name": cd.model_name,
            "model_version": cd.model_version,
            "processed_at": cd.processed_at,
            "has_target": cd.has_target,
            "results": cd.results or [],
            "error_message": cd.error_message,
        },
    }


async def _wait_for_record(
    session: AsyncSession, device_id: str, data_id: str
) -> InspectionRecord | None:
    """有界等待巡检记录入库（处理 HTTP 图片先到、MQTT 记录后到的时序差异）.

    轮询数据库实际状态，不依赖固定 sleep；超时仍未出现返回 None。
    """
    deadline = time.monotonic() + settings.IMAGE_PENDING_WAIT_SECONDS
    while True:
        record = await session.scalar(
            select(InspectionRecord).where(
                InspectionRecord.device_id == device_id,
                InspectionRecord.data_id == data_id,
            )
        )
        if record is not None:
            return record
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(settings.IMAGE_PENDING_POLL_INTERVAL)


async def device_upload_image(
    session: AsyncSession,
    device: Device,
    data_id: str,
    image_id: str | None,
    content: bytes,
    declared_content_type: str | None,
    filename: str | None = None,
    inspection_id: str | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """设备专用图片上传（已通过 get_current_device 认证）.

    幂等键：``image_id``（客户端生成 UUID）。同一 image_id 重复上传返回已有记录，
    不重复创建图片与云端推理任务。巡检记录归属由设备身份 + 绑定关系决定。
    """
    effective_image_id = (image_id or "").strip() or uuid.uuid4().hex

    async def validate_binding(record: InspectionRecord) -> None:
        if record.device_id != device.device_id:
            raise NotFoundError("巡检记录不存在")
        if inspection_id:
            event = await session.get(InspectionEvent, record.event_id) if record.event_id else None
            if event is None or event.inspection_id != inspection_id:
                raise BusinessError("图片 inspection_id 与数据记录不匹配", code=409, status_code=409)
        if captured_at:
            try:
                text = captured_at[:-1] + "+00:00" if captured_at.endswith("Z") else captured_at
                supplied = datetime.fromisoformat(text)
                if supplied.tzinfo is None:
                    supplied = supplied.replace(tzinfo=timezone.utc)
                stored = record.captured_at
                if stored.tzinfo is None:
                    stored = stored.replace(tzinfo=timezone.utc)
                if abs((stored.astimezone(timezone.utc) - supplied.astimezone(timezone.utc)).total_seconds()) > 2:
                    raise BusinessError("图片 timestamp 与数据记录不匹配", code=409, status_code=409)
            except ValueError as exc:
                raise BusinessError("图片 timestamp 格式无效", code=400, status_code=400) from exc

    # 1. 幂等：同一 image_id 重复上传
    existing = await session.scalar(
        select(ImageRecord).where(ImageRecord.image_id == effective_image_id)
    )
    if existing is not None:
        record = await session.get(InspectionRecord, existing.inspection_id)
        if record is None or record.device_id != device.device_id:
            raise ForbiddenError("image_id 已存在且不属于该设备")
        await validate_binding(record)
        cd = await session.scalar(
            select(CloudDetection).where(CloudDetection.image_id == existing.id)
        )
        return {
            "image_id": effective_image_id,
            "image_type": existing.image_type,
            "upload_status": existing.upload_status,
            "already_uploaded": True,
            "cloud_detection": {
                "status": cd.status if cd else None,
                "model_name": cd.model_name if cd else None,
                "model_version": cd.model_version if cd else None,
                "processed_at": cd.processed_at if cd else None,
                "has_target": cd.has_target if cd else None,
                "results": cd.results if cd else [],
                "error_message": cd.error_message if cd else None,
            },
        }

    # 2. 校验图片
    try:
        real_type = validate_image(content, declared_content_type)
    except InvalidImageError as exc:
        raise BusinessError(str(exc), code=400, status_code=400) from exc

    # 3. 有界等待巡检记录入库（记录必须属于本设备）
    record = await _wait_for_record(session, device.device_id, data_id)
    if record is None:
        raise NotFoundError("巡检记录尚未入库，请稍后重试")
    await validate_binding(record)

    # 4. 保存图片 + 创建 image record + 关联
    ext = extension_for(real_type)
    storage_key = f"images/original/{effective_image_id}.{ext}"
    save_bytes(storage_key, content)

    image = ImageRecord(
        image_id=effective_image_id,
        inspection_id=record.id,
        image_type="original",
        storage_key=storage_key,
        content_type=real_type,
        size_bytes=len(content),
        upload_status="completed",
    )
    session.add(image)
    await session.flush()

    # 5. 创建推理任务
    cd = CloudDetection(
        image_id=image.id,
        inspection_id=record.id,
        status=STATUS_PENDING,
    )
    session.add(cd)
    await session.flush()

    # 6. 先提交，保证图片上传落库（模型不可用也不回滚）
    await session.commit()

    # 7. 尽力调用模型服务
    result = await model_client.submit_image(
        content, real_type, device.device_id, data_id, timeout=MODEL_SUBMIT_TIMEOUT
    )
    await _apply_cloud_result(session, cd, result, record, effective_image_id)
    await session.commit()

    return {
        "image_id": effective_image_id,
        "image_type": "original",
        "upload_status": "completed",
        "already_uploaded": False,
        "cloud_detection": {
            "status": cd.status,
            "model_name": cd.model_name,
            "model_version": cd.model_version,
            "processed_at": cd.processed_at,
            "has_target": cd.has_target,
            "results": cd.results or [],
            "error_message": cd.error_message,
        },
    }


async def reprocess_image(
    session: AsyncSession, user_id: int, data_id: str
) -> dict[str, Any]:
    """重新提交原图到模型服务（用于模型就绪后重试）."""
    record = await session.scalar(
        select(InspectionRecord)
        .where(InspectionRecord.data_id == data_id)
    )
    if record is None:
        raise NotFoundError("巡检记录不存在")
    if record.owner_user_id != user_id:
        raise ForbiddenError("无权访问该巡检记录")

    image = await session.scalar(
        select(ImageRecord).where(
            ImageRecord.inspection_id == record.id,
            ImageRecord.image_type == "original",
        )
    )
    if image is None:
        raise BusinessError("该巡检记录尚未上传图片", code=400, status_code=400)

    cd = await session.scalar(
        select(CloudDetection).where(CloudDetection.image_id == image.id)
    )
    if cd is None:
        cd = CloudDetection(image_id=image.id, inspection_id=record.id, status=STATUS_PENDING)
        session.add(cd)
        await session.flush()

    cd.status = STATUS_PROCESSING
    await session.commit()

    from app.services.image_storage import read_bytes

    content = read_bytes(image.storage_key)
    result = await model_client.submit_image(
        content, image.content_type or "image/jpeg", record.device_id, data_id,
        timeout=MODEL_SUBMIT_TIMEOUT,
    )
    await _apply_cloud_result(session, cd, result, record, image.image_id)
    await session.commit()

    return {
        "image_id": image.image_id,
        "cloud_detection": {
            "status": cd.status,
            "model_name": cd.model_name,
            "model_version": cd.model_version,
            "processed_at": cd.processed_at,
            "has_target": cd.has_target,
            "results": cd.results or [],
            "error_message": cd.error_message,
        },
    }
