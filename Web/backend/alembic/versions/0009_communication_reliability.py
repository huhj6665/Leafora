"""Nullable hardware samples and persisted command delivery / END evidence.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("location_records", "latitude", existing_type=sa.Float(), nullable=True)
    op.alter_column("location_records", "longitude", existing_type=sa.Float(), nullable=True)
    op.alter_column("environment_records", "sampled_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.add_column("task_commands", sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("task_commands", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_commands", sa.Column("accepted_ack_payload", sa.JSON(), nullable=True))
    op.add_column("task_commands", sa.Column("final_ack_payload", sa.JSON(), nullable=True))
    op.create_index("ix_task_commands_retry_due", "task_commands", ["status", "next_attempt_at", "expires_at"])


def downgrade():
    # Never manufacture coordinates/timestamps to force a NOT NULL downgrade.
    connection = op.get_bind()
    if (connection.scalar(sa.text("SELECT count(*) FROM location_records WHERE latitude IS NULL OR longitude IS NULL"))
            or connection.scalar(sa.text("SELECT count(*) FROM environment_records WHERE sampled_at IS NULL"))
            or connection.scalar(sa.text("SELECT count(*) FROM task_commands WHERE accepted_ack_payload IS NOT NULL OR final_ack_payload IS NOT NULL"))):
        raise RuntimeError("Downgrade would discard hardware nulls or END evidence; preserve the database at 0009")
    op.drop_index("ix_task_commands_retry_due", table_name="task_commands")
    for name in ("final_ack_payload", "accepted_ack_payload", "next_attempt_at", "delivery_attempts"):
        op.drop_column("task_commands", name)
    op.alter_column("environment_records", "sampled_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("location_records", "longitude", existing_type=sa.Float(), nullable=False)
    op.alter_column("location_records", "latitude", existing_type=sa.Float(), nullable=False)
