# P0 — Foundation: work packages

Phase goal (KIEN-TRUC-VIETRP.md §13, P0): a running skeleton covering repo layout, DB schema + Alembic, passphrase vault, OpenRouter client + Decisions, tokenizer, and the frontend shell (layout, 2 themes, router, i18n). **No chat, no library CRUD, no agents.** Those start in P1.

## Team

| Role | Agent file | Model | Does |
|---|---|---|---|
| Lead | (main session) | Opus | Splits work, writes contracts, reviews, integrates |
| backend-builder | `.claude/agents/backend-builder.md` | Sonnet | Backend WPs |
| frontend-builder | `.claude/agents/frontend-builder.md` | Sonnet | Frontend WPs |
| ops-builder | `.claude/agents/ops-builder.md` | Haiku | Deploy/ops WPs |
| qa-runner | `.claude/agents/qa-runner.md` | Haiku | Runs gates + rule greps, never edits |
| lead-reviewer | `.claude/agents/lead-reviewer.md` | Opus | Optional independent review |

## Waves

| Wave | WPs (run in parallel) | Depends on |
|---|---|---|
| 1 | **A** backend foundation · **B** frontend shell · **C** deploy | — |
| 2 | **D** vault backend · **E** LLM layer · **F** frontend vault + API key UI | A (D, E), B (F); F codes against the contract in WP-D |
| 3 | qa-runner → lead review → fixes | 1, 2 |

**File ownership is exclusive within a wave.** Builders never edit files outside their list. If they need such a change, they report it under "Needs from other WPs".

Shared constants (every WP uses these):
- Backend port in dev and prod: `7880` (uvicorn binds `127.0.0.1:7880`).
- Frontend dev port: `5173`; Vite proxies `/api` → `http://127.0.0.1:7880`.
- Session cookie name: `vietrp_session`.
- Error body: `{"error": {"code": "<snake_case>", "message": "<English>"}}`.

---

## WP-A · Backend foundation (backend-builder)

**Owns:**
- `vietrp-studio/.gitignore`, `vietrp-studio/.env.example`, `vietrp-studio/README.md`
- `backend/pyproject.toml`, `backend/uv.lock`, `backend/.python-version`, `backend/alembic.ini`, `backend/README.md`
- `backend/app/__init__.py`, `backend/app/main.py`
- `backend/app/core/{__init__,config,db,errors,deps}.py`
- `backend/app/models/**`
- `backend/migrations/**`
- `backend/tests/{conftest.py,test_health.py,test_config.py,test_errors.py,test_migrations.py}`
- empty `__init__.py` packages: `api/`, `services/`, `repositories/`, `schemas/`, `formats/`, `agents/`, `pipeline/`, `llm/`, `prompts/`, `creator/pools/` (keep an empty `.gitkeep` there)

**Build:**
1. uv project, `requires-python = "==3.12.*"`. Pin exact versions. Add **every** P0 runtime dependency now, so wave 2 does not touch `pyproject.toml`:
   - runtime: fastapi, uvicorn[standard], pydantic, pydantic-settings, sqlalchemy[asyncio], asyncpg, alembic, httpx, tiktoken, argon2-cffi, cryptography, jinja2, sse-starlette;
   - dev: pytest, pytest-asyncio, ruff, mypy.
   - Configure ruff (line length 120, isort rules), mypy strict for `app/`, and pytest (`asyncio_mode = "auto"`, marker `live`).
