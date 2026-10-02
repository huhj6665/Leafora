"""Cloud-to-device task commands and the latest telemetry snapshot."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database.base import Base, BigIntPK, TimestampMixin


class TaskCommand(TimestampMixin, Base):
    __tablename__ = "task_commands"
    __table_args__ = (
        UniqueConstraint("inspection_pk", "command_type", name="uq_task_command_event_type"),
        Index("ix_task_commands_device_status", "device_pk", "status"),
        Index("ix_task_commands_retry_due", "status", "next_attempt_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    command_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    inspection_pk: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("inspection_events.id", ondelete="CASCADE"), nullable=False
    )
    device_pk: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    command_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING", server_default="PENDING"
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    ack_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    accepted_ack_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    final_ack_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class DeviceLatestData(TimestampMixin, Base):
    __tablename__ = "device_latest_data"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    device_pk: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("devices.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    owner_user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    inspection_pk: Mapped[Optional[int]] = mapped_column(
        BigIntPK, ForeignKey("inspection_events.id", ondelete="SET NULL"), nullable=True
    )
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
