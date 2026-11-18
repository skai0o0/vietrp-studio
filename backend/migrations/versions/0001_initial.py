"""Initial schema (architecture section 7).

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
EMPTY_OBJECT = sa.text("'{}'::jsonb")
EMPTY_ARRAY = sa.text("'[]'::jsonb")
VISIBILITY_CHECK = "visibility IN ('public','private')"

# Creation order matters for foreign keys; downgrade drops in reverse.
TABLES_IN_ORDER = (
    "vaults",
    "assets",
    "secrets",
    "personas",
    "characters",
    "worlds",
    "lorebooks",
    "lore_entries",
    "lorebook_links",
    "favorites",
    "prompt_presets",
    "creator_sessions",
    "chats",
    "messages",
    "message_variants",
    "memory_snapshots",
    "usage_log",
)


def _id() -> sa.Column[object]:
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _vault_id() -> sa.Column[object]:
    return sa.Column(
        "vault_id", pg.UUID(as_uuid=True), sa.ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False, index=True
    )


def _created_at() -> sa.Column[object]:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW)


def _updated_at() -> sa.Column[object]:
    return sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW)


def _visibility() -> sa.Column[object]:
    return sa.Column("visibility", sa.Text(), nullable=False, server_default="private")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "vaults",
        _id(),
        sa.Column("lookup_hash", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("kdf_salt", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("settings", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        _created_at(),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )

    op.create_table(
        "assets",
        _id(),
        _vault_id(),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("path", sa.Text()),
        sa.Column("bytes", sa.LargeBinary()),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        _created_at(),
    )

    op.create_table(
        "secrets",
        sa.Column("vault_id", pg.UUID(as_uuid=True), sa.ForeignKey("vaults.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("hint", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )

    op.create_table(
        "personas",
        _id(),
        _vault_id(),
        sa.Column("data", pg.JSONB(), nullable=False),
        sa.Column("avatar_asset_id", pg.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="SET NULL")),
        _created_at(),
        _updated_at(),
    )

    op.create_table(
        "characters",
        _id(),
        _vault_id(),
        _visibility(),
        sa.Column("data", pg.JSONB(), nullable=False),
        sa.Column("avatar_asset_id", pg.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="SET NULL")),
        sa.Column("judge_score", pg.JSONB()),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(VISIBILITY_CHECK, name="visibility"),
    )
    op.create_index("ix_characters_visibility_updated_at", "characters", ["visibility", "updated_at"])

    op.create_table(
        "worlds",
        _id(),
        _vault_id(),
        _visibility(),
        sa.Column("data", pg.JSONB(), nullable=False),
        sa.Column("cover_asset_id", pg.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="SET NULL")),
        sa.Column("judge_score", pg.JSONB()),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(VISIBILITY_CHECK, name="visibility"),
    )
    op.create_index("ix_worlds_visibility_updated_at", "worlds", ["visibility", "updated_at"])

    op.create_table(
        "lorebooks",
        _id(),
        _vault_id(),
        _visibility(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("settings", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(VISIBILITY_CHECK, name="visibility"),
    )
    op.create_index("ix_lorebooks_visibility_updated_at", "lorebooks", ["visibility", "updated_at"])

    op.create_table(
        "lore_entries",
        _id(),
        _vault_id(),
        sa.Column(
            "lorebook_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("lorebooks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("data", pg.JSONB(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _created_at(),
        _updated_at(),
    )

    op.create_table(
        "lorebook_links",
        _id(),
        _vault_id(),
        sa.Column(
            "lorebook_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("lorebooks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", pg.UUID(as_uuid=True), nullable=False),
        _created_at(),
        sa.CheckConstraint("target_type IN ('character','world','chat')", name="target_type"),
        sa.UniqueConstraint("lorebook_id", "target_type", "target_id"),
    )

    op.create_table(
        "favorites",
        _id(),
        _vault_id(),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", pg.UUID(as_uuid=True), nullable=False),
        _created_at(),
        sa.CheckConstraint("target_type IN ('character','world')", name="target_type"),
        sa.UniqueConstraint("vault_id", "target_type", "target_id"),
    )

    op.create_table(
        "prompt_presets",
        _id(),
        _vault_id(),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("layers", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        _created_at(),
        _updated_at(),
    )

    op.create_table(
        "creator_sessions",
        _id(),
        _vault_id(),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("seed", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("messages", pg.JSONB(), nullable=False, server_default=EMPTY_ARRAY),
        sa.Column("raw", sa.Text()),
        sa.Column("result", pg.JSONB()),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("mode IN ('slots','chat')", name="mode"),
    )

    op.create_table(
        "chats",
        _id(),
        _vault_id(),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("world_id", pg.UUID(as_uuid=True), sa.ForeignKey("worlds.id", ondelete="SET NULL")),
        sa.Column("opening_id", sa.Text()),
        sa.Column("cast_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default=sa.text("'{}'::uuid[]")),
        sa.Column("persona_id", pg.UUID(as_uuid=True), sa.ForeignKey("personas.id", ondelete="SET NULL")),
        sa.Column("pack", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("state", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("settings", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("parent_chat_id", pg.UUID(as_uuid=True), sa.ForeignKey("chats.id", ondelete="SET NULL")),
        sa.Column("forked_at_seq", sa.Integer()),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("mode IN ('single','world')", name="mode"),
    )

    op.create_table(
        "messages",
        _id(),
        _vault_id(),
        sa.Column(
            "chat_id", pg.UUID(as_uuid=True), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.Text(), nullable=False),
        sa.Column("active_variant", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("meta", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("state_before", pg.JSONB()),
        _created_at(),
        sa.UniqueConstraint("chat_id", "seq"),
    )

    op.create_table(
        "message_variants",
        _id(),
        _vault_id(),
        sa.Column(
            "message_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("draft", sa.Text()),
        sa.Column("director", pg.JSONB()),
        sa.Column("usage", pg.JSONB()),
        sa.Column("stopped", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _created_at(),
        sa.UniqueConstraint("message_id", "idx"),
    )

    op.create_table(
        "memory_snapshots",
        _id(),
        _vault_id(),
        sa.Column("chat_id", pg.UUID(as_uuid=True), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("upto_seq", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("events", pg.JSONB(), nullable=False, server_default=EMPTY_ARRAY),
        _created_at(),
    )
    op.create_index("ix_memory_snapshots_chat_id_upto_seq", "memory_snapshots", ["chat_id", "upto_seq"])

    op.create_table(
        "usage_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("vault_id", pg.UUID(as_uuid=True), sa.ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_id", pg.UUID(as_uuid=True), sa.ForeignKey("chats.id", ondelete="SET NULL")),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost", sa.Numeric(12, 7)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_usage_log_vault_id_created_at", "usage_log", ["vault_id", "created_at"])


def downgrade() -> None:
    for table in reversed(TABLES_IN_ORDER):
        op.drop_table(table)
    # pgcrypto is left installed: other objects in the database may rely on it.
