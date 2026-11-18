"""Application settings, read once from the environment (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Backend root (the folder that holds `app/`); relative paths in settings resolve against it.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Upload caps from the P1 API contract (WP-I): 5 MB per image, 20 MB per import file.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMPORT_BYTES = 20 * 1024 * 1024

# A pepper or session secret shorter than this is trivially guessable (architecture section 6).
MIN_SECRET_BYTES = 32


class Settings(BaseSettings):
    """All P0 settings. Environment variables use the `VIETRP_` prefix unless an alias says otherwise."""

    model_config = SettingsConfigDict(
        env_prefix="VIETRP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- Required secrets and connections (no defaults on purpose) ---
    # The standard DATABASE_URL name is kept because systemd/env tooling expects it (AGENTS.md section 7).
    database_url: str = Field(
        validation_alias=AliasChoices("DATABASE_URL", "VIETRP_DATABASE_URL"),
        repr=False,
    )
    # Mixed into the vault lookup HMAC; it lives in the environment, never in the DB.
    server_pepper: str = Field(repr=False)
    session_secret: str = Field(repr=False)

    # --- Runtime mode ---
    env: Literal["dev", "prod"] = "dev"
    # Resolved from `env` when left unset: the Secure cookie flag needs HTTPS, which only prod has (via Cloudflare).
    cookie_secure: bool = False
    # Sliding session lifetime: 7 days keeps the home-server user signed in between visits.
    session_ttl_seconds: int = 7 * 24 * 60 * 60

    # --- Vault crypto ---
    # Not secret: a fixed salt makes the lookup deterministic. The secret part is the server pepper.
    global_salt: bytes = b"vietrp-studio/vault-lookup/v1"
    # Argon2id parameters from AGENTS.md section 4.7; tune so unlock takes about 0.5 s on the server.
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 65536
    argon2_parallelism: int = 2

    # --- Passphrase strength (architecture section 6): strong = >= 16 chars, or >= 4 words and >= 12 chars ---
    passphrase_min_chars: int = 16
    passphrase_min_words: int = 4
    passphrase_min_chars_with_words: int = 12

    # --- Unlock rate limit: 10 attempts per 300 s per IP stops brute force but tolerates typos ---
    unlock_rate_limit_attempts: int = 10
    unlock_rate_limit_window_seconds: int = 300
    # Only trust CF-Connecting-IP when the TCP peer is cloudflared on loopback.
    trusted_proxy_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "::1"])

    # --- Secrets the vault may store ---
    allowed_secret_names: list[str] = Field(default_factory=lambda: ["OPENROUTER_API_KEY"])

    # --- OpenRouter (the only LLM provider, AGENTS.md section 2) ---
    openrouter_base_url: str = "https://openrouter.ai"
    # Generous read timeout because reasoning models can be silent for a long time before the first token.
    http_timeout_seconds: float = 120.0
    http_connect_timeout_seconds: float = 10.0
    # Retry 429/5xx up to 3 times with exponential backoff (AGENTS.md section 4.4).
    llm_max_retries: int = 3
    llm_backoff_base_seconds: float = 2.0
    # Per-call Decisions question budget (AGENTS.md section 4.4).
    decisions_max_questions: int = 40

    # --- Uploads (checked from Content-Length before the body is read) ---
    max_image_bytes: int = MAX_IMAGE_BYTES
    max_import_bytes: int = MAX_IMPORT_BYTES

    # --- SSE ---
    # Cloudflare drops idle proxied connections after about 100 s; 15 s leaves a wide margin.
    sse_ping_interval_seconds: int = 15

    # --- Web ---
    # Dev only: the Vite dev server runs on another origin. Prod is same-origin, so CORS stays off.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"])
    frontend_dist_dir: Path = Path("../frontend/dist")

    @model_validator(mode="before")
    @classmethod
    def _default_cookie_secure(cls, data: Any) -> Any:
        if isinstance(data, dict) and "cookie_secure" not in data:
            data = {**data, "cookie_secure": data.get("env", "dev") == "prod"}
        return data

    @field_validator("server_pepper", "session_secret")
    @classmethod
    def _check_secret_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) < MIN_SECRET_BYTES:
            raise ValueError(f"must be at least {MIN_SECRET_BYTES} bytes")
        return value

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("must start with postgresql+asyncpg://")
        return value

    @property
    def frontend_dist_path(self) -> Path:
        """`frontend_dist_dir` resolved against the backend root when relative."""
        if self.frontend_dist_dir.is_absolute():
            return self.frontend_dist_dir
        return (BACKEND_ROOT / self.frontend_dist_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


# --- Pipeline (WP-M) ---
# Hybrid lorebook mode: non-keyword candidates the Orchestrator may judge (bounds the Decisions question budget).
LORE_AI_CANDIDATES = 12
# Fraction of the context window that triggers the Archivist (architecture section 3.1, `memory.summarize_at`).
SUMMARIZE_AT_DEFAULT = 0.8
# Fallback context window when the model's length is unknown.
DEFAULT_CONTEXT_TOKENS = 32000
# Tokens kept free for the model's reply when budgeting the prompt.
RESPONSE_RESERVE_TOKENS = 1024

# --- Single-chat turn (P2 fixes) ---
# Retries after a Director-rejected draft before the best variant is kept (architecture section 5.1: bounded loop).
DIRECTOR_MAX_RETRIES = 2
# Reasoning tokens share the Writer's max_tokens. A live probe (deepseek-v4.1-flash, effort=medium, 2026-11-19)
# spent ~1,100 reasoning tokens on one turn; with the 1,500 base the reply was cut. Added on top when reasoning is on.
WRITER_REASONING_EXTRA_TOKENS = 4000
# Messages loaded as history for one turn; the assembler then trims to the token budget, so this only bounds the query.
TURN_HISTORY_LIMIT = 200
# Recent lines shown to the Orchestrator: enough context to pick a speaker without inflating the Decisions prompt.
ORCHESTRATOR_RECENT_LINES = 6

# --- World-chat agents (WP-U; ported from vietrp-agent/backend/vietrp/engine/group.py) ---
# Min probability for an absent character to be treated as arriving in the scene (group.py: ARRIVE_THRESHOLD).
ARRIVE_THRESHOLD = 0.5
# Presence hysteresis (group.py: update_state): entering requires >= 0.5, leaving requires dropping below 0.2.
PRESENCE_ENTER_THRESHOLD = 0.5
PRESENCE_STAY_THRESHOLD = 0.2
# Min interject/follow-up probability for a present character to chain into the turn (group.py: CHAIN_THRESHOLD).
CHAIN_THRESHOLD = 0.6
# Lower interject threshold when a character owes a reply or just arrived (group.py: OWED_THRESHOLD).
OWED_THRESHOLD = 0.2
# Silent turns before a present character uses the lower quiet threshold (group.py: QUIET_TURNS / QUIET_THRESHOLD).
QUIET_TURNS = 3
QUIET_THRESHOLD = 0.35
# Min confidence on the atomic addressee choice to override the Orchestrator's speaker pick (group.py: ADDRESS_CONF).
ADDRESS_CONFIDENCE = 0.55
# Min confidence to update location_id or time in State Keeper (group.py: update_state).
LOCATION_CONFIDENCE = 0.3
TIME_CONFIDENCE = 0.4

# --- Memory / Archivist (WP-M4; architecture section 5.3, group.py: MAX_FACTS) ---
# Maximum memorable events kept in `chat.state.events` (group.py: MAX_FACTS).
MAX_EVENTS = 24
# Minimum recent messages kept verbatim after automatic compression when context approaches threshold.
ARCHIVIST_KEEP_RECENT = 6
# Recent messages kept verbatim on manual `/summarize` when more than 2 unsummarized messages exist.
ARCHIVIST_MANUAL_KEEP_RECENT = 2

# --- Turn pipeline / Anti-repeat (WP-B5; vietrp-agent/backend/vietrp/turn.py:122) ---
# SequenceMatcher ratio above which a speaker's reply triggers one rewrite attempt.
ANTI_REPEAT_THRESHOLD = 0.6
