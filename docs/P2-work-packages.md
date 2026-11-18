# P2 — Single chat: work packages

Phase goal (KIEN-TRUC-VIETRP.md §13, P2): single chat (`mode = "single"`) end to end. Orchestrator → Writer → Director over SSE, Bond Drafter/Selector after the user's first message, the minor-safety module, lorebook selection, prompt assembly with presets, the token bar and the Prompt Inspector. **Out of scope:** world chat, State Keeper and `<scene>` (P3); Archivist (P4, but the trigger hook point exists); swipe UI, fork, undo, `/time` `/move` `/addnpc`, continue (P5); Creator and Card Judge (P6).

Same team, rules and file-ownership discipline as P0/P1 (`docs/P0-work-packages.md`, AGENTS.md §8–9). Backend port 7880; frontend 5173. Drafted by the lead at the end of P1 (2026-11-18) from KIEN-TRUC §3, §3.0, §3.1, §4.4, §4.5, §5.1, §7, §8, §9.3. Read the P1 review hand-off notes in `PROGRESS.md` (lorebook visibility must be re-checked at prompt time).

## Waves

| Wave | WPs (parallel) | Depends on |
|---|---|---|
| 1 | **L** LLM wiring + agent framework · **M** pipeline core (safety, lorebook, assembler, commands) · **C2** contracts (chat schemas + SSE events + generated TS) | P1 |
| 2 | **N** agents (orchestrator, writer, director, bond_drafter, bond_selector) · **O** chats API + single-turn pipeline + SSE · **Q0** FE chat API client + `useTurnStream` | L, M, C2 |
| 3 | **R** chat page UI (bubbles, input, token bar, Prompt Inspector) · **S** new-chat flow + presets UI + chat settings | O, Q0 |
| 4 | qa-runner → lead review → fixes; one opt-in live smoke test (`pytest -m live`) only if the owner has saved an OpenRouter key | all |

---

## WP-C2 · Contracts (backend-builder; land first in wave 1)

**Owns:** `backend/app/schemas/chat.py`, `backend/app/schemas/events.py`, `backend/app/schemas/presets.py`, `backend/tests/schemas/**`, the export step that writes `frontend/src/types/generated/schemas/{chat,events,presets}*.json` (extend `app/formats/export_schema.py` only by adding entries to its registry).

**Build:**
1. `events.py`: one Pydantic model per SSE event, with a `type` literal and a discriminated union `TurnEvent`. Names are fixed (AGENTS §4.5): `plan`, `speaker_start`, `draft`, `director`, `content`, `reset_content`, `rejudge`, `scene`, `speaker_end`, `state`, `archivist`, `bonds`, `notice`, `usage`, `ping`, `done`, `error`. P2 emits all of them except `scene`, `state` and `archivist`, which are defined now and used in P3/P4.
   - `plan {turn_type, speakers: [{id, kind: "character"|"narrator", sentences}], lore_ids[], card_fields[]}`
   - `speaker_start {message_id, speaker, seq}`; `draft {delta}`; `content {delta}`; `reset_content {message_id}`
   - `director {passed, score, criteria: [{id, probability, passed, hint_vi}], attempt}`; `rejudge {attempt}`
   - `speaker_end {message_id, variant_idx, stopped}`; `bonds {bonds}`; `notice {code, agent?, detail?}`
   - `usage {agent, model, prompt_tokens, completion_tokens, reasoning_tokens, cost}`; `ping {}`; `done {message_ids[]}`; `error {code}`
   - No secrets or raw provider errors in any event (AGENTS §2.2). `notice.detail` is English, for logs.
2. `chat.py`:
   - `ChatCreate {mode: "single", character_id, persona_id?, greeting_index, title?, settings?}`
   - `ChatSummary`, `ChatOut {…, state, settings, messages_count}`
   - `MessageOut {id, seq, speaker, active_variant, variants: [{idx, content, stopped, director?, created_at}], meta, created_at}` (no `draft` text unless `?include=drafts`)
   - `TurnRequest {text, prefill?}`; `ChatSettings`, the per-chat overrides of KIEN-TRUC §3.1 (`director.enabled`, `director.stream_mode`, `lorebook.mode`, `memory.context_length`, `memory.summarize_at`, `nsfw`, per-agent `model`).
   - `PromptPreview {layers: [{name, tokens, text}], total_tokens, budget}` for the Prompt Inspector.
3. `presets.py`: `PresetIn/PresetOut {agent, name, layers: dict[str, str]}`.
4. Export JSON Schema, run `npm run gen:types` in the frontend, commit nothing.

---

## WP-L · LLM wiring + agent framework (backend-builder)

