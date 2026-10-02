"""Add assistant-only tables, leaving all business data intact."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None
BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def owner(nullable=False):
    return sa.Column("owner_user_id", BIGINT, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=nullable)


def conversation():
    return sa.Column("conversation_id", sa.String(40), sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False)


def upgrade():
    # Frozen schema: historical migrations must not import mutable application models.
    op.create_table("assistant_conversations", sa.Column("id", sa.String(40), primary_key=True), owner(),
                    sa.Column("title", sa.String(100), nullable=False), sa.Column("context", sa.JSON(), nullable=False),
                    sa.Column("active_run_id", sa.String(40)), *timestamps())
    op.create_table("assistant_messages", sa.Column("id", sa.String(40), primary_key=True), conversation(),
                    sa.Column("role", sa.String(12), nullable=False), sa.Column("content", sa.Text(), nullable=False),
                    sa.Column("attachment_ids", sa.JSON(), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False),
                    sa.Column("status", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("assistant_runs", sa.Column("id", sa.String(40), primary_key=True), owner(), conversation(),
                    sa.Column("user_message_id", sa.String(40), nullable=False), sa.Column("assistant_message_id", sa.String(40), nullable=False),
                    sa.Column("client_request_id", sa.String(64), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
                    sa.Column("request", sa.JSON(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
                    sa.Column("model", sa.String(100), nullable=False), sa.Column("usage", sa.JSON(), nullable=False),
                    sa.Column("error", sa.String(500)), sa.UniqueConstraint("conversation_id", "client_request_id", name="uq_assistant_request"),
                    *timestamps())
    op.create_table("assistant_events", sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
                    sa.Column("run_id", sa.String(40), sa.ForeignKey("assistant_runs.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("kind", sa.String(20), nullable=False),
                    sa.Column("payload", sa.JSON(), nullable=False), sa.UniqueConstraint("run_id", "sequence", name="uq_assistant_event"))
    op.create_table("assistant_documents", sa.Column("id", sa.String(40), primary_key=True), owner(nullable=True),
                    sa.Column("title", sa.String(255), nullable=False), sa.Column("kind", sa.String(16), nullable=False),
                    sa.Column("mime_type", sa.String(100), nullable=False), sa.Column("storage_key", sa.String(100), nullable=False),
                    sa.Column("byte_size", sa.Integer(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False),
                    sa.Column("chunks", sa.JSON(), nullable=False), sa.Column("metadata", sa.JSON(), nullable=False),
                    sa.Column("deleted_at", sa.DateTime(timezone=True)), *timestamps())
    op.create_table("assistant_field_contexts", sa.Column("id", BIGINT, primary_key=True, autoincrement=True), owner(),
                    sa.Column("field_id", sa.String(64), nullable=False), sa.Column("context", sa.JSON(), nullable=False),
                    sa.UniqueConstraint("owner_user_id", "field_id", name="uq_assistant_field_context"), *timestamps())
    for table, columns in {"assistant_conversations": ["owner_user_id"], "assistant_messages": ["conversation_id"],
                           "assistant_runs": ["owner_user_id", "conversation_id", "updated_at"], "assistant_events": ["run_id"],
                           "assistant_documents": ["owner_user_id"]}.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in ("assistant_field_contexts", "assistant_documents", "assistant_events", "assistant_runs", "assistant_messages", "assistant_conversations"):
        op.drop_table(table)
