"""Mini-program task-control request schemas."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class InspectionStart(BaseModel):
    field_id: str = Field(..., min_length=1, max_length=64)
    device_id: str = Field(..., min_length=1, max_length=64)
    client_request_id: str = Field(..., min_length=8, max_length=64)
    name: Optional[str] = Field(default=None, max_length=128)
    run_mode: Literal["FAST_TEST", "REALTIME_SIMULATION", "REAL_DEVICE"] = "REAL_DEVICE"


class InspectionEnd(BaseModel):
    client_request_id: str = Field(..., min_length=8, max_length=64)
