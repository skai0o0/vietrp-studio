# P5 — Chat Experience (Commands, NPC, Anti-Repeat, Continue, Swipe, Edit, Delete, Undo, Fork): work packages

Phase goal (`KIEN-TRUC-VIETRP.md` §5.1, §5.2, §7, §8, §9.3):
- Enable `/time`, `/move`, `/addnpc`, `/removenpc`, `/listnpc`, `/clearnpc` commands (alongside `/cmd` and `/force`).
- Add anti-repeat check (`difflib.SequenceMatcher > 0.6` -> `writer_repeated` notice + 1 rewrite) in `single_turn` and `world_turn`.
- Add Continue turn (`POST /api/chats/{id}/continue`), Regenerate + Swipe (`POST /api/messages/{id}/regenerate`, `PUT /api/messages/{id}/active-variant` + `/api/chats/{chat_id}/messages/...` aliases), Edit (`PATCH`), Delete (`DELETE`), Undo (`POST /api/chats/{id}/undo`), and Fork (`POST /api/chats/{id}/fork`, including `parent_chat_id` & `forked_at_seq` tree metadata and snapshot copying).
- Wire all actions in Frontend (`MessageBubble`, `ChatInput`, `CommandPopup`, `RecentChats` fork tree + search + grouping, `vi.ts`).

## Waves

| Wave | WPs | Depends on |
|---|---|---|
| 1 | **C5** contracts + schema export + FE gen:types | P4 |
| 2 | **B5** commands, anti-repeat, continue, regenerate/swipe, edit/delete/undo, fork | C5 |
| 3 | **F5** FE controls, swipe/regen/edit/delete/fork, continue/undo, sidebar fork tree + search/group | C5, B5 |

---

## WP-C5 · Contracts & Schema Export (`backend-builder`)

**Owns:**
- `backend/app/schemas/chat.py` (add `parent_chat_id: str | None = None`, `forked_at_seq: int | None = None` to `ChatSummary`, plus `ContinueRequest`, `MessageUpdate`, `ActiveVariantRequest`, `RegenerateRequest`, `ForkRequest`, `UndoResult`)
- `backend/app/formats/export_schema.py` (add P5 request/response models as needed)
- `frontend/src/types/generated/**` & `frontend/src/types/chat.ts`

## WP-B5 · Backend Chat Actions & Commands (`backend-builder`)

**Owns:**
- `backend/app/core/config.py` (`ANTI_REPEAT_THRESHOLD = 0.6`)
- `backend/app/pipeline/commands.py` (structured parse for `/time`, `/move`, `/addnpc`, `/removenpc`, `/listnpc`, `/clearnpc`, pure state command execution helper)
- `backend/app/pipeline/state_commands.py` (executes pure state commands updating `chat.state` with `StateEvent` + `NoticeEvent`)
- `backend/app/pipeline/single_turn.py`, `backend/app/pipeline/world_turn.py` (anti-repeat, `is_continue` mode skipping `answers_last` & `no_new_events`, pure state command fast-path)
- `backend/app/repositories/chats_repo.py`, `backend/app/repositories/messages_repo.py` (`parent_chat_id`, `forked_at_seq`, `set_active_variant`, `update_variant_content`, `add_variant`, `delete_from_seq`, `get_by_id`, `clone_chat_for_fork`)
- `backend/app/services/chat_service.py`, `backend/app/services/turn_service.py` (`undo`, `fork`, `edit_message`, `delete_message`, `set_active_variant`, `start_continue`, `start_regenerate`)
- `backend/app/api/chats.py`, `backend/app/api/turns.py`, `backend/app/api/__init__.py` (chat & message routes)
- `backend/tests/chat/fakes.py`
- `backend/tests/pipeline/test_commands.py`, `backend/tests/chat/test_p5_actions.py`

## WP-F5 · Frontend Chat Experience (`frontend-builder`)

**Owns:**
- `frontend/src/features/chat/api.ts`, `frontend/src/features/chat/hooks.ts`, `frontend/src/features/chat/useTurnStream.ts`
- `frontend/src/features/chat/components/commands.ts`, `frontend/src/features/chat/components/ChatInput.tsx`, `frontend/src/features/chat/components/MessageBubble.tsx`, `frontend/src/features/chat/components/MessageList.tsx`, `frontend/src/features/chat/components/ChatView.tsx`
- `frontend/src/features/chat/newChat/RecentChats.tsx`
- `frontend/src/i18n/vi.ts`
- `frontend/src/features/chat/chat.test.tsx`, `frontend/src/features/chat/components/components.test.tsx`
