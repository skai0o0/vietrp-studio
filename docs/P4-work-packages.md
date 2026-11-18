# P4 — Memory / Archivist: work packages

Phase goal (`KIEN-TRUC-VIETRP.md` §5.3, §7, §8):
- Add the **Archivist** agent (`backend/app/agents/archivist.py` + `app/prompts/archivist/*.j2`) following `vietrp-agent/backend/vietrp/engine/group.py`.
- Track `CorrectionTable` feedback from actual `writer` `usage.prompt_tokens` into `tiktoken` estimates (`AGENTS.md` §4.5).
- Replace already-summarized messages (`seq < state.summary_upto`) in prompts with `state.summary` + `state.events` (`MAX_EVENTS = 24`), prioritizing higher `meta.priority` turns during compression and saving immutable `MemorySnapshot` rows for P5 undo/fork.
- Automatically trigger Archivist at `memory.summarize_at` (or when messages are dropped from the context window), emit `archivist` SSE events, and re-run Bond Drafter/Selector (`overwrite_unpinned=True`) if new events were added.
- Expose `POST /api/chats/{chat_id}/summarize` for manual compression and build the Frontend Memory & Memory-settings UI for both world and single chats.

## Waves

| Wave | WPs | Depends on |
|---|---|---|
| 1 | **M4** backend Archivist, snapshots, memory pipeline & `/summarize` | P3 |
| 2 | **FE4** frontend Archivist SSE sync, `MemorySection` & memory settings | M4 |

---

## WP-M4 · Backend Archivist & Memory Pipeline (`backend-builder`)

**Owns:**
- `backend/app/core/config.py`
- `backend/app/prompts/archivist/system.j2`, `backend/app/prompts/archivist/user.j2`
- `backend/app/agents/archivist.py`
- `backend/app/repositories/messages_repo.py`
- `backend/app/pipeline/memory.py`
- `backend/app/pipeline/single_turn.py`, `backend/app/pipeline/world_turn.py`
- `backend/app/services/turn_service.py`, `backend/app/services/chat_service.py`
- `backend/app/api/chats.py`
- `backend/tests/chat/fakes.py`
- `backend/tests/agents/test_archivist.py`, `backend/tests/chat/test_memory.py`

**Contracts:**
- `POST /api/chats/{chat_id}/summarize` -> returns `ChatOut` (updates `state.summary`, `state.summary_upto`, `state.events`, writes `memory_snapshots` row; raises `422` `nothing_to_summarize` if no unsummarized messages exist).
- SSE `ArchivistEvent(type="archivist", summary=str, events_added=int)` emitted after automatic turn compression.
- `chat.state` keys supported for both `single` and `world`: `summary: str`, `summary_upto: int` (exclusive `seq` bound: messages with `seq < summary_upto` are already summarized), `events: list[{id, title, content}]`.

---

## WP-FE4 · Frontend Memory UI & Settings (`frontend-builder`)

**Owns:**
- `frontend/src/features/chat/api.ts`, `frontend/src/features/chat/hooks.ts`
- `frontend/src/features/chat/store.ts`, `frontend/src/features/chat/useTurnStream.ts`
- `frontend/src/features/chat/state/MemorySection.tsx`, `frontend/src/features/chat/state/LiveStateEditor.tsx`
- `frontend/src/features/chat/settings/ChatSettingsPanel.tsx`
- `frontend/src/i18n/vi.ts`
- `frontend/src/features/chat/chat.test.tsx`, `frontend/src/features/chat/state/stateEditor.test.tsx`
