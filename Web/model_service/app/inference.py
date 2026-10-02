"""RT-DETR-L 模型封装（懒加载）.

- 使用 Ultralytics RTDETR 接口加载，禁止用 YOLO 类错误加载。
- 权重缺失时服务可启动，``is_ready`` 返回 False，/predict 返回 503。
- 权重标识使用 SHA-256，禁止仅用 "RT-DETR-L" 作为永久版本号。
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger("model_service.inference")

_model: Any = None
_weights_identifier: Optional[str] = None
_load_error: Optional[str] = None


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_model() -> Any:
    """加载 RT-DETR-L 模型（进程内单例，懒加载）."""
    global _model, _weights_identifier, _load_error

    if _model is not None:
        return _model

    weight_path = Path(settings.MODEL_WEIGHT_PATH)
    if not weight_path.exists():
        _load_error = f"weights not found: {weight_path}"
        logger.warning("MODEL_UNAVAILABLE %s", _load_error)
        return None

    try:
        from ultralytics import RTDETR  # 使用 Ultralytics RT-DETR 接口

        _model = RTDETR(str(weight_path))
        _model.to(settings.MODEL_DEVICE)
        _weights_identifier = _compute_sha256(weight_path)
        logger.info("MODEL_LOADED name=%s version=%s weights=%s device=%s",
                    settings.MODEL_NAME, settings.MODEL_VERSION,
                    _weights_identifier, settings.MODEL_DEVICE)
        return _model
    except Exception as exc:  # noqa: BLE001
        _load_error = f"load failed: {exc}"
        logger.exception("MODEL_LOAD_FAILED %s", _load_error)
        return None


def weights_identifier() -> Optional[str]:
    return _weights_identifier


def load_error() -> Optional[str]:
    return _load_error


def is_ready() -> bool:
    return load_model() is not None


def predict(image_array: Any) -> list:
    """对单张图像（numpy BGR 数组）执行推理，返回 ultralytics Results 列表."""
    model = load_model()
    if model is None:
        raise RuntimeError(_load_error or "model unavailable")
    return model.predict(
        source=image_array,
        imgsz=settings.MODEL_IMAGE_SIZE,
        conf=settings.MODEL_CONFIDENCE,
        device=settings.MODEL_DEVICE,
        verbose=False,
    )