2. `core/config.py`: a pydantic-settings `Settings` object, read once (cached). It holds **all** P0 settings below; each has a comment saying why it has that value.

   | Field | Env var | Default |
   |---|---|---|
   | `database_url` | `DATABASE_URL` | required; `postgresql+asyncpg://…` |
   | `server_pepper` | `VIETRP_SERVER_PEPPER` | required, ≥ 32 bytes |
   | `session_secret` | `VIETRP_SESSION_SECRET` | required |
   | `env` | `VIETRP_ENV` | `"dev"`; or `"prod"` |
   | `cookie_secure` | | true when env = prod |
   | `session_ttl_seconds` | | 7 days, sliding |
   | `global_salt` | | constant bytes; not secret, documented as such |
   | `argon2_time_cost`, `argon2_memory_cost_kib`, `argon2_parallelism` | | 3, 65536, 2 |
   | `passphrase_min_chars` | | 16 |
   | `passphrase_min_words`, `passphrase_min_chars_with_words` | | 4, 12 (strong = ≥16 chars, or ≥4 words and ≥12 chars) |
   | `unlock_rate_limit` | | 10 attempts / 300 s per IP |
   | `trusted_proxy_hosts` | | `["127.0.0.1", "::1"]` |
   | `allowed_secret_names` | | `["OPENROUTER_API_KEY"]` |
   | `openrouter_base_url` | | `https://openrouter.ai` |
   | `http_timeout_seconds`, `http_connect_timeout_seconds` | | 120, 10 |
   | `llm_max_retries`, `llm_backoff_base_seconds` | | 3, 2.0 |
   | `decisions_max_questions` | | 40 |
   | `sse_ping_interval_seconds` | | 15 (Cloudflare idles out at ~100 s) |
   | `cors_origins` | | `["http://127.0.0.1:5173", "http://localhost:5173"]`, dev only |
   | `frontend_dist_dir` | | `../frontend/dist` |
3. `core/db.py`: async engine and session factory; `get_session` dependency (one transaction per request; services commit).
4. `core/errors.py`: `AppError(code, message, status)`, plus handlers that turn `AppError`, validation errors (`validation_error`, 422) and unhandled errors (`internal_error`, 500, no stack trace in the body) into the standard error body.
5. `main.py`: `create_app()`.
   - `GET /api/health` → `{"status": "ok", "version": "<from package>"}`.
   - CORS only when env = dev.
   - Serves `frontend_dist_dir` as static files with SPA fallback for non-`/api` paths, only if the directory exists.
   - Mounts routers from `app.api` through one `include_routers(app)` function in `app/api/__init__.py`. That file stays an empty registry in WP-A; WP-D adds its routers there.
6. `models/`: SQLAlchemy 2 typed models for **every table in KIEN-TRUC §7**:
   - `vaults`, `secrets`, `personas`, `characters`, `worlds`, `lorebooks`, `lore_entries`, `lorebook_links`, `favorites`, `prompt_presets`, `creator_sessions`, `chats`, `messages`, `message_variants`, `memory_snapshots`, `usage_log`, `assets`.
   - Rules:
     - UUID PKs default `gen_random_uuid()`; `usage_log.id` is a bigint identity.
     - `timestamptz` defaults `now()`; `jsonb` for `data`, `state`, `meta`, `settings`, etc.
     - Every owned table has `vault_id` FK → `vaults.id ON DELETE CASCADE`, indexed.
     - `visibility` has CHECK `('public','private')` default `'private'`, with an index on `(visibility, updated_at)`.
     - `chats.mode` CHECK `('single','world')`; `chats.parent_chat_id` self-FK `ON DELETE SET NULL`.
     - `messages` UNIQUE `(chat_id, seq)`; `message_variants` UNIQUE `(message_id, idx)`.
     - `secrets` PK `(vault_id, name)`, columns `ciphertext bytea`, `hint text`, `updated_at`.
     - `vaults`: `lookup_hash bytea UNIQUE`, `kdf_salt bytea`, `wrapped_dek bytea`, `display_name text`, `settings jsonb default '{}'`, `created_at`, `last_seen_at`.
     - `lorebook_links`: `(lorebook_id, target_type CHECK in ('character','world','chat'), target_id)` UNIQUE.
     - `favorites`: `(vault_id, target_type CHECK in ('character','world'), target_id)` UNIQUE.
     - `assets`: `kind`, `mime`, `path text null`, `bytes bytea null`, `size_bytes`.
     - `usage_log`: `vault_id`, `chat_id null`, `agent`, `model`, `prompt_tokens`, `completion_tokens`, `reasoning_tokens`, `cost numeric(12,7) null`, `created_at`, with an index on `(vault_id, created_at)`.
