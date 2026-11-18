"""Vault cryptography (AGENTS.md section 4.7, architecture section 6).

- lookup  = HMAC-SHA256(server_pepper, Argon2id(passphrase, global_salt))
- KEK     = Argon2id(passphrase, vault.kdf_salt), used as a Fernet key
- wrapped = Fernet(KEK).encrypt(DEK); secrets = Fernet(DEK).encrypt(value)

Nothing here logs or returns key material in error messages.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import unicodedata

import anyio
from argon2.low_level import Type, hash_secret_raw
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings

KDF_SALT_BYTES = 16  # per-vault random salt for the KEK (WP-D spec)
DERIVED_KEY_BYTES = 32  # Fernet needs a 32-byte key
HINT_CHARS = 4  # last characters shown to identify a stored key
# Below this a "last 4" hint would reveal most of the value, so no hint is stored.
HINT_MIN_VALUE_CHARS = 8


class CryptoError(Exception):
    """Unwrapping or decrypting failed (wrong key or corrupted data)."""


def normalize_passphrase(passphrase: str) -> bytes:
    """NFC-normalize so the same Vietnamese text typed on different devices derives the same keys."""
    return unicodedata.normalize("NFC", passphrase).encode("utf-8")


def check_strength(passphrase: str, settings: Settings) -> bool:
    """Strong = at least `passphrase_min_chars` characters, or enough words and a shorter minimum length."""
    text = passphrase.strip()
    if len(text) >= settings.passphrase_min_chars:
        return True
    words = text.split()
    return len(words) >= settings.passphrase_min_words and len(text) >= settings.passphrase_min_chars_with_words


def _argon2_raw(secret: bytes, salt: bytes, settings: Settings) -> bytes:
    return hash_secret_raw(
        secret=secret,
        salt=salt,
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost_kib,
        parallelism=settings.argon2_parallelism,
        hash_len=DERIVED_KEY_BYTES,
        type=Type.ID,
    )


def derive_lookup_sync(passphrase: str, settings: Settings) -> bytes:
    inner = _argon2_raw(normalize_passphrase(passphrase), settings.global_salt, settings)
    return hmac.new(settings.server_pepper.encode("utf-8"), inner, hashlib.sha256).digest()


def derive_kek_sync(passphrase: str, kdf_salt: bytes, settings: Settings) -> bytes:
    return _argon2_raw(normalize_passphrase(passphrase), kdf_salt, settings)


async def derive_lookup(passphrase: str, settings: Settings) -> bytes:
    """Argon2 is CPU- and memory-heavy, so it runs off the event loop."""
    return await anyio.to_thread.run_sync(derive_lookup_sync, passphrase, settings)


async def derive_kek(passphrase: str, kdf_salt: bytes, settings: Settings) -> bytes:
    return await anyio.to_thread.run_sync(derive_kek_sync, passphrase, kdf_salt, settings)


def new_kdf_salt() -> bytes:
    return secrets.token_bytes(KDF_SALT_BYTES)


def new_dek() -> bytes:
    """A random Fernet key (urlsafe-base64 of 32 random bytes)."""
    return Fernet.generate_key()


def _fernet_from_raw(key: bytes) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(key))


def wrap_dek(dek: bytes, kek: bytes) -> bytes:
    return _fernet_from_raw(kek).encrypt(dek)


def unwrap_dek(wrapped_dek: bytes, kek: bytes) -> bytes:
    try:
        return _fernet_from_raw(kek).decrypt(wrapped_dek)
    except InvalidToken as exc:
        raise CryptoError("Could not unwrap the data key") from exc


def encrypt_secret(value: str, dek: bytes) -> bytes:
    return Fernet(dek).encrypt(value.encode("utf-8"))


def decrypt_secret(ciphertext: bytes, dek: bytes) -> str:
    try:
        return Fernet(dek).decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError("Could not decrypt the secret") from exc


def make_hint(value: str) -> str | None:
    if len(value) < HINT_MIN_VALUE_CHARS:
        return None
    return value[-HINT_CHARS:]
