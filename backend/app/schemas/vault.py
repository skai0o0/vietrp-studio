"""API schemas for the vault and secrets endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# Cap input size so a huge body cannot turn into a huge Argon2/Fernet job.
MAX_PASSPHRASE_CHARS = 512
MAX_DISPLAY_NAME_CHARS = 40  # WP-D contract
MAX_SECRET_VALUE_CHARS = 4096

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_DISPLAY_NAME_CHARS)]


class UnlockRequest(BaseModel):
    passphrase: str = Field(min_length=1, max_length=MAX_PASSPHRASE_CHARS, repr=False)


class CreateVaultRequest(BaseModel):
    passphrase: str = Field(min_length=1, max_length=MAX_PASSPHRASE_CHARS, repr=False)
    display_name: DisplayName


class UpdateVaultRequest(BaseModel):
    display_name: DisplayName


class VaultOut(BaseModel):
    id: uuid.UUID
    display_name: str
    created_at: datetime


class VaultResponse(BaseModel):
    vault: VaultOut


class UnlockResponse(BaseModel):
    exists: bool
    vault: VaultOut | None = None


class SecretValueIn(BaseModel):
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SECRET_VALUE_CHARS)] = (
        Field(repr=False)
    )


class SecretOut(BaseModel):
    """The value is never part of this model."""

    name: str
    is_set: bool
    hint: str | None = None
    updated_at: datetime | None = None


class SecretResponse(BaseModel):
    secret: SecretOut


class SecretListResponse(BaseModel):
    secrets: list[SecretOut]