7. Alembic, async env. Migration `0001_initial` creates everything above and enables `pgcrypto`. No `create_all` at runtime.
8. Tests:
   - health endpoint;
   - error body shape for `AppError`, 422 and 500;
   - settings validation (missing pepper fails; prod sets cookie_secure);
   - `test_migrations.py` runs `upgrade head` then `downgrade base` against `VIETRP_TEST_DATABASE_URL`, and skips when that is unset.
9. `vietrp-studio/README.md`: what the project is (2–3 lines), the folder map, links to `AGENTS.md`/architecture, and dev quickstart for backend + frontend. `.env.example` lists every env var with placeholders. `.gitignore` covers Python, Node, `.env*` except `.env.example`, `dist`, `.venv`.

**Done when:** the gates pass (`ruff format --check`, `ruff check`, `mypy app`, `pytest`), and `uv run uvicorn app.main:app --port 7880` starts with dummy env values and answers `/api/health`.

---

## WP-B · Frontend shell (frontend-builder)

**Owns:** everything under `vietrp-studio/frontend/` except `src/features/vault/**` and `src/features/settings/**`, which are reserved for WP-F. WP-B creates only placeholder pages for those two.

**Build:**
1. Vite + React 18 + TS (`strict`, `noUncheckedIndexedAccess`), TailwindCSS 3, shadcn/ui (`components.json`). Add the primitives P0/P1 needs: button, input, label, dialog, sheet, tooltip, dropdown-menu, tabs, switch, separator, scroll-area, toast/sonner. Also lucide-react, framer-motion, @tanstack/react-query, zustand, react-router-dom, Vitest + Testing Library + jsdom, ESLint (typescript-eslint, react-hooks, jsx-a11y), and Prettier. Exact versions only. Scripts: `dev`, `build`, `preview`, `lint`, `typecheck`, `test`, `format`.
2. Fonts: self-hosted via `@fontsource` (no CDN). The sans font must have full Vietnamese support (e.g. Be Vietnam Pro); the serif for E-ink chat content must too (e.g. Noto Serif).
3. **Themes** (`src/styles/themes/oled-neon.css`, `e-ink.css`): CSS variables on `[data-theme=…]`. Semantic tokens at least:
   - `--bg`, `--surface`, `--surface-2`, `--border`, `--text`, `--text-muted`;
   - `--accent`, `--accent-2`, `--danger`, `--focus`;
   - `--glow` (`none` in e-ink), `--radius`, `--font-sans`, `--font-content`, `--motion` (`1`/`0`).

   Map them in `tailwind.config.ts` as semantic utilities (`bg-surface`, `text-muted`, `shadow-glow`, …). OLED Neon follows glow's palette (`viet-rp-glow/tailwind.config.ts`), with a true `#000` base. E-ink is paper-white, black text, 1px borders, with no shadow, glow, gradient or motion. Theme state lives in a small Zustand store (`src/app/theme.ts`) persisted to `localStorage` in try/catch, defaults to `oled-neon`, and applies `data-theme` on `<html>` before first paint (inline script in `index.html`).
4. `useReducedMotion()` returns true for e-ink or `prefers-reduced-motion`. All framer-motion usage goes through shared variants in `src/lib/motion.ts` that respect it.
5. **i18n:** `src/i18n/vi.ts` is a nested object with all strings, plus a typed `t("a.b.c", params?)` (keys type-checked) and `errorMessage(code)` that maps backend error codes to Vietnamese, with a generic fallback. Seed it with the nav labels, page titles and the P0 error codes:
   - `validation_error`, `internal_error`, `vault_locked`, `vault_not_found`, `vault_exists`;
   - `passphrase_weak`, `rate_limited`, `secret_name_invalid`, `network_error`.
