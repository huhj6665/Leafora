"""推理编排：图片字节 → 解码 → RT-DETR-L → 结构化结果.

关键：bbox 必须转换回原始上传图片像素坐标 [x1, y1, x2, y2]，
不能把 resize 到 800×800 的网络输入坐标直接当作原图坐标。
Ultralytics 在 Results.boxes.xyxy 中已按原图（orig_shape）反算坐标，
此处额外做 clamp + round，确保不越界、为整数像素。
"""
from __future__ import annotations

import base64
from typing import Any, Optional

from app import inference
from app.config import settings
from app.schemas import PredictResponse


def _decode_image(data: bytes) -> Any:
    import cv2  # 由 ultralytics 依赖提供，懒加载
    import numpy as np

    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解码图片（仅支持 JPEG/PNG）")
    return img


def predict_from_bytes(image_bytes: bytes) -> PredictResponse:
    """执行推理并返回结构化结果（含标注图 base64）."""
    img = _decode_image(image_bytes)
    orig_h, orig_w = img.shape[:2]

    results = inference.predict(img)
    if not results:
        raise RuntimeError("模型未返回结果")

    result = results[0]
    names = result.names if result.names else {}

    detections = []
    has_target = False
    if result.boxes is not None and len(result.boxes) > 0:
        has_target = True
        # xyxy 已位于原图坐标（ultralytics 反算了 letterbox），此处 clamp 到原图范围
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            detections.append({
                "class": names.get(cls_id, str(cls_id)),
                "confidence": round(conf, 4),
                "bbox": [
                    max(0, round(x1)), max(0, round(y1)),
                    min(orig_w, round(x2)), min(orig_h, round(y2)),
                ],
            })

    # 标注图
    annotated_b64: Optional[str] = None
    try:
        import cv2
        plot = result.plot()  # BGR ndarray，坐标已对应原图
        ok, buf = cv2.imencode(".jpg", plot)
        if ok:
            annotated_b64 = base64.b64encode(buf.tobytes()).decode()
    except Exception:  # noqa: BLE001 - 标注图失败不影响推理结果
        annotated_b64 = None

    return PredictResponse(
        model_name=settings.MODEL_NAME,
        model_version=settings.MODEL_VERSION,
        weights_identifier=inference.weights_identifier() or "",
        has_target=has_target,
        results=detections,
        annotated_image_base64=annotated_b64,
    )
