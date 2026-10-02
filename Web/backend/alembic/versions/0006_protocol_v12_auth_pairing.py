"""protocol v1.2, pairing, QR login and phone password support

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("sync_status", sa.String(16), server_default="IDLE", nullable=False))
    op.add_column("devices", sa.Column("pending_sync_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("devices", sa.Column("last_status_payload", sa.JSON(), nullable=True))
    op.add_column("inspection_events", sa.Column("sync_status", sa.String(16), server_default="SYNCED", nullable=False))
    op.add_column("inspection_events", sa.Column("pending_sync_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("inspection_records", sa.Column("sequence", sa.Integer(), nullable=True))

    for column in (
        "altitude_msl_m", "height_ellipsoid_m", "fix_quality", "rtk_status",
        "satellites_used", "horizontal_accuracy_m", "vertical_accuracy_m",
        "ground_speed_mps", "course_over_ground_deg", "correction_age_s",
    ):
        op.alter_column("location_records", column, nullable=True)
    op.add_column("location_records", sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=True))
    for column in ("temperature", "humidity", "co2", "light"):
        op.alter_column("environment_records", column, nullable=True)
    op.add_column("environment_records", sa.Column("valid", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    for column in ("cpu_usage", "memory_usage", "temperature"):
        op.alter_column("device_status_records", column, nullable=True)
    op.add_column("detection_records", sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "device_pairing_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("pairing_session_id", sa.String(64), nullable=False),
        sa.Column("device_pk", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_user_id", sa.BigInteger(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["device_pk"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pairing_session_id"),
    )
    op.create_index("ix_pairing_device_status", "device_pairing_sessions", ["device_pk", "status"])

    op.create_table(
        "web_login_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("login_session_id", sa.String(64), nullable=False),
        sa.Column("scan_token_hash", sa.String(64), nullable=False),
        sa.Column("poll_token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_user_id", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["confirmed_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login_session_id"),
    )

    op.create_table(
        "device_control_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("inspection_id", sa.String(64), nullable=False),
        sa.Column("command", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("ack_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "request_id", name="uq_control_device_request"),
    )
    op.create_index("ix_control_inspection", "device_control_requests", ["inspection_id"])


def downgrade() -> None:
    op.drop_table("device_control_requests")
    op.drop_table("web_login_sessions")
    op.drop_table("device_pairing_sessions")
    op.drop_column("detection_records", "sampled_at")
    op.drop_column("environment_records", "valid")
    op.drop_column("location_records", "sampled_at")
    op.drop_column("inspection_records", "sequence")
    op.drop_column("inspection_events", "pending_sync_count")
    op.drop_column("inspection_events", "sync_status")
    op.drop_column("devices", "last_status_payload")
    op.drop_column("devices", "pending_sync_count")
    op.drop_column("devices", "sync_status")
