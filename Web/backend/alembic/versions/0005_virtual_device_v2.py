"""virtual device v2 telemetry

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("device_status_records", sa.Column("storage_usage", sa.Float(), nullable=True))
    op.add_column("device_status_records", sa.Column("network_status", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("device_status_records", "network_status")
    op.drop_column("device_status_records", "storage_usage")
