"""Short-lived protocol sessions and idempotency records."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database.base import Base, BigIntPK, TimestampMixin


class DevicePairingSession(TimestampMixin, Base):
    __tablename__ = "device_pairing_sessions"
    __table_args__ = (Index("ix_pairing_device_status", "device_pk", "status"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    pairing_session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_pk: Mapped[int] = mapped_column(BigIntPK, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_user_id: Mapped[Optional[int]] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)


class WebLoginSession(TimestampMixin, Base):
    __tablename__ = "web_login_sessions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    login_session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scan_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    poll_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_user_id: Mapped[Optional[int]] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)


class DeviceControlRequest(TimestampMixin, Base):
    __tablename__ = "device_control_requests"
    __table_args__ = (
        UniqueConstraint("device_id", "request_id", name="uq_control_device_request"),
        Index("ix_control_inspection", "inspection_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    inspection_id: Mapped[str] = mapped_column(String(64), nullable=False)
    command: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    ack_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
