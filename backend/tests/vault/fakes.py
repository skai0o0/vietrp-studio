"""In-memory repositories used by the vault API tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.repositories.secrets_repo import SecretRecord
from app.repositories.vault_repo import DuplicateVaultError, VaultRecord


class FakeVaultRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, VaultRecord] = {}

    async def find_by_lookup(self, lookup_hash: bytes) -> VaultRecord | None:
        return next((v for v in self.rows.values() if v.lookup_hash == lookup_hash), None)

    async def get(self, vault_id: uuid.UUID) -> VaultRecord | None:
        return self.rows.get(vault_id)

    async def create(
        self, *, lookup_hash: bytes, kdf_salt: bytes, wrapped_dek: bytes, display_name: str
    ) -> VaultRecord:
        if await self.find_by_lookup(lookup_hash) is not None:
            raise DuplicateVaultError
        now = datetime.now(UTC)
        record = VaultRecord(uuid.uuid4(), lookup_hash, kdf_salt, wrapped_dek, display_name, now, now)
        self.rows[record.id] = record
        return record

    async def rename(self, vault_id: uuid.UUID, display_name: str) -> VaultRecord | None:
        old = self.rows.get(vault_id)
        if old is None:
            return None
        new = VaultRecord(
            old.id, old.lookup_hash, old.kdf_salt, old.wrapped_dek, display_name, old.created_at, old.last_seen_at
        )
        self.rows[vault_id] = new
        return new

    async def touch(self, vault_id: uuid.UUID) -> None:
        return None

    async def commit(self) -> None:
        return None


class FakeSecretRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, str], SecretRecord] = {}

    async def list(self, vault_id: uuid.UUID) -> list[SecretRecord]:
        return [r for (vid, _), r in self.rows.items() if vid == vault_id]

    async def get(self, vault_id: uuid.UUID, name: str) -> SecretRecord | None:
        return self.rows.get((vault_id, name))

    async def upsert(self, vault_id: uuid.UUID, name: str, ciphertext: bytes, hint: str | None) -> SecretRecord:
        record = SecretRecord(name, ciphertext, hint, datetime.now(UTC))
        self.rows[(vault_id, name)] = record
        return record

    async def delete(self, vault_id: uuid.UUID, name: str) -> None:
        self.rows.pop((vault_id, name), None)

    async def commit(self) -> None:
        return None
