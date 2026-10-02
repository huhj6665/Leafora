"""模型服务请求/响应 Schema."""
from typing import List, Optional

from pydantic import BaseModel


class DetectionResult(BaseModel):
    """单条检测结果（原始像素坐标 bbox）.

    注意：结果中的类别字段统一命名为 ``class``（与业务协议、后端存储、前端展示一致），
    不要使用 ``class_name`` / ``name`` / ``cls`` 等别名，否则会导致前端 class 列为空。
    """

    class_: str = ""
    confidence: float
    bbox: List[float]  # 原图像素坐标 [x1, y1, x2, y2]


class PredictResponse(BaseModel):
    model_name: str
    model_version: str
    weights_identifier: str
    has_target: bool
    # 结果以 dict 原样透传，保证 `class` 键不被 pydantic 重命名/丢弃
    results: List[dict] = []
    annotated_image_base64: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    model_ready: bool
    model_name: str
    model_version: str
    weights_identifier: Optional[str] = None
    detail: Optional[str] = None
