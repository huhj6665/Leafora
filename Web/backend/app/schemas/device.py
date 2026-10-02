"""设备相关 Schema."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeviceItem(BaseModel):
    """设备列表项."""

    id: int
    device_id: str
    device_name: str
    status: int
    operating_status: str = "SHUTDOWN"
    communication_status: str = "OFFLINE"
    last_seen_at: Optional[datetime] = None
    cpu_temperature: Optional[float] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    storage_usage: Optional[float] = None
    network_status: Optional[str] = None
    inspection_count: int = 0
    sync_status: str = "IDLE"
    pending_sync_count: int = 0
    bind_time: Optional[datetime] = None


class BindRequest(BaseModel):
    """设备绑定请求."""

    device_id: str = Field(..., min_length=1, description="设备编号，如 TLD001")


class UnbindRequest(BaseModel):
    """设备解绑请求."""

    device_id: str = Field(..., min_length=1, description="设备编号，如 TLD001")


class PairingConfirmRequest(BaseModel):
    pairing_session_id: str = Field(..., min_length=8, max_length=64)
    pairing_token: str = Field(..., min_length=20, max_length=512)
    device_id: str = Field(..., min_length=1, max_length=64)
