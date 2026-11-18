# P6 — Creator & Card Judge: work packages

Phase goal (`KIEN-TRUC-VIETRP.md` §3, §5.4, §7, §8, §9.2):
- Add dummy Vietnamese creator pools (`backend/app/creator/pools/{character,world}_pools.json`) editable outside code.
- Add **Card Judge** (`backend/app/agents/card_judge.py` + `app/prompts/card_judge/*.j2`) using Decisions API to return per-criterion probability, pass/fail, score, and short Vietnamese fix hints (`hint_vi`) — never just a single number.
- Add **Creator** (`backend/app/agents/creator.py` + `app/prompts/creator/*.j2`) supporting conversational interview mode (`POST /api/creator/sessions/{id}/message`) and 2-step generation (`draft_raw` -> `format_json` + validation + `card_judge` via SSE `raw` -> `formatted` -> `validated` -> `judged` -> `done`).
- Persist creator sessions in `creator_sessions` (`creator_repo.py`), wire `GET /api/creator/pools`, session CRUD, `/save` to library, and `POST /api/characters/{id}/judge` + `POST /api/worlds/{id}/judge` storing `judge_score` on characters/worlds.
- Build `/create` UI (`features/create/**`) with Carousel + Slot Machine (random unlocked reels + lock toggles) and Chat Interview mode, plus 2-step raw draft editor, formatted result preview, Card Judge score panel (`CardJudgePanel.tsx`), and Card Judge integration inside `CharacterEditor` & `WorldEditor`.

## Waves

| Wave | WPs | Depends on |
|---|---|---|
| 1 | **B6** backend Creator, Card Judge, pools, repo, API & schemas + FE gen:types | P5 |
| 2 | **F6** frontend Creator UI (`/create`) + CardJudgePanel in editors | B6 |

---

## WP-B6 · Backend Creator & Card Judge (`backend-builder`)

**Owns:**
- `backend/app/creator/pools/character_pools.json`, `backend/app/creator/pools/world_pools.json`
- `backend/app/prompts/card_judge/*.j2`, `backend/app/prompts/creator/*.j2`
- `backend/app/agents/card_judge.py`, `backend/app/agents/creator.py`
- `backend/app/repositories/creator_repo.py`, `backend/app/repositories/characters_repo.py`
- `backend/app/schemas/creator.py`, `backend/app/schemas/library.py` (`judge_score: dict[str, Any] | None = None` on `CharacterOut` / `WorldOut`), `backend/app/formats/export_schema.py`
- `backend/app/services/creator_service.py`, `backend/app/services/library_service.py`
- `backend/app/api/creator.py`, `backend/app/api/library.py`, `backend/app/api/__init__.py`
- `backend/tests/library/fakes.py` (`judge_score` support on `FakeContentRepository`)
- `backend/tests/agents/test_card_judge.py`, `backend/tests/agents/test_creator.py`, `backend/tests/creator/test_creator_api.py`

## WP-F6 · Frontend Creator & Card Judge UI (`frontend-builder`)

**Owns:**
- `frontend/src/types/library.ts` (re-export `judge_score` if needed)
- `frontend/src/features/create/**`
- `frontend/src/pages/CreatePage.tsx`
- `frontend/src/features/library/character/CharacterEditor.tsx`, `frontend/src/features/library/world/WorldEditor.tsx`, `frontend/src/features/library/api.ts`, `frontend/src/features/library/hooks.ts`
- `frontend/src/i18n/vi.ts`
- `frontend/src/features/create/create.test.tsx`, `frontend/src/features/library/characterEditor.test.tsx`