**Owns:** `backend/app/agents/base.py`, `backend/app/agents/__init__.py`, `backend/app/llm/{deps,fake}.py` (new), `backend/app/repositories/usage_repo.py`, `backend/app/main.py` lifespan block only, `backend/app/core/deps.py` (adding LLM deps only), `backend/app/services/vault_service.py` (only the `get_secret` dedupe from the P0 open items), `backend/tests/agents/test_base.py`, `backend/tests/llm/test_wiring.py`, `backend/tests/fixtures/llm/**` (the loader and format; agent-specific fixtures belong to WP-N).

**Build:**
1. Lifespan: one shared `OpenRouterClient`, `PricingCache`, `CorrectionTable`, and the `Resilient{Decision,Extraction}Client`s (P0 open item). Depend on them through `core/deps.py`. The OpenRouter key is read per call from the vault (`get_secret("openrouter_api_key")`) and is never stored on a shared object.
2. `agents/base.py`:
   - `AgentContext {vault_id, chat_id, llm: LLMGateway, settings, clock}`
   - `AgentResult[T] {value: T, usage: list[Usage], notices: list[Notice]}`
   - `LLMGateway`: a facade over chat/stream/decisions/extractions that records a `usage_log` row for every call (vault, chat, agent, model, tokens, cost) and yields `usage` events. Retry 429/5xx with backoff (max 3) and explicit timeouts (reuse the P0 client).
   - Helper `run_non_critical(agent_id, coro)`: on failure returns a `notice` and lets the turn continue (AGENTS §4.4).
3. `llm/fake.py`: `RecordedLLM`, which replays `tests/fixtures/llm/*.json` (request matcher → response or stream chunks), so no test touches the network. A `pytest -m live` marker is registered in `pyproject.toml`; live tests are skipped unless `VIETRP_LIVE=1`.
4. Tests: usage rows are written per call with cost from the pricing cache; secrets never appear in `usage_log`, events or exceptions; the fake replays both streaming and decisions.

---

## WP-M · Pipeline core (backend-builder)

**Owns:** `backend/app/pipeline/{safety,lorebook,prompt_assembler,commands,context_budget}.py`, `backend/app/prompts/_shared/*.j2`, `backend/app/prompts/presets.py` (default preset loading + layer override), `backend/tests/pipeline/**`.

**Build:**
1. `safety.py` (AGENTS §2.1, the only home of these rules):
   - `minor_rule(cast) -> str | None`: the Vietnamese hard rule, injected when any present character has `age < 18`.
   - `assert_cast_usable(cast)`: `age is None` → `AppError("age_required")`, so a chat cannot start or continue with a card that has no age.
   - Move `card_has_minor`, `is_nsfw_tagged` and the public NSFW guard here, and re-export them from `formats/validate.py` for compatibility.
   - The assembler calls `apply(prompt_layers, cast, settings)`. It appends the rule as the **last system layer**, after presets, `/cmd` instructions and NSFW text, and nothing can override or remove it.
2. `lorebook.py`, after `viet-rp-glow/src/utils/promptBuilder.ts`:
   - keyword scan over the last `scan_depth` messages, with `selective` + `secondary_keys`, `constant`, `priority`, `position` and `enabled`;
   - token `budget` per book;
   - `mode`: `keyword` | `ai` | `hybrid`. Hybrid returns keyword/constant hits plus top-N remaining candidates (config `LORE_AI_CANDIDATES`) for the Orchestrator to judge; it never sends the whole book.
   - Only books visible to the chat's vault are loaded: own, or public right now. Re-check visibility here and never trust `lorebook_links` alone (P1 review m7).
3. `commands.py`: parse `/cmd [instruction] [message]` and `/force @name`. Other commands (`/time`, `/move`, `/addnpc`…) are parsed into `UnsupportedCommand` until P5, so the UI can say "chưa hỗ trợ".
4. `prompt_assembler.py`:
   - layered prompt: preset system → card (selected fields only) → persona → bonds → lore (by position) → summary/events (empty until P4) → recent window that fits the budget → `/cmd` instruction → prefill;
   - returns `AssembledPrompt {messages, layers: [{name, tokens, text}], total_tokens}`, which also feeds the Prompt Inspector;
   - templates in `app/prompts/_shared/*.j2`, no prose in Python.
5. `context_budget.py`: tiktoken count × per-model `CorrectionTable` factor; `needs_summary(total, settings)` at `memory.summarize_at` (hook only; P4 runs the Archivist).
6. Tests (mandatory, AGENTS §6):
   - The safety rule is present in every assembly path: plain, `/cmd`, prefill, NSFW on, and a preset that tries to say the opposite. It is always the last system layer.
   - `age None` blocks.
   - Lorebook: keyword/selective/constant/budget/priority, hybrid candidates capped, private foreign books excluded.
   - Commands parser.
   - Assembler budget trimming keeps the newest messages.

