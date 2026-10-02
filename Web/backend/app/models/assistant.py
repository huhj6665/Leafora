"""Assistant-owned persistence; existing inspection tables are never mutated."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database.base import Base, BigIntPK, TimestampMixin


class AssistantConversation(TimestampMixin, Base):
    __tablename__ = "assistant_conversations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100), default="新的对话")
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    active_run_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(40), ForeignKey("assistant_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text, default="")
    attachment_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AssistantRun(Base):
    __tablename__ = "assistant_runs"
    __table_args__ = (UniqueConstraint("conversation_id", "client_request_id", name="uq_assistant_request"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(40), ForeignKey("assistant_conversations.id", ondelete="CASCADE"), index=True)
    user_message_id: Mapped[str] = mapped_column(String(40))
    assistant_message_id: Mapped[str] = mapped_column(String(40))
    client_request_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    model: Mapped[str] = mapped_column(String(100), default="")
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AssistantEvent(Base):
    __tablename__ = "assistant_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_assistant_event"),)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(40), ForeignKey("assistant_runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)


class AssistantDocument(TimestampMixin, Base):
    __tablename__ = "assistant_documents"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16))
    mime_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    chunks: Mapped[list] = mapped_column(JSON, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AssistantFieldContext(TimestampMixin, Base):
    __tablename__ = "assistant_field_contexts"
    __table_args__ = (UniqueConstraint("owner_user_id", "field_id", name="uq_assistant_field_context"),)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"))
    field_id: Mapped[str] = mapped_column(String(64))
    context: Mapped[dict] = mapped_column(JSON, default=dict)
