"""巡检业务数据模型.

以 ``inspection_records`` 为统一主记录，``data_id`` 是整份业务数据的关联中心。
围绕它建立结构化的子表：定位/环境/Jetson 检测/设备状态/图片/云端检测。

设计原则：
    - 不把整份 MQTT JSON 仅作为字符串塞进一张表；结构化落库，便于查询与地图/分析扩展。
    - ``(device_id, data_id)`` 唯一，保证 MQTT QoS1 重投不产生重复业务数据。
    - Jetson 原始 ``detection`` 与云端 ``cloud_detection`` 分离保存，互不覆盖。
    - 图片通过 ``image_id`` 独立主键，经 ``inspection_id`` 关联到巡检记录（不用图片 ID 当业务主 ID）。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database.base import Base, BigIntPK, TimestampMixin


class InspectionEvent(TimestampMixin, Base):
    """一次完整巡检任务。

    ``InspectionRecord`` 仍代表一条不可变的采样数据；事件只负责把同一次
    Jetson 作业中的 GPS、环境、图片与检测结果聚合起来。历史记录允许
    ``event_id`` 为空，从而保证迁移不改写、不丢失已有数据。
    """

    __tablename__ = "inspection_events"
    __table_args__ = (
        Index("ix_inspection_events_owner_started", "owner_user_id", "started_at"),
        Index("ix_inspection_events_device", "device_id"),
        UniqueConstraint(
            "owner_user_id", "client_request_id", name="uq_inspection_owner_client_request"
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    inspection_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="设备生成的巡检 UUID"
    )
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="未命名巡检")
    location_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="CREATED", server_default="CREATED"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sync_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SYNCED", server_default="SYNCED"
    )
    pending_sync_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    field_pk: Mapped[Optional[int]] = mapped_column(
        BigIntPK, ForeignKey("fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    field_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    field_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    field_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    client_request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    run_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    data_provenance: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    records: Mapped[list["InspectionRecord"]] = relationship(back_populates="event")


class InspectionRecord(Base):
    """巡检记录主表."""

    __tablename__ = "inspection_records"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "data_id", name="uq_inspection_device_data"
        ),
        Index("ix_inspection_device_id", "device_id"),
        Index("ix_inspection_owner_user_id", "owner_user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigIntPK, primary_key=True, autoincrement=True, comment="记录主键ID"
    )
    event_id: Mapped[Optional[int]] = mapped_column(
        BigIntPK,
        ForeignKey("inspection_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="所属巡检事件；历史 V2 数据可为空",
    )
    device_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="设备编号，如 TLD_SIM_001"
    )
    data_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="巡检数据唯一ID（UUID4）"
    )
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        BigIntPK,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="归属用户ID（由后端根据绑定关系确定）",
    )
    schema_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="1.0", comment="MQTT 协议版本"
    )
    captured_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="设备采集时间（timestamp）"
    )
    received_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="服务端接收/入库时间",
    )
    # 原始 MQTT JSON（联调/审计用），不替代结构化子表
    raw_payload: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="原始 MQTT JSON 字符串"
    )
    sequence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    field_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    field_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    data_provenance: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    flight_status: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    location: Mapped[Optional["LocationRecord"]] = relationship(
        back_populates="inspection", uselist=False, cascade="all, delete-orphan"
    )
    environment: Mapped[Optional["EnvironmentRecord"]] = relationship(
        back_populates="inspection", uselist=False, cascade="all, delete-orphan"
    )
    device_status: Mapped[Optional["DeviceStatusRecord"]] = relationship(
        back_populates="inspection", uselist=False, cascade="all, delete-orphan"
    )
    detection: Mapped[Optional["DetectionRecord"]] = relationship(
        back_populates="inspection", uselist=False, cascade="all, delete-orphan"
    )
    images: Mapped[list["ImageRecord"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )
    event: Mapped[Optional["InspectionEvent"]] = relationship(back_populates="records")


class LocationRecord(Base):
    """GPS / RTK 定位数据."""

    __tablename__ = "location_records"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    inspection_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("inspection_records.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True, comment="关联巡检记录ID",
    )
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    altitude_msl_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    height_ellipsoid_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fix_quality: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rtk_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    satellites_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    horizontal_accuracy_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vertical_accuracy_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ground_speed_mps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    course_over_ground_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    correction_age_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sampled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    inspection: Mapped["InspectionRecord"] = relationship(back_populates="location")


class EnvironmentRecord(Base):
    """环境传感器数据."""

    __tablename__ = "environment_records"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    inspection_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("inspection_records.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True, comment="关联巡检记录ID",
    )
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    humidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    co2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    light: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sampled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="环境采样时间"
    )
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    inspection: Mapped["InspectionRecord"] = relationship(back_populates="environment")


class DeviceStatusRecord(Base):
    """设备运行状态."""

    __tablename__ = "device_status_records"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    inspection_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("inspection_records.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True, comment="关联巡检记录ID",
    )
    cpu_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    storage_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    network_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    inspection: Mapped["InspectionRecord"] = relationship(back_populates="device_status")


class DetectionRecord(Base):
    """Jetson 边缘检测结果（原始，不被云端覆盖）."""

    __tablename__ = "detection_records"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    inspection_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("inspection_records.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True, comment="关联巡检记录ID",
    )
    has_target: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sampled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    inspection: Mapped["InspectionRecord"] = relationship(back_populates="detection")
    results: Mapped[list["DetectionResult"]] = relationship(
        back_populates="detection", cascade="all, delete-orphan"
    )


class DetectionResult(Base):
    """Jetson 检测结果明细（单条目标）."""

    __tablename__ = "detection_results"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    detection_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("detection_records.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="关联 detection_records.id",
    )
    class_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="类别")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, comment="置信度")
    bbox: Mapped[list] = mapped_column(JSON, nullable=False, comment="[x1,y1,x2,y2]")

    detection: Mapped["DetectionRecord"] = relationship(back_populates="results")


class ImageRecord(Base):
    """图片记录（原始图 / 标注图）."""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    image_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="图片唯一ID（UUID4）"
    )
    inspection_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("inspection_records.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="关联巡检记录ID",
    )
    image_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="original", comment="original / annotated"
    )
    storage_key: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="相对存储路径（storage key）"
    )
    content_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="MIME 类型"
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    upload_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="completed", comment="上传状态"
    )

    inspection: Mapped["InspectionRecord"] = relationship(back_populates="images")
    cloud_detection: Mapped[Optional["CloudDetection"]] = relationship(
        back_populates="image", uselist=False, cascade="all, delete-orphan"
    )


class CloudDetection(Base):
    """云端 RT-DETR-L 二次识别结果（与 Jetson 原始 detection 分离）."""

    __tablename__ = "cloud_detection"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    image_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("images.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True, comment="关联 images.id（一对一）",
    )
    inspection_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("inspection_records.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="关联巡检记录ID",
    )
    # waiting_image / pending / processing / completed / failed / model_unavailable / not_required
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", comment="推理任务状态"
    )
    model_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    weights_identifier: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="权重标识（SHA-256 / 文件名）"
    )
    processed_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="模型处理完成时间"
    )
    has_target: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    results: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment='[{class, confidence, bbox}]'
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    image: Mapped["ImageRecord"] = relationship(back_populates="cloud_detection")