---

## WP-N · Agents (backend-builder)

**Owns:** `backend/app/agents/{orchestrator,writer,director,bond_drafter,bond_selector}.py`, `backend/app/prompts/{orchestrator,writer,director,bond_drafter,bond_selector}/*.j2`, `backend/tests/agents/test_{orchestrator,writer,director,bonds}.py`, `backend/tests/fixtures/llm/{orchestrator,writer,director,bond_*}*.json`.

References (read-only): `vietrp-agent/backend/vietrp/engine/group.py` (its "director" = our **Orchestrator**), `judge.py` (= our **Director**), `turn.py`. Mind the role-name trap (AGENTS §1).

**Build** (each module exposes `AgentConfig` + `async def run(ctx, cfg, …)`, AGENTS §4.4; models come from `llm/defaults.py`):
1. `orchestrator`, Decisions with atomic positive questions within the question budget:
   - turn type;
   - which lore candidates apply (only the pre-filtered top-N from WP-M);
   - which card fields to load;
   - who the user is addressing.

   Single chat has one speaker, the character or the narrator. On failure, fall back to narrator + core fields and emit a `notice`.
2. `writer`: streams from the `AssembledPrompt`; accepts a `fix_hints` list on retry.
3. `director`:
   - criteria from KIEN-TRUC §3: answers the last message; doesn't open new events on its own; doesn't write for the player; no assistant voice;
   - returns per-criterion probability, pass/fail and short Vietnamese hints, never a single number;
   - threshold in config;
   - sets `meta.priority` for P4;
   - the retry loop lives in WP-O, not here.
4. `bond_drafter` (chat JSON) → `bond_selector` (Decisions `choice`):
   - per pair (character ↔ persona): addressing, nickname, relationship, `stance`, `closeness` 0–4, an optional shared-history hook;
   - **never overwrite fields the card pins** (`addressing`, `relationships`), only fill gaps;
   - record history with the triggering `seq` (KIEN-TRUC §3.0).
5. Tests with recorded fixtures only: happy path, malformed model output → fallback, the orchestrator fallback, pinned bond fields untouched, and director hints present on fail.

---

## WP-O · Chats API + single-turn pipeline (backend-builder)

**Owns:** `backend/app/api/{chats,turns,presets,utility}.py` + registration lines, `backend/app/services/{chat_service,turn_service,preset_service}.py`, `backend/app/repositories/{chats_repo,messages_repo,presets_repo}.py`, `backend/app/pipeline/single_turn.py`, `backend/tests/chat/**`.

**API** (KIEN-TRUC §8, P2 subset):

| Method + path | Notes |
|---|---|
| `GET/POST /api/chats`, `GET/PATCH/DELETE /api/chats/{id}` | `mode = "single"` only (422 `mode_unsupported` otherwise). Create checks `assert_cast_usable`, snapshots the card into `chat.pack`, and writes the chosen greeting as message seq 0 |
| `GET /api/chats/{id}/messages?before=&limit=` | Paginated `MessageOut[]` |
| `POST /api/chats/{id}/turn` | SSE `TurnEvent`s, `ping` every 15 s. One running turn per chat (409 `turn_running`) |
| `POST /api/chats/{id}/stop` | Cooperative cancel. Partial text is saved as a variant with `stopped: true` |
| `GET /api/chats/{id}/prompt-preview?text=` | `PromptPreview` for the Prompt Inspector (no LLM call) |
| `PATCH /api/chats/{id}/state` | Edit `state.bonds` by hand (the only state in single chat) |
| CRUD `/api/presets` | Per-agent layers that override the default templates |
| `GET /api/models`, `POST /api/tokens/count`, `GET /api/usage?chat_id=` | Utility |

**`single_turn.py`** (KIEN-TRUC §5.1), an async generator of `TurnEvent`:
1. parse commands;
2. first user message only: Bond Drafter → Selector (non-critical) → `bonds`;
3. Orchestrator → `plan`;
4. assemble (WP-M), with the safety rule always applied;
5. Writer streams;
6. Director, following `director.stream_mode`:
   - `draft_then_replace`: forward the draft as `draft`/`content`, then `reset_content` + final text if rejected;
   - `hold_until_approved`: only progress events until approval;
   - on fail, retry with hints up to `DIRECTOR_MAX_RETRIES` (config), keep the higher-scoring variant, emit `rejudge`;
