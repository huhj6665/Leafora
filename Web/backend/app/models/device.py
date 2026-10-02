"""设备与设备绑定模型.

devices:          设备本体表，为未来 Jetson 边缘设备接入预留。
device_binding:   用户与设备绑定关系。

绑定规则：
    - 一个用户可以绑定多个设备；
    - 一个设备同一时间只能绑定一个用户（通过部分唯一索引保证，
      仅对 status=1 的“已绑定”记录生效）。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database.base import Base, BigIntPK, TimestampMixin


class Device(TimestampMixin, Base):
    """设备表."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(
        BigIntPK, primary_key=True, autoincrement=True, comment="设备主键ID"
    )
    device_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="设备编号，如 TLD001"
    )
    device_name: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", comment="设备名称"
    )
    device_secret: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="设备认证密钥 bcrypt 摘要"
    )
    # 状态：1-启用，0-禁用
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", comment="状态"
    )
    operating_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SHUTDOWN", server_default="SHUTDOWN",
        comment="运行状态：RUNNING/SHUTDOWN/ERROR/DISABLED",
    )
    communication_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="OFFLINE", server_default="OFFLINE",
        comment="通信状态：ONLINE/OFFLINE",
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近一次可信数据上报时间"
    )
    sync_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="IDLE", server_default="IDLE"
    )
    pending_sync_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_status_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class DeviceBinding(Base):
    """设备绑定表."""

    __tablename__ = "device_binding"
    __table_args__ = (
        # 部分唯一索引：同一设备只能存在一条 status=1 的绑定记录
        Index(
            "uq_device_binding_active_device",
            "device_id",
            unique=True,
            postgresql_where=text("status = 1"),
            sqlite_where=text("status = 1"),
        ),
        Index("ix_device_binding_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigIntPK, primary_key=True, autoincrement=True, comment="绑定ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigIntPK,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="用户ID",
    )
    device_id: Mapped[int] = mapped_column(
        BigIntPK,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="设备ID（外键 -> devices.id）",
    )
    bind_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, comment="绑定时间"
    )
    unbind_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="解绑时间"
    )
    # 状态：1-已绑定，0-已解绑
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", comment="绑定状态"
    )

    device = relationship("Device")
    user = relationship("User")
