"""inspection event aggregation

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("operating_status", sa.String(length=16), server_default="SHUTDOWN", nullable=False))
    op.add_column("devices", sa.Column("communication_status", sa.String(length=16), server_default="OFFLINE", nullable=False))
    op.add_column("devices", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "inspection_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("inspection_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), server_default="未命名巡检", nullable=False),
        sa.Column("location_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="CREATED", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inspection_id"),
    )
    op.create_index("ix_inspection_events_owner_started", "inspection_events", ["owner_user_id", "started_at"])
    op.create_index("ix_inspection_events_device", "inspection_events", ["device_id"])
    op.add_column("inspection_records", sa.Column("event_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_inspection_records_event_id", "inspection_records", "inspection_events",
        ["event_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_inspection_records_event_id", "inspection_records", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_inspection_records_event_id", table_name="inspection_records")
    op.drop_constraint("fk_inspection_records_event_id", "inspection_records", type_="foreignkey")
    op.drop_column("inspection_records", "event_id")
    op.drop_table("inspection_events")
    op.drop_column("devices", "last_seen_at")
    op.drop_column("devices", "communication_status")
    op.drop_column("devices", "operating_status")
