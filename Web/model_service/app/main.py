"""模型服务 FastAPI 入口.

- POST /predict : multipart 上传图片，返回推理结果（模型未就绪返回 503）
- GET  /health  : 服务/模型状态

权重缺失时服务仍可启动，不因模型不可用而崩溃。
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app import inference
from app.config import settings
from app.schemas import HealthResponse, PredictResponse
from app.service import predict_from_bytes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("model_service")

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION)


@app.get("/health", response_model=HealthResponse)
async def health():
    ready = inference.is_ready()
    return HealthResponse(
        status="ok" if ready else "model_unavailable",
        model_ready=ready,
        model_name=settings.MODEL_NAME,
        model_version=settings.MODEL_VERSION,
        weights_identifier=inference.weights_identifier(),
        detail=inference.load_error(),
    )


@app.post("/predict", response_model=PredictResponse)
async def predict(
    image: UploadFile = File(...),
    device_id: str = Form(""),
    data_id: str = Form(""),
):
    """执行推理；模型未部署/权重缺失返回 503."""
    if not inference.is_ready():
        raise HTTPException(
            status_code=503,
            detail=f"model_unavailable: {inference.load_error() or 'weights missing'}",
        )
    data = await image.read()
    try:
        return predict_from_bytes(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("PREDICT_FAILED")
        raise HTTPException(status_code=500, detail=f"inference failed: {exc}") from exc
