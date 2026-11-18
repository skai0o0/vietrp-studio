"""Chats, messages, variants, memory snapshots and the usage log."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    EMPTY_ARRAY,
    EMPTY_OBJECT,
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UuidPkMixin,
    VaultOwnedMixin,
)


class Chat(UuidPkMixin, VaultOwnedMixin, TimestampMixin, Base):
    __tablename__ = "chats"
    __table_args__ = (CheckConstraint("mode IN ('single','world')", name="mode"),)

    mode: Mapped[str] = mapped_column(Text)
    world_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("worlds.id", ondelete="SET NULL"))
    # Slug of the opening inside the world content (not a row id).
    opening_id: Mapped[str | None] = mapped_column(Text)
    cast_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default=text("'{}'::uuid[]"))
    persona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("personas.id", ondelete="SET NULL"))
    pack: Mapped[dict[str, Any]] = mapped_column(server_default=EMPTY_OBJECT)
    state: Mapped[dict[str, Any]] = mapped_column(server_default=EMPTY_OBJECT)
    settings: Mapped[dict[str, Any]] = mapped_column(server_default=EMPTY_OBJECT)
    parent_chat_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"))
    forked_at_seq: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text, server_default="")


class Message(UuidPkMixin, VaultOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("chat_id", "seq"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(Text)
    active_variant: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    meta: Mapped[dict[str, Any]] = mapped_column(server_default=EMPTY_OBJECT)
    # Exact chat state before this message; undo, fork and swipe depend on it.
    state_before: Mapped[dict[str, Any] | None] = mapped_column()


class MessageVariant(UuidPkMixin, VaultOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "message_variants"
    __table_args__ = (UniqueConstraint("message_id", "idx"),)

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    draft: Mapped[str | None] = mapped_column(Text)
    director: Mapped[dict[str, Any] | None] = mapped_column()
    usage: Mapped[dict[str, Any] | None] = mapped_column()
    # True when the user pressed Stop and only partial text was saved (AGENTS.md section 4.5).
    stopped: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class MemorySnapshot(UuidPkMixin, VaultOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "memory_snapshots"
    __table_args__ = (Index("ix_memory_snapshots_chat_id_upto_seq", "chat_id", "upto_seq"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    upto_seq: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    events: Mapped[list[Any]] = mapped_column(server_default=EMPTY_ARRAY)


class UsageLog(Base):
    __tablename__ = "usage_log"
    __table_args__ = (Index("ix_usage_log_vault_id_created_at", "vault_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    vault_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vaults.id", ondelete="CASCADE"))
    # Keep cost history when a chat is deleted.
    chat_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"))
    agent: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    prompt_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    reasoning_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 7))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