6. **Routing** (KIEN-TRUC §9.2), with placeholder pages that show a title and an empty state:
   - `/` Gallery, `/chat/:chatId`;
   - `/library/characters`, `/library/worlds`, `/library/lorebooks`, `/library/personas`;
   - `/characters/:id`, `/worlds/:id`, `/create`, `/settings`;
   - plus a 404 page.

   Lazy-load the pages.
7. **AppLayout** (KIEN-TRUC §9.1, AGENTS.md §5.3):
   - ≥1280px: collapsed IconRail on the left (icons + tooltip), optional LeftSidebar, Main, optional RightSidebar.
   - 768–1279px: IconRail + Main; sidebars open as `Sheet`s.
   - <768px: BottomNav with 5 items max + Main; sidebars as drawer/bottom sheet.
   - Pages declare their sidebars through a small `usePageChrome({ left?, right? })` API, so later phases can plug in the chat list and the state panel.
   - Use `100dvh`, handle safe-area insets, add a skip link, and a visible focus ring.
   - The IconRail bottom has a theme toggle and a slot `railFooter` that WP-F fills with the lock button.
8. **lib:**
   - `apiClient.ts`: fetch wrapper with `credentials: "include"`, JSON in/out, throwing `ApiError {status, code, message}`; network failures map to `network_error`.
   - `sse.ts`: a POST-capable SSE client over `fetch` + `ReadableStream`, because EventSource cannot POST. It parses `event:`/`data:` lines into typed `{event, data}`, handles `ping` silently, supports `AbortSignal`, and calls `onEvent`, `onError`, `onDone`. It does not reconnect automatically for POST turns.
   - `cn.ts`.
   - `queryClient.ts`: TanStack Query with sane defaults; 401 `vault_locked` invalidates the `["vault","me"]` query.
9. `vite.config.ts`: `@` alias, `/api` proxy → `http://127.0.0.1:7880`, Vitest config (jsdom).
10. Tests:
    - `sse.ts` parser (multi-line data, split chunks, ping ignored, abort);
    - `t()` interpolation and `errorMessage` fallback;
    - the theme store applies `data-theme`;
    - AppLayout renders the BottomNav at a mobile width and the IconRail at desktop (matchMedia mock).

**Done when:** the gates pass (`lint`, `typecheck`, `test`, `build`), and the shell has been checked at 375px and 1440px in both themes.

---

## WP-C · Deploy (ops-builder)

**Owns:** `vietrp-studio/deploy/**`.

**Build:**
1. `deploy/systemd/vietrp-api.service`:
   - user `vietrp`, `WorkingDirectory=/opt/vietrp/backend`, `EnvironmentFile=/etc/vietrp/vietrp.env`;
   - `ExecStartPre` runs `alembic upgrade head`; `ExecStart` runs uvicorn on `127.0.0.1:7880` (via the uv-managed venv) with `--proxy-headers --forwarded-allow-ips=127.0.0.1`;
   - `Restart=on-failure`, plus hardening.
2. `deploy/systemd/vietrp-backup.service` + `vietrp-backup.timer` (daily, `Persistent=true`), and `deploy/scripts/backup.sh`: `pg_dump -Fc` to `/var/backups/vietrp/`, keep the last 14, `umask 077`.
3. `deploy/scripts/env.example`: same keys as `vietrp-studio/.env.example`, with prod notes.
4. `deploy/README.md` (Vietnamese), step by step for Debian 12:
   - create user `vietrp` and `/opt/vietrp`;
   - install PostgreSQL 17 from the PGDG apt repo; create role + DB; listen on localhost only;
   - install uv and Node (for building the frontend);
   - build the frontend; `uv sync --frozen`;
   - write `/etc/vietrp/vietrp.env` (mode 600) and generate secrets (`openssl rand -hex 32`);
   - enable the services.
   - **Cloudflare Tunnel from the Zero Trust dashboard:** create the tunnel → choose Debian → install `cloudflared` as a service using the token command the dashboard shows → Public Hostname `<your domain>` → Service `http://127.0.0.1:7880`.
   - Notes: no port forwarding; never use `trycloudflare`; SSE works through the tunnel, and the app pings every 15 s; optional Cloudflare Access policy.
   - Updating, restoring from backup, and where the pepper and env file must be backed up (separately from dumps; losing the pepper = every vault becomes unreachable).
   - Health check: `curl http://127.0.0.1:7880/api/health`.

