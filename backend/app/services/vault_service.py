"""Vault use cases: unlock, create, rename, and per-vault secrets."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import Settings
from app.core.deps import SessionDep, SessionStoreDep, SettingsDep
from app.core.errors import AppError
from app.core.sessions import SessionStore, VaultSession
from app.repositories.secrets_repo import SecretRecord, SecretRepository, SqlSecretRepository
from app.repositories.vault_repo import DuplicateVaultError, SqlVaultRepository, VaultRecord, VaultRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OpenedVault:
    vault: VaultRecord
    session: VaultSession


class VaultService:
    def __init__(
        self,
        vaults: VaultRepository,
        secrets_repo: SecretRepository,
        store: SessionStore,
        settings: Settings,
    ) -> None:
        self._vaults = vaults
        self._secrets = secrets_repo
        self._store = store
        self._settings = settings

    # --- vault lifecycle ---

    async def unlock(self, passphrase: str, previous_session_id: str | None = None) -> OpenedVault | None:
        """Open the vault for this passphrase, or None when there is none (no separate wrong-password state)."""
        lookup = await security.derive_lookup(passphrase, self._settings)
        vault = await self._vaults.find_by_lookup(lookup)
        if vault is None:
            return None
        kek = await security.derive_kek(passphrase, vault.kdf_salt, self._settings)
        try:
            dek = security.unwrap_dek(vault.wrapped_dek, kek)
        except security.CryptoError:
            logger.error("Vault %s matched a lookup but its data key could not be unwrapped", vault.id)
            return None
        return await self._open(vault, dek, previous_session_id)

    async def create(self, passphrase: str, display_name: str, previous_session_id: str | None = None) -> OpenedVault:
        if not security.check_strength(passphrase, self._settings):
            raise AppError("passphrase_weak", "Passphrase does not meet the minimum strength", 422)
        lookup = await security.derive_lookup(passphrase, self._settings)
        if await self._vaults.find_by_lookup(lookup) is not None:
            raise AppError("vault_exists", "A vault already exists for this passphrase", 409)
        kdf_salt = security.new_kdf_salt()
        kek = await security.derive_kek(passphrase, kdf_salt, self._settings)
        dek = security.new_dek()
        try:
            vault = await self._vaults.create(
                lookup_hash=lookup,
                kdf_salt=kdf_salt,
                wrapped_dek=security.wrap_dek(dek, kek),
                display_name=display_name,
            )
        except DuplicateVaultError as exc:
            raise AppError("vault_exists", "A vault already exists for this passphrase", 409) from exc
        return await self._open(vault, dek, previous_session_id)

    async def _open(self, vault: VaultRecord, dek: bytes, previous_session_id: str | None) -> OpenedVault:
        await self._vaults.touch(vault.id)
        await self._vaults.commit()
        await self._store.remove(previous_session_id)
        session = await self._store.create(vault.id, dek)
        return OpenedVault(vault, session)

    async def lock(self, session_id: str | None) -> None:
        await self._store.remove(session_id)

    async def get_vault(self, session: VaultSession) -> VaultRecord:
        vault = await self._vaults.get(session.vault_id)
        if vault is None:
            await self._store.remove(session.session_id)
            raise AppError("vault_locked", "Vault no longer exists", 401)
        return vault

    async def rename(self, session: VaultSession, display_name: str) -> VaultRecord:
        vault = await self._vaults.rename(session.vault_id, display_name)
        if vault is None:
            await self._store.remove(session.session_id)
            raise AppError("vault_locked", "Vault no longer exists", 401)
        await self._vaults.commit()
        return vault

    # --- secrets ---

    def _check_name(self, name: str) -> None:
        if name not in self._settings.allowed_secret_names:
            raise AppError("secret_name_invalid", "Secret name is not supported", 400)

    async def list_secrets(self, session: VaultSession) -> list[tuple[str, SecretRecord | None]]:
        stored = {record.name: record for record in await self._secrets.list(session.vault_id)}
        return [(name, stored.get(name)) for name in self._settings.allowed_secret_names]

    async def set_secret(self, session: VaultSession, name: str, value: str) -> SecretRecord:
        self._check_name(name)
        record = await self._secrets.upsert(
            session.vault_id, name, security.encrypt_secret(value, session.dek), security.make_hint(value)
        )
        await self._secrets.commit()
        return record

    async def delete_secret(self, session: VaultSession, name: str) -> None:
        self._check_name(name)
        await self._secrets.delete(session.vault_id, name)
        await self._secrets.commit()

    async def get_secret(self, session: VaultSession, name: str) -> str | None:
        """Decrypted value for server-side use (never returned over the API)."""
        return _decrypt_record(await self._secrets.get(session.vault_id, name), session, name)


def get_vault_service(db: SessionDep, store: SessionStoreDep, settings: SettingsDep) -> VaultService:
    return VaultService(SqlVaultRepository(db), SqlSecretRepository(db), store, settings)


VaultServiceDep = Annotated[VaultService, Depends(get_vault_service)]


def _decrypt_record(record: SecretRecord | None, session: VaultSession, name: str) -> str | None:
    """The one place a stored secret is decrypted for server-side use."""
    if record is None:
        return None
    try:
        return security.decrypt_secret(record.ciphertext, session.dek)
    except security.CryptoError:
        logger.error("Secret %s in vault %s could not be decrypted", name, session.vault_id)
        return None


async def get_secret(db: AsyncSession, session: VaultSession, name: str) -> str | None:
    """Decrypted secret for other services that hold a DB session (the LLM layer gets keys as parameters)."""
    return _decrypt_record(await SqlSecretRepository(db).get(session.vault_id, name), session, name)


__all__ = ["OpenedVault", "VaultService", "VaultServiceDep", "get_secret", "get_vault_service"]