7. persist the message, variant (with `draft` and `director` JSON), meta and `state_before` in **one transaction** at `speaker_end`;
8. `usage`, `done`.

No `state_keeper` call (AGENTS §4.5). Use a heartbeat task for `ping`. A client disconnect cancels like `stop`.

**Tests:**
- full turn with `RecordedLLM`: events in order, persistence, `state_before` exact;
- both stream modes, including a rejection path;
- stop mid-stream → `stopped` variant;
- 409 on a concurrent turn;
- vault isolation on every route (another vault's chat → 404);
- a chat with an under-18 character carries the safety layer (inspect via prompt-preview);
- a card with `age: null` cannot start a chat;
- Postgres variants when `VIETRP_TEST_DATABASE_URL` is set.

---

## WP-Q0 · FE chat client (frontend-builder)

**Owns:** `frontend/src/features/chat/{api,hooks,store}.ts`, `frontend/src/features/chat/useTurnStream.ts`, `frontend/src/types/chat.ts` (hand-written API shapes not covered by generated types), and their tests. It may extend `frontend/src/lib/sse.ts` for POST-body SSE, plus its tests.

**Build:**
- typed fetchers + TanStack Query hooks for every WP-O route;
- `useTurnStream(chatId)`:
  - consumes typed events through `lib/sse.ts`;
  - keeps the active turn, the draft buffer and director status in a Zustand store (UI/stream state only, AGENTS §5.3);
  - handles `reset_content` by replacing the buffer;
  - on `done`, invalidates the messages query;
- `stop()` calls the stop route and aborts the stream.

Tests: event sequences for both stream modes, `reset_content`, `error`, `notice`, and abort.

---

## WP-R · Chat page UI (frontend-builder)

**Owns:** `frontend/src/features/chat/components/**`, `frontend/src/pages/ChatPage.tsx`, appended `chat.*` keys in `vi.ts`.

**Build** (KIEN-TRUC §9.3, AGENTS §5.3):
1. Messages:
   - Telegram-style bubbles, grouped consecutive messages, avatars, a distinct narrator style;
   - meta popover: Director criteria + hints, draft, usage/cost;
   - swipe `< i/n >` renders existing variants read-only (regenerate is P5);
   - delete/edit/fork buttons are visible but disabled with a "P5" tooltip, or hidden. Choose one and report it.
2. Input:
   - textarea with send, stop and prefill;
   - `/` popup listing `/cmd` and `/force`, with the other commands shown as "chưa hỗ trợ".
   - **The token bar is the textarea's top border**: prompt tokens / budget, color steps at 60/80/100%, and a click opens the Prompt Inspector. The budget math lives in a tested pure function.
3. Prompt Inspector: a sheet/dialog listing layers with token counts and text, the safety layer visibly marked.
4. Streaming:
   - draft text shows in a muted style while `director` is pending;
   - `hold_until_approved` shows a progress indicator;
   - notices appear as small inline toasts.
5. `100dvh`, works with the virtual keyboard, mobile-first at 375px; both themes; E-ink serif, no motion.

Tests: the token bar math + color steps, the command popup, the bubble grouping, and the streaming render from a mocked `useTurnStream`.

---

## WP-S · New chat flow + presets + chat settings (frontend-builder)

**Owns:** `frontend/src/features/chat/newChat/**`, `frontend/src/features/settings/presets/**` (new files; one `<PresetsSection />` line added in `SettingsPage.tsx`), `frontend/src/features/chat/settings/**`, appended `newChat.*`, `presets.*` and `chatSettings.*` keys in `vi.ts`, plus a "Chat" button on the character detail page through one prop/slot agreed with the lead. Do not edit WP-J's editor internals beyond that line.

**Build:**
- New chat: pick a persona → pick a card (from the library or a gallery duplicate) → swipe the greeting (`< 1/n >`) → create → navigate to `/chat/:id`. Cards with `needs_age` are blocked with a link to the editor.
- Chat list in the left sidebar (recent chats).
- Presets editor per agent (layers as textareas, reset to default).
- Per-chat settings sheet: director on/off + stream mode, lorebook mode, NSFW (with a note that the under-18 rule always applies), per-agent model.

---

## Lead notes

- C2 lands first. N and O build against `schemas/events.py` and WP-M's `AssembledPrompt`. If WP-O needs a column (e.g. a chat `updated_at` index), the lead adds migration `0002`.
- The safety tests in WP-M are a merge blocker (AGENTS §2.1). The lead re-verifies them personally in wave 4.
- No test may hit the network. The live smoke test is opt-in (`pytest -m live`, `VIETRP_LIVE=1`) and runs only if the owner has saved a key. Never enter or ask for the owner's real key.
