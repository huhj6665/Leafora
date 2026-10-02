"""field snapshots, cloud task commands and MQTT V1.3 telemetry

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fields",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("field_id", sa.String(64), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("status", sa.String(16), server_default="READY", nullable=False),
        sa.Column("data_source", sa.String(32), server_default="SIMULATED_CALIBRATION", nullable=False),
        sa.Column("calibration_status", sa.String(16), server_default="SIMULATED", nullable=False),
        sa.Column("coordinate_system", sa.String(16), server_default="WGS84", nullable=False),
        sa.Column("base_map_path", sa.String(512), nullable=True),
        sa.Column("pixel_boundary", sa.JSON(), nullable=False),
        sa.Column("geo_boundary", sa.JSON(), nullable=False),
        sa.Column("control_points", sa.JSON(), nullable=False),
        sa.Column("transform_params", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("field_id"),
    )
    op.create_index("ix_fields_owner_status", "fields", ["owner_user_id", "status"])

    for column in (
        sa.Column("field_pk", sa.BigInteger(), nullable=True),
        sa.Column("field_id", sa.String(64), nullable=True),
        sa.Column("field_version", sa.Integer(), nullable=True),
        sa.Column("field_snapshot", sa.JSON(), nullable=True),
        sa.Column("client_request_id", sa.String(64), nullable=True),
        sa.Column("run_mode", sa.String(32), nullable=True),
        sa.Column("data_provenance", sa.String(32), nullable=True),
    ):
        op.add_column("inspection_events", column)
    op.create_foreign_key(
        "fk_inspection_events_field_pk", "inspection_events", "fields", ["field_pk"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_inspection_events_field_pk", "inspection_events", ["field_pk"])
    op.create_unique_constraint(
        "uq_inspection_owner_client_request", "inspection_events", ["owner_user_id", "client_request_id"]
    )

    for column in (
        sa.Column("field_id", sa.String(64), nullable=True),
        sa.Column("field_version", sa.Integer(), nullable=True),
        sa.Column("run_mode", sa.String(32), nullable=True),
        sa.Column("data_provenance", sa.String(32), nullable=True),
        sa.Column("flight_status", sa.JSON(), nullable=True),
    ):
        op.add_column("inspection_records", column)

    op.create_table(
        "task_commands",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("inspection_pk", sa.BigInteger(), nullable=False),
        sa.Column("device_pk", sa.BigInteger(), nullable=False),
        sa.Column("command_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), server_default="PENDING", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("ack_payload", sa.JSON(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["inspection_pk"], ["inspection_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_pk"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id"),
        sa.UniqueConstraint("inspection_pk", "command_type", name="uq_task_command_event_type"),
    )
    op.create_index("ix_task_commands_device_status", "task_commands", ["device_pk", "status"])

    op.create_table(
        "device_latest_data",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_pk", sa.BigInteger(), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("inspection_pk", sa.BigInteger(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["device_pk"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inspection_pk"], ["inspection_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_pk"),
    )


def downgrade() -> None:
    op.drop_table("device_latest_data")
    op.drop_table("task_commands")
    for name in ("flight_status", "data_provenance", "run_mode", "field_version", "field_id"):
        op.drop_column("inspection_records", name)
    op.drop_constraint("uq_inspection_owner_client_request", "inspection_events", type_="unique")
    op.drop_index("ix_inspection_events_field_pk", table_name="inspection_events")
    op.drop_constraint("fk_inspection_events_field_pk", "inspection_events", type_="foreignkey")
    for name in ("data_provenance", "run_mode", "client_request_id", "field_snapshot", "field_version", "field_id", "field_pk"):
        op.drop_column("inspection_events", name)
    op.drop_table("fields")
