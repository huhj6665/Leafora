"""User-owned field maps and calibration metadata."""
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database.base import Base, BigIntPK, TimestampMixin


class Field(TimestampMixin, Base):
    __tablename__ = "fields"
    __table_args__ = (
        Index("ix_fields_owner_status", "owner_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    field_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    owner_user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="READY", server_default="READY"
    )
    data_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="SIMULATED_CALIBRATION",
        server_default="SIMULATED_CALIBRATION",
    )
    calibration_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SIMULATED", server_default="SIMULATED"
    )
    coordinate_system: Mapped[str] = mapped_column(
        String(16), nullable=False, default="WGS84", server_default="WGS84"
    )
    base_map_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    pixel_boundary: Mapped[list] = mapped_column(JSON, nullable=False)
    geo_boundary: Mapped[dict] = mapped_column(JSON, nullable=False)
    control_points: Mapped[list] = mapped_column(JSON, nullable=False)
    transform_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