**Done when:** `bash -n` passes on the scripts (and shellcheck, if available), and the README walks a fresh Debian 12 box to a working tunnel.

---

## WP-D · Vault backend (backend-builder) — wave 2

**Owns:**
- `app/core/security.py`, `app/core/sessions.py`, `app/core/ratelimit.py`, `app/core/client_ip.py`
- `app/api/__init__.py` (register routers only), `app/api/vault.py`, `app/api/secrets.py`
- `app/schemas/vault.py`
- `app/services/vault_service.py`
- `app/repositories/{__init__,vault_repo,secrets_repo}.py`
- additions to `app/core/deps.py` (`require_vault`, `get_vault_session`)
- `tests/vault/**`

**Crypto** (AGENTS.md §4.7, KIEN-TRUC §6):
- `derive_lookup(passphrase) = HMAC-SHA256(server_pepper, Argon2id(passphrase, global_salt))`.
- `derive_kek(passphrase, kdf_salt) = Argon2id(passphrase, kdf_salt)`, 32 bytes, used as a Fernet key (urlsafe-b64).
- New vault: random 16-byte `kdf_salt`; random Fernet DEK; `wrapped_dek = Fernet(KEK).encrypt(DEK)`.
- Secrets: `ciphertext = Fernet(DEK).encrypt(value)`; `hint` = last 4 chars.
- Argon2 runs via `anyio.to_thread.run_sync`.
- `check_strength(passphrase)` follows the config rule.

**Sessions:**
- In-memory store `session_id (secrets.token_urlsafe(32)) → {vault_id, dek, expires_at}`, with a sliding TTL and an `asyncio.Lock`.
- A server restart clears all sessions, by design.
- Cookie: `vietrp_session`, `HttpOnly`, `SameSite=Strict`, `Secure` = `cookie_secure`, `Path=/`, `Max-Age` = TTL.

**Client IP + rate limit:**
- Use `CF-Connecting-IP` only when the socket peer is in `trusted_proxy_hosts`; otherwise use the peer address.
- Sliding window per IP for unlock/create, from config.
- When limited: 429 `rate_limited` with a `Retry-After` header.

**API contract** (WP-F builds against this exactly):

| Method + path | Request | Success | Errors |
|---|---|---|---|
| `POST /api/vault/unlock` | `{passphrase: string}` | 200 `{exists: true, vault: VaultOut}` + cookie; or 200 `{exists: false}` (no cookie) | 429 `rate_limited`, 422 `validation_error` |
| `POST /api/vault/create` | `{passphrase: string, display_name: string (1–40)}` | 201 `{vault: VaultOut}` + cookie | 409 `vault_exists`, 422 `passphrase_weak`, 429 `rate_limited` |
| `POST /api/vault/lock` | — | 204, session removed, cookie cleared | — |
| `GET /api/vault/me` | — | 200 `{vault: VaultOut}` | 401 `vault_locked` |
| `PATCH /api/vault/me` | `{display_name}` | 200 `{vault: VaultOut}` | 401, 422 |
| `GET /api/secrets` | — | 200 `{secrets: SecretOut[]}`, one entry per allowed name | 401 |
| `PUT /api/secrets/{name}` | `{value: string (non-empty, trimmed)}` | 200 `{secret: SecretOut}` | 400 `secret_name_invalid`, 401, 422 |
| `DELETE /api/secrets/{name}` | — | 204 | 400, 401 |

- `VaultOut = {id: uuid, display_name: string, created_at: datetime}`
- `SecretOut = {name: string, is_set: bool, hint: string | null, updated_at: datetime | null}`. **The value is never returned.**
- `unlock` and `create` both update `last_seen_at`. Unlock with a wrong passphrase is simply `exists: false`; there is no separate "wrong password" state, by design.

