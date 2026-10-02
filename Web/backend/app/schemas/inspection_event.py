"""巡检事件 API 输入模型。"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class InspectionEventCreate(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(default="田间巡检", min_length=1, max_length=128)
    location_name: Optional[str] = Field(default=None, max_length=255)


class InspectionEventStatusUpdate(BaseModel):
    status: Literal["RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
    failure_reason: Optional[str] = Field(default=None, max_length=500)


class AssistantQuestion(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    inspection_id: Optional[str] = Field(default=None, max_length=64)
