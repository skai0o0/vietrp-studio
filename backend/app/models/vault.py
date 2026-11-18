"""Vault and its encrypted secrets."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, LargeBinary, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import EMPTY_OBJECT, Base, CreatedAtMixin, UuidPkMixin


class Vault(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "vaults"

    lookup_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    kdf_salt: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)
    display_name: Mapped[str] = mapped_column(Text)
    settings: Mapped[dict[str, Any]] = mapped_column(server_default=EMPTY_OBJECT)
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Secret(Base):
    __tablename__ = "secrets"

    # The composite PK (vault_id, name) already indexes vault_id as its leading column.
    vault_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vaults.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    hint: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
