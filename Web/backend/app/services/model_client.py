"""云端模型服务 HTTP 客户端.

后端通过 HTTP 调用独立部署的 RT-DETR-L 模型服务（``MODEL_SERVICE_URL``）。
模型服务未配置 / 未启动 / 权重缺失时，均视为 ``model_unavailable``，绝不回滚图片上传。

返回统一结构：
    {
        "available": bool,
        "status": "completed" | "model_unavailable" | "failed",
        "results": [...],            # [{class, confidence, bbox}]
        "has_target": bool,
        "model_name": str,
        "model_version": str,
        "weights_identifier": str,
        "processed_at": str,
        "annotated_image_base64": str | None,
        "reason": str | None,        # 不可用/失败原因
    }
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("app.model_client")

TIMEOUT_SECONDS = 60.0
RETRYABLE_STATUS_CODES = {502, 504}
RETRY_DELAY_SECONDS = 0.5


def _unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "status": "model_unavailable", "reason": reason}


async def submit_image(
    image_bytes: bytes,
    content_type: str,
    device_id: str,
    data_id: str,
    timeout: float = TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """将图片提交到模型服务并返回推理结果.

    任何连接/HTTP 异常都降级为 model_unavailable，不向调用方抛出。
    """
    url = settings.MODEL_SERVICE_URL
    if not url:
        return _unavailable("model_service_not_configured")

    predict_url = url.rstrip("/") + "/predict"
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    predict_url,
                    files={"image": ("image", image_bytes, content_type)},
                    data={"device_id": device_id, "data_id": data_id},
                )
        except httpx.HTTPError as exc:
            if attempt == 0:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            logger.warning("MODEL_SERVICE_UNREACHABLE url=%s err=%s", url, exc)
            return _unavailable(f"model_service_unreachable: {exc}")

        if resp.status_code in RETRYABLE_STATUS_CODES and attempt == 0:
            await asyncio.sleep(RETRY_DELAY_SECONDS)
            continue
        break

    if resp.status_code == 503:
        detail = ""
        try:
            detail = resp.json().get("detail", "")
        except Exception:  # noqa: BLE001
            detail = resp.text[:200]
        return _unavailable(detail or "model_unavailable")

    if resp.status_code in RETRYABLE_STATUS_CODES:
        return _unavailable(f"model_service_http_{resp.status_code}")

    if resp.status_code != 200:
        return {
            "available": False,
            "status": "failed",
            "reason": f"model_service_http_{resp.status_code}",
        }

    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "status": "failed", "reason": f"bad_response: {exc}"}

    data.setdefault("available", True)
    data.setdefault("status", "completed")
    return data
