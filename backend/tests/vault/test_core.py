from __future__ import annotations

import unicodedata

import pytest

from app.core import security
from app.core.client_ip import resolve_client_ip
from app.core.config import Settings
from app.core.ratelimit import SlidingWindowLimiter
from app.core.sessions import SessionStore
from tests.conftest import make_settings
from tests.vault.conftest import FAST_ARGON2

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def cfg() -> Settings:
    return make_settings(**FAST_ARGON2)


def test_lookup_is_deterministic(cfg: Settings) -> None:
    assert security.derive_lookup_sync(PASSPHRASE, cfg) == security.derive_lookup_sync(PASSPHRASE, cfg)
    assert security.derive_lookup_sync(PASSPHRASE, cfg) != security.derive_lookup_sync(PASSPHRASE + "!", cfg)


def test_lookup_normalizes_unicode(cfg: Settings) -> None:
    composed = "Việt Nam là một đất nước xinh đẹp"
    decomposed = unicodedata.normalize("NFD", composed)
    assert decomposed != composed
    assert security.derive_lookup_sync(composed, cfg) == security.derive_lookup_sync(decomposed, cfg)


def test_different_peppers_give_different_lookups() -> None:
    a = make_settings(server_pepper="a" * 40, **FAST_ARGON2)
    b = make_settings(server_pepper="b" * 40, **FAST_ARGON2)
    assert security.derive_lookup_sync(PASSPHRASE, a) != security.derive_lookup_sync(PASSPHRASE, b)


async def test_async_derivation_matches_sync(cfg: Settings) -> None:
    assert await security.derive_lookup(PASSPHRASE, cfg) == security.derive_lookup_sync(PASSPHRASE, cfg)


def test_kek_depends_on_salt(cfg: Settings) -> None:
    s1, s2 = security.new_kdf_salt(), security.new_kdf_salt()
    assert len(s1) == 16 and s1 != s2
    assert security.derive_kek_sync(PASSPHRASE, s1, cfg) != security.derive_kek_sync(PASSPHRASE, s2, cfg)
    assert len(security.derive_kek_sync(PASSPHRASE, s1, cfg)) == 32


def test_wrap_unwrap_and_wrong_kek(cfg: Settings) -> None:
    salt = security.new_kdf_salt()
    kek = security.derive_kek_sync(PASSPHRASE, salt, cfg)
    dek = security.new_dek()
    wrapped = security.wrap_dek(dek, kek)
    assert security.unwrap_dek(wrapped, kek) == dek
    wrong = security.derive_kek_sync("a different passphrase entirely", salt, cfg)
    with pytest.raises(security.CryptoError):
        security.unwrap_dek(wrapped, wrong)


def test_secret_encrypt_decrypt_and_wrong_dek() -> None:
    dek = security.new_dek()
    token = security.encrypt_secret("sk-dummy-value-12345678", dek)
    assert b"sk-dummy" not in token
    assert security.decrypt_secret(token, dek) == "sk-dummy-value-12345678"
    with pytest.raises(security.CryptoError):
        security.decrypt_secret(token, security.new_dek())


def test_hint() -> None:
    assert security.make_hint("sk-dummy-value-12345678") == "5678"
    assert security.make_hint("short") is None


@pytest.mark.parametrize(
    ("passphrase", "ok"),
    [
        ("a" * 16, True),
        ("a" * 15, False),
        ("one two three four", True),
        ("a b c d", False),  # four words but too short
        ("ab cd ef gh", False),  # 11 chars
        ("abc def ghi jkl", True),  # 4 words, 15 chars
        ("one two three", False),  # 3 words, 13 chars
    ],
)
def test_strength_rule(cfg: Settings, passphrase: str, ok: bool) -> None:
    assert security.check_strength(passphrase, cfg) is ok


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_session_ttl_slides_and_expires() -> None:
    clock = Clock()
    store = SessionStore(100, clock)
    import uuid

    session = await store.create(uuid.uuid4(), b"dek")
    clock.now += 60
    assert await store.get(session.session_id) is not None  # slides to +100 from now
    clock.now += 60
    assert await store.get(session.session_id) is not None
    clock.now += 101
    assert await store.get(session.session_id) is None
    assert await store.get(None) is None
    assert await store.get("missing") is None


async def test_session_remove_and_purge() -> None:
    import uuid

    clock = Clock()
    store = SessionStore(10, clock)
    a = await store.create(uuid.uuid4(), b"a")
    b = await store.create(uuid.uuid4(), b"b")
    await store.remove(a.session_id)
    assert await store.get(a.session_id) is None
    clock.now += 11
    assert await store.purge_expired() == 1
    assert await store.get(b.session_id) is None


def test_session_repr_hides_dek() -> None:
    import uuid

    from app.core.sessions import VaultSession

    assert "secret-dek" not in repr(VaultSession("sid", uuid.uuid4(), b"secret-dek", 1.0))


def test_client_ip_trust_rules() -> None:
    trusted = ["127.0.0.1", "::1"]
    assert resolve_client_ip("127.0.0.1", "203.0.113.9", trusted) == "203.0.113.9"
    assert resolve_client_ip("::1", "2001:db8::1", trusted) == "2001:db8::1"
    # Untrusted peer: the header is spoofable and must be ignored.
    assert resolve_client_ip("198.51.100.7", "203.0.113.9", trusted) == "198.51.100.7"
    # Trusted peer without or with a garbage header falls back to the peer.
    assert resolve_client_ip("127.0.0.1", None, trusted) == "127.0.0.1"
    assert resolve_client_ip("127.0.0.1", "not-an-ip", trusted) == "127.0.0.1"
    assert resolve_client_ip(None, None, trusted) == "unknown"


def test_rate_limiter_window() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(3, 60, clock)
    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]
    assert limiter.hit("a") == 60
    assert limiter.hit("b") is None  # other IPs are independent
    clock.now += 30
    assert limiter.hit("a") == 30
    clock.now += 31
    assert limiter.hit("a") is None  # the window slid past the first hits