**Internal API for other services:** `async def get_secret(session: VaultSession, name: str) -> str | None` in `vault_service`. The LLM layer receives keys as parameters and never calls this itself.

**Tests:**
- lookup determinism, and that different peppers give different lookups;
- KEK/DEK wrap/unwrap; wrong KEK fails;
- strength rule;
- session TTL and expiry;
- client IP trust rules;
- rate limiter;
- API flow against an in-memory fake repository (unlock unknown → create → me → set secret → list shows hint, not value → lock → me 401);
- assert no response body or log record ever contains the secret value;
- the same flow against real Postgres when `VIETRP_TEST_DATABASE_URL` is set.

---

## WP-E · LLM layer (backend-builder) — wave 2

**Owns:** `app/llm/**`, `app/repositories/usage_repo.py`, `tests/llm/**`, `tests/fixtures/llm/**`.

Reference: `vietrp-agent/backend/vietrp/llm.py` (streaming), `engine/group.py::_post` and `judge.py` (Decisions request/response shape), `turn.py` (usage aggregation).

**Build:**
1. `defaults.py`: `DEFAULT_MODELS: dict[AgentId, str]` exactly as AGENTS.md §4.4 lists them; `extractions` defaults to the decision model. `AgentId` is a `Literal` of the 9 agent ids.
2. `client.py`: one shared `httpx.AsyncClient` factory with config timeouts.
   - Headers: `Authorization: Bearer <api_key>`, `X-Title: VietRP Studio`, `HTTP-Referer` from config if set.
   - Retries on 429/500/502/503/529 with exponential backoff (`llm_max_retries`, `llm_backoff_base_seconds`), honoring `Retry-After`.
   - Raises `LLMError(code, status, message)`. The message must never include the API key or request headers.
3. `chat.py`: `stream_chat(api_key, model, messages, params) -> AsyncIterator[ChatEvent]`.
   - Sends `stream: true` and `usage: {include: true}` to `POST /api/v1/chat/completions`.
   - Parses SSE `data:` lines and ignores `: OPENROUTER PROCESSING` comments.
   - `ChatEvent` is a union of `ContentDelta(text)`, `ReasoningDelta(text)`, `Usage(prompt_tokens, completion_tokens, reasoning_tokens, cost)` and `Finish(reason)`.
   - `finish_reason == "length"` yields `Finish("length")`.
   - Params: `temperature`, `top_p`, `max_tokens`, `reasoning: {effort} | off`, `provider` routing passthrough.
   - Also `complete_chat(...)` (non-stream), returning `(text, Usage)`.
4. `decisions.py`:
   - `Question` models: `Choice(criteria: dict[str, str], instructions)`, `Noul(instructions)`, `Score(criteria: list[str], instructions)`.
   - `DecisionClient` protocol: `async decide(api_key, model, state: dict[str, str], questions: dict[str, Question]) -> DecisionResult`.
   - `DecisionResult` holds normalized answers: choice → `{choice, confidence, probabilities}`; noul → `{p}`; score → `{score}`. It also has `usage` and `model`.
   - Enforce `decisions_max_questions`: raise `QuestionBudgetExceeded` before any network call.
   - `OpenRouterDecisionClient` posts to `/api/alpha/decisions`.
   - `ChatFallbackDecisionClient` asks a chat model for strict JSON (`response_format` json_schema) with the same normalized output.
   - `ResilientDecisionClient(primary, fallback)` uses the fallback when the primary returns 404/410/5xx after retries or an unparseable body, and flags `used_fallback=True`.
5. `extractions.py`: the same pattern for `/api/alpha/extractions`: fields `{name: {type: "text", instructions}}` → `{value, confidence}`, with a chat fallback.
6. `tokenizer.py`:
   - `count_text`, `count_messages` (tiktoken `o200k_base`, +4 tokens per message).
   - `CorrectionTable`: per-model EMA factor of `real_prompt_tokens / estimated`, clamped to [0.8, 2.0], default 1.0; `estimate(model, messages)` applies it.
   - Load the encoding lazily and cache it.
