"""Library content: assets, personas, characters, worlds, lorebooks, favorites, presets, creator sessions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    text,
)
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

VISIBILITY_CHECK = "visibility IN ('public','private')"


class Asset(UuidPkMixin, VaultOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "assets"

    kind: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(Text)
    # Python name avoids shadowing the `bytes` builtin; the column is still called `bytes`.
    data_bytes: Mapped[bytes | None] = mapped_column("bytes", LargeBinary, deferred=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)


class Persona(UuidPkMixin, VaultOwnedMixin, TimestampMixin, Base):
    __tablename__ = "personas"

    data: Mapped[dict[str, Any]] = mapped_column()
    avatar_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))


class Character(UuidPkMixin, VaultOwnedMixin, TimestampMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (
        CheckConstraint(VISIBILITY_CHECK, name="visibility"),
        Index("ix_characters_visibility_updated_at", "visibility", "updated_at"),
    )

    visibility: Mapped[str] = mapped_column(Text, server_default="private")
    data: Mapped[dict[str, Any]] = mapped_column()
    avatar_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    judge_score: Mapped[dict[str, Any] | None] = mapped_column()


class World(UuidPkMixin, VaultOwnedMixin, TimestampMixin, Base):
    __tablename__ = "worlds"
    __table_args__ = (
        CheckConstraint(VISIBILITY_CHECK, name="visibility"),
        Index("ix_worlds_visibility_updated_at", "visibility", "updated_at"),
    )

    visibility: Mapped[str] = mapped_column(Text, server_default="private")
    data: Mapped[dict[str, Any]] = mapped_column()
    cover_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    judge_score: Mapped[dict[str, Any] | None] = mapped_column()


class Lorebook(UuidPkMixin, VaultOwnedMixin, TimestampMixin, Base):
    __tablename__ = "lorebooks"
    __table_args__ = (
        CheckConstraint(VISIBILITY_CHECK, name="visibility"),
        Index("ix_lorebooks_visibility_updated_at", "visibility", "updated_at"),
    )

    visibility: Mapped[str] = mapped_column(Text, server_default="private")
    name: Mapped[str] = mapped_column(Text)
    # Book-level options (scan_depth, token_budget, ...) validated by `formats/` in P1.
    settings: Mapped[dict[str, Any]] = mapped_column(server_default=EMPTY_OBJECT)


class LoreEntry(UuidPkMixin, VaultOwnedMixin, TimestampMixin, Base):
    __tablename__ = "lore_entries"

    lorebook_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lorebooks.id", ondelete="CASCADE"), index=True)
    # keys, secondary_keys, selective, constant, priority, position, content, select_mode (architecture 4.4).
    data: Mapped[dict[str, Any]] = mapped_column()
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class LorebookLink(UuidPkMixin, VaultOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "lorebook_links"
    __table_args__ = (
        CheckConstraint("target_type IN ('character','world','chat')", name="target_type"),
        UniqueConstraint("lorebook_id", "target_type", "target_id"),
    )

    lorebook_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lorebooks.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(Text)
    # Polymorphic reference (character, world or chat), so no database-level FK.
    target_id: Mapped[uuid.UUID] = mapped_column()


class Favorite(UuidPkMixin, VaultOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "favorites"
    __table_args__ = (
        CheckConstraint("target_type IN ('character','world')", name="target_type"),
        UniqueConstraint("vault_id", "target_type", "target_id"),
    )

    target_type: Mapped[str] = mapped_column(Text)
    # Polymorphic reference (character or world), so no database-level FK.
    target_id: Mapped[uuid.UUID] = mapped_column()


class PromptPreset(UuidPkMixin, VaultOwnedMixin, TimestampMixin, Base):
    __tablename__ = "prompt_presets"

    agent: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    layers: Mapped[dict[str, Any]] = mapped_column(server_default=EMPTY_OBJECT)


class CreatorSession(UuidPkMixin, VaultOwnedMixin, TimestampMixin, Base):
    __tablename__ = "creator_sessions"
    __table_args__ = (CheckConstraint("mode IN ('slots','chat')", name="mode"),)

    mode: Mapped[str] = mapped_column(Text)
    seed: Mapped[dict[str, Any]] = mapped_column(server_default=EMPTY_OBJECT)
    messages: Mapped[list[Any]] = mapped_column(server_default=EMPTY_ARRAY)
    raw: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column()
