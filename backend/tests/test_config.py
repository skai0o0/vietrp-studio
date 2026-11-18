from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_ROOT, Settings
from tests.conftest import DUMMY_DATABASE_URL, DUMMY_PEPPER, DUMMY_SESSION_SECRET, make_settings


def test_defaults() -> None:
    settings = make_settings()
    assert settings.env == "dev"
    assert settings.cookie_secure is False
    assert settings.session_ttl_seconds == 7 * 24 * 3600
    assert (settings.argon2_time_cost, settings.argon2_memory_cost_kib, settings.argon2_parallelism) == (3, 65536, 2)
    assert settings.allowed_secret_names == ["OPENROUTER_API_KEY"]
    assert settings.trusted_proxy_hosts == ["127.0.0.1", "::1"]
    assert settings.sse_ping_interval_seconds == 15
    assert settings.decisions_max_questions == 40


def test_prod_sets_cookie_secure() -> None:
    assert make_settings(env="prod").cookie_secure is True


def test_explicit_cookie_secure_wins() -> None:
    assert make_settings(env="prod", cookie_secure=False).cookie_secure is False


def test_missing_pepper_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # The dev .env may be exported into the shell; the test must not see it.
    monkeypatch.delenv("VIETRP_SERVER_PEPPER", raising=False)
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]
            _env_file=None, database_url=DUMMY_DATABASE_URL, session_secret=DUMMY_SESSION_SECRET
        )


def test_short_pepper_fails() -> None:
    with pytest.raises(ValidationError):
        make_settings(server_pepper="too-short")


def test_database_url_must_be_asyncpg() -> None:
    with pytest.raises(ValidationError):
        make_settings(database_url="postgresql://user@host/db")


def test_env_vars_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)
    monkeypatch.setenv("VIETRP_SERVER_PEPPER", DUMMY_PEPPER)
    monkeypatch.setenv("VIETRP_SESSION_SECRET", DUMMY_SESSION_SECRET)
    monkeypatch.setenv("VIETRP_ENV", "prod")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database_url == DUMMY_DATABASE_URL
    assert settings.env == "prod"
    assert settings.cookie_secure is True


def test_secrets_not_in_repr() -> None:
    text = repr(make_settings())
    assert DUMMY_PEPPER not in text
    assert DUMMY_SESSION_SECRET not in text
    assert "user:pw" not in text


def test_relative_frontend_dist_resolves_against_backend_root() -> None:
    assert (
        make_settings(frontend_dist_dir=Path("../frontend/dist")).frontend_dist_path
        == (BACKEND_ROOT / "../frontend/dist").resolve()
    )
    absolute = Path.cwd().resolve()
    assert make_settings(frontend_dist_dir=absolute).frontend_dist_path == absolute
