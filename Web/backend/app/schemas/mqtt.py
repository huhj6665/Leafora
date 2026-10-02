"""TLD MQTT V1.0 数据协议 Schema.

模拟设备与真实 Jetson 必须使用同一 JSON 结构。字段名在各模块间不得改名。

注意：``detection`` 为 Jetson 边缘结果，仅作模拟；真实图片二次识别结果
单独保存到 ``cloud_detection``，二者互不覆盖。
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _timestamp(value: Optional[str]) -> Optional[str]:
    if value is not None:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


class LocationBlock(BaseModel):
    """GPS / RTK 定位."""

    latitude: Optional[float] = Field(..., ge=-90, le=90, allow_inf_nan=False)
    longitude: Optional[float] = Field(..., ge=-180, le=180, allow_inf_nan=False)
    altitude_msl_m: Optional[float] = None
    height_ellipsoid_m: Optional[float] = None
    fix_quality: Optional[int] = None
    rtk_status: Optional[str] = None
    satellites_used: Optional[int] = None
    horizontal_accuracy_m: Optional[float] = None
    vertical_accuracy_m: Optional[float] = None
    ground_speed_mps: Optional[float] = None
    course_over_ground_deg: Optional[float] = None
    correction_age_s: Optional[float] = None
    position_valid: bool
    sampled_at: Optional[str] = None

    _time = field_validator("sampled_at")(_timestamp)

    @model_validator(mode="after")
    def valid_position_has_coordinates(self):
        if self.position_valid and (self.latitude is None or self.longitude is None):
            raise ValueError("有效定位必须包含经纬度")
        return self


class EnvironmentBlock(BaseModel):
    """环境传感器."""

    temperature: Optional[float] = Field(default=None, allow_inf_nan=False)
    humidity: Optional[float] = Field(default=None, allow_inf_nan=False)
    co2: Optional[float] = Field(default=None, allow_inf_nan=False)
    light: Optional[float] = Field(default=None, allow_inf_nan=False)
    sampled_at: Optional[str]
    valid: bool = True

    _time = field_validator("sampled_at")(_timestamp)

    @model_validator(mode="after")
    def valid_sample_has_timestamp(self):
        if self.valid and (self.sampled_at is None or all(
            value is None for value in (self.temperature, self.humidity, self.co2, self.light)
        )):
            raise ValueError("有效环境样本必须包含采样时间和读数")
        return self


class DetectionResultItem(BaseModel):
    """单条 Jetson 检测结果."""

    model_config = ConfigDict(populate_by_name=True)

    class_name: str = Field(alias="class", description="类别")
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2]


class DetectionBlock(BaseModel):
    """Jetson 边缘检测块."""

    has_target: bool
    results: List[DetectionResultItem] = Field(default_factory=list)
    sampled_at: Optional[str] = None

    _time = field_validator("sampled_at")(_timestamp)


class DeviceStatusBlock(BaseModel):
    """设备运行状态."""

    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    temperature: Optional[float] = None
    cpu_temperature: Optional[float] = None
    storage_usage: Optional[float] = None
    network_status: Optional[Literal["online", "offline", "degraded"]] = None


class MqttMessageV1(BaseModel):
    """TLD MQTT V1.0 完整消息."""

    schema_version: str
    device_id: str
    data_id: str
    # V1.1 向后兼容扩展：旧设备不传时仍按 V1.0 正常入库。
    inspection_id: Optional[str] = None
    sequence: Optional[int] = Field(default=None, ge=0)
    field_id: Optional[str] = None
    field_version: Optional[int] = Field(default=None, ge=1)
    run_mode: Optional[str] = None
    data_provenance: Optional[str] = None
    flight_status: Optional[dict] = None
    timestamp: str

    _time = field_validator("timestamp")(_timestamp)

    location: LocationBlock
    environment: EnvironmentBlock
    detection: DetectionBlock
    device_status: DeviceStatusBlock

    @model_validator(mode="after")
    def real_environment_requires_complete_readings(self):
        if self.run_mode == "REAL_DEVICE" and self.environment.valid and any(
            value is None for value in (self.environment.temperature, self.environment.humidity,
                                       self.environment.co2, self.environment.light)
        ):
            raise ValueError("真实设备部分传感器失效时 environment.valid 必须为 false")
        return self


class InspectionControlMessage(BaseModel):
    """设备控制消息，通过独立 control topic 上报巡检生命周期。"""

    type: Literal["inspection_control"]
    command: Literal["START", "END"]
    schema_version: str = "1.1"
    # V1.1 legacy controls may omit request_id; the cloud derives a stable
    # compatibility key from device/inspection/command in that case.
    request_id: Optional[str] = Field(default=None, min_length=4, max_length=64)
    inspection_id: str = Field(..., min_length=4, max_length=64)
    device_id: str = Field(..., min_length=1, max_length=64)
    timestamp: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=128)
    pending_sync_count: int = Field(default=0, ge=0)


class DeviceStatusMessage(BaseModel):
    type: Literal["device_status"] = "device_status"
    device_id: str
    timestamp: Optional[str] = None
    operating_status: Optional[str] = None
    communication_status: str = "ONLINE"
    sync_status: str = "IDLE"
    pending_sync_count: int = Field(default=0, ge=0)
    inspection_id: Optional[str] = None
    gps_fix: Optional[str] = None
    rtk_status: Optional[str] = None
    camera_status: Optional[str] = None
    inference_status: Optional[str] = None
    storage_usage: Optional[float] = None


class DeviceAckMessage(BaseModel):
    type: Literal["command_ack"] = "command_ack"
    device_id: str
    command_id: str
    status: str
    schema_version: str = "2.0"
    inspection_id: Optional[str] = None
    command: Optional[str] = None
    phase: Optional[str] = None
    reason_code: Optional[str] = None
    summary: Optional[dict] = None
    timestamp: Optional[str] = None