7. `pricing.py`: fetch `GET /api/v1/models` once, cache it with a TTL from config (add an `LLMConfig` dataclass inside `app/llm/` for anything not already in core config, and do not edit `core/config.py`). Expose `price(model) -> {prompt, completion} | None` and `estimate_cost(model, usage)`. Prefer `usage.cost` from the provider when present.
8. `usage.py` + `repositories/usage_repo.py`:
   - `UsageRecorder` protocol `record(vault_id, chat_id, agent, model, usage)`.
   - `SqlUsageRecorder` inserts into `usage_log`; `NullUsageRecorder` for tests.
   - `stream_chat`, `complete_chat` and `decide` accept an optional `recorder` + context `(vault_id, chat_id, agent)` and record exactly once per call, including on the fallback path.
9. Tests use `httpx.MockTransport` and JSON/SSE fixtures written by hand to match the reference shapes. No network.
   - Stream parsing, including a chunk split mid-line, a reasoning delta, a usage chunk and a length finish.
   - Retry on 429 with `Retry-After`; no retry on 400.
   - Decisions normalization for choice/noul/score.
   - The budget is enforced without a network call.
   - Fallback triggers on 404; usage is recorded exactly once.
   - The API key never appears in an `LLMError` message.
   - Token counting sanity, and the EMA factor clamp.
   - The tiktoken encoding may need a one-time download. If the sandbox blocks it, mark those tests to skip with a clear reason; do not fake the counts.

---

## WP-F · Frontend vault + API key UI (frontend-builder) — wave 2

**Owns:** `frontend/src/features/vault/**`, `frontend/src/features/settings/**`, the added keys in `src/i18n/vi.ts` (append-only, under `vault.*` and `settings.*`), and replacing the `/settings` placeholder route element. The router edit is limited to that one line.

**Build** against the WP-D contract:
1. `VaultGate`: wraps the app. It calls `GET /api/vault/me` through TanStack Query (`["vault","me"]`). On 401 `vault_locked` it renders `UnlockScreen` full-screen; otherwise it renders children.
2. `UnlockScreen`:
   - centered card with the app name and a one-line explanation (no accounts; passphrase = your vault; losing it means losing data, said plainly);
   - passphrase field with show/hide, and a live strength hint mirroring the server rule (≥16 chars, or ≥4 words and ≥12 chars);
   - submit → `POST /api/vault/unlock`; `exists: false` opens a confirm dialog "Chưa có vault cho passphrase này. Tạo vault mới?" with a `display_name` field → `POST /api/vault/create`;
   - map errors with `errorMessage(code)`; show `Retry-After` on 429;
   - submit on Enter, focus management, no autofill of the passphrase into the URL, `autocomplete="current-password"`;
   - works in both themes and at 375px.
3. Lock button in the IconRail footer slot (and in the mobile settings page) → `POST /api/vault/lock` → clear the query cache → UnlockScreen.
4. Settings page (`/settings`) with three sections:
   - **Vault**: edit display name;
   - **API key**: list from `GET /api/secrets`, showing `is_set` and `••••<hint>`, a set/replace dialog (`PUT`), delete with confirm (`DELETE`). The key value is never shown back, and the input clears after save;
   - **Giao diện**: theme switch.
5. Tests with a mocked `fetch`:
   - unlock existing;
   - unlock unknown → confirm → create;
   - weak passphrase error mapping;
   - the secrets list renders the hint and never the value;
   - lock returns to the UnlockScreen.

---

## Lead checklist per WP (review)

- [ ] AGENTS.md §2 non-negotiables hold.
- [ ] Files stay within ownership; reference folders are untouched.
- [ ] The contract matches exactly: paths, status codes, error codes, field names.
- [ ] Gates were re-run by qa-runner, not only self-reported.
- [ ] No magic numbers; English identifiers; Vietnamese only in `vi.ts`, prompts and docs.
- [ ] Tests cover behavior and error paths, not just the happy path.
