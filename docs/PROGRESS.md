# VietRP Studio: progress and handoff

> This is the single file a fresh lead session reads to continue the work. **Update it after every WP finishes** (status, report summary, open issues), before doing anything else.
> Last updated: 2026-11-19 ~01:14 (UTC+7). **P4 & P5 DONE.** P6 `WP-B6` DONE (`556` BE tests), `gen:types` synced, `WP-F6` running. Next: P7.

## How to resume (lead procedure)

> **Not a Claude session with subagents** (Antigravity, Codex, …)? Follow `docs/handoff/HANDOFF-NEXT-AGENT.md` instead: one agent, one WP at a time, gates after each, update this file. Steps 2–4 below describe the Claude multi-agent setup.
> The live smoke test for single chat is `scripts/dev/smoke_single_chat.py` (run it from `backend/` while the server runs on 7880).


1. Read `../../AGENTS.md`, `../../KIEN-TRUC-VIETRP.md`, this file, and the current phase's `docs/P<n>-work-packages.md`.
2. You are the **lead** (Opus): you assign, review and integrate. Builders are spawned with the Agent tool: `subagent_type: general-purpose`, a `model` override (sonnet for builders, haiku for ops/qa), `run_in_background: true`. The prompt tells them to read their role file in `../../.claude/agents/<role>.md` and their WP. Reuse the P0 prompts' structure: environment notes, the files that other parallel WPs own, "never kill processes you did not start", "do not commit".
3. For any WP marked **in progress** below: the builder may have died mid-work when the quota ran out. Check its owned files exist, run its gates, and either re-spawn it with "continue WP-X; files already present: …" or finish it yourself if it is small.
4. **Pace with quota:** call `mcp__ccd_session_mgmt__get_usage`. Above ~85% of the 5-hour window, don't start new builders. Update this file, then stop (or schedule a resume at `resetsAt` + 5 min with `mcp__scheduled-tasks__create_scheduled_task`, `fireAt`, carrying the same self-contained prompt).
5. Never commit to git unless the owner asks; `vietrp-studio` is not a git repo yet. Never kill processes you did not start (port 7870 is the owner's `vietrp-agent`).
6. Report to the owner in Vietnamese at the end of each phase.

## Environment facts

- Windows 11 dev box. Backend: `cd backend && uv run …` (Python 3.12 via uv). Frontend: `cd frontend && npm run …` (Node 24).
- Ports: backend **7880**, Vite 5173; the Vite proxy sends `/api` to 7880. **7870 belongs to another app; don't touch it.**
- PostgreSQL 17 is running locally. The lead has **no superuser password**.
  - `scripts/dev/create-dev-db.sql` creates role `vietrp_studio` + DBs `vietrp_studio`, `vietrp_studio_test`. The owner must run it once: `"C:/Program Files/PostgreSQL/17/bin/psql.exe" -h 127.0.0.1 -U postgres -v db_password=<password from backend/.env> -f scripts/dev/create-dev-db.sql` (the password is no longer in the repo).
  - Credentials (generated test values) are in `backend/.env` (gitignored).
  - To run DB tests: export `VIETRP_TEST_DATABASE_URL` from `backend/.env`, then `uv run pytest`. Also run `uv run alembic upgrade head` against `DATABASE_URL`.
- The browser pane may be hidden, which makes screenshots render black. Use DOM checks (`javascript_tool`) or ask the owner to show the pane.

## Status

> **Tóm tắt cho chủ dự án: P3 (Chat Thực tại) đã XONG, 2026-11-18.**
> - Đã hoàn thành chế độ Chat Thực tại nhiều nhân vật: Orchestrator chọn danh sách nhân vật trả lời + độ dài + trường card/bí mật được phép tiết lộ; hỗ trợ 2 chế độ viết (`Từng nhân vật` mặc định hoặc `Một lần gọi cho cả nhóm`), `/force @ten`, và `Người dẫn truyện`.
> - Khối `<scene>` được lọc khỏi stream chữ và Director; State Keeper cập nhật song song vị trí (hysteresis 0.5 / 0.2), thời gian, căng thẳng, nhân vật có mặt/chờ đáp và NPC phụ.
> - Bond Drafter/Selector tự điền xưng hô & quan hệ cho cả cặp nhân vật–người chơi và giữa các nhân vật (tôn trọng trường đã ghim trong card, lưu lịch sử thay đổi).
> - Giao diện mới (kèm 2 skill `ui-ux-pro-max` và `design-taste-frontend` cho `frontend-builder`): luồng tạo Chat Thực tại (Thực tại → Cảnh mở đầu → Cast có khoá card thiếu tuổi → Persona), Trình sửa trạng thái trực tiếp + Bond + Scene ở thanh bên phải, xem trước prompt theo từng speaker (`Nhóm`, `Người dẫn truyện`, từng nhân vật), bubble nhiều speaker.
> - Kiểm thử cuối pha (sau khi sửa toàn bộ 1 blocker + 3 major + 7 minor từ review độc lập): backend `508 passed` (Postgres thật), frontend `137 passed` (18 file test) + build sạch, `mypy --strict` 104 file, `ruff`, `eslint`, rule greps sạch, `vietrp-agent/` & `viet-rp-glow/` nguyên vẹn.
> - Smoke test live trên backend thật (`127.0.0.1:7880`): cả `smoke_single_chat.py` và `smoke_world_chat.py` đều PASS (`minor_rule` là lớp system cuối cùng, `PATCH /state` gắn cờ `manual`, thiếu key báo 400 `openrouter_key_missing`).
> - **Chưa chạy với LLM thật** (cần thêm OpenRouter key trong `/settings`). Tiếp theo: P4 (Ký ức / Archivist, hoàn thiện Settings UI).

> **Tóm tắt cho chủ dự án: P2 (Chat đơn) đã XONG, 2026-11-18.**
> - Đã có chat đơn đầy đủ luồng: Orchestrator → Writer → Director (stream qua SSE, có ping 15 giây). Hai chế độ hiển thị: hiện bản nháp rồi thay, hoặc giữ tới khi duyệt.
> - Bond Drafter/Selector tự đặt xưng hô và quan hệ sau tin đầu; không ghi đè những gì card đã ghim.
> - Lorebook lai: từ khoá trước, AI chọn top-N sau. Preset theo agent. Thanh token là viền trên ô nhập. Có Prompt Inspector, và layer an toàn được đánh dấu riêng.
> - Luồng tạo chat (persona → card → swipe lời mở đầu), danh sách chat gần đây, bảng cài đặt riêng cho từng chat.
> - Kiểm thử: backend 419 test (có DB thật), frontend 114 test, mypy strict, build sạch.
> - Lead đã smoke test trên backend thật: luật dưới 18 tuổi có mặt trong prompt; thiếu API key thì báo rõ; giao diện đạt ở 1440/375px và cả 2 theme.
> - **Chưa chạy với LLM thật**, vì vault chưa có OpenRouter key. Bạn thêm key trong Cài đặt rồi chat thử để kiểm tra chất lượng thật; đặc biệt Decisions API đang là alpha.
> - Tiếp theo: P3, Chat Thực tại (nhiều nhân vật, State Keeper, khối `<scene>`).

> **Tóm tắt cho chủ dự án: P1 (Thư viện) đã XONG, 2026-11-18.**
> - Đã có CRUD cho Nhân vật, Thực tại, Persona và Lorebook, cùng các trang danh sách và trình sửa (có cây địa điểm và danh sách Cảnh mở đầu).
> - Nhập/xuất SillyTavern CCv2/CCv3 (json/png) và World Info. VietRP → ST → VietRP không mất dữ liệu.
> - Gallery: thẻ công khai, yêu thích, "Thêm vào thư viện".
> - Kiểm thử: backend 264 test (có DB thật), frontend 84 test. Lint, mypy, typecheck và build đều sạch.
> - Review độc lập tìm ra 2 lỗi an toàn và đã sửa xong:
>   - đọc tuổi khi nhập card: nếu card ghi nhiều tuổi mâu thuẫn thì nay để trống và bắt bạn điền, không đoán nữa;
>   - tag "nsfw" viết lách (dấu cách, ký tự ẩn, chữ full-width, "18+") không còn vượt qua được luật chặn card dưới 18 tuổi công khai.
> - Chưa kiểm tra bằng mắt trên trình duyệt (2 theme, 375px/1440px). Bạn nên mở thử `npm run dev` khi rảnh.
> - Tiếp theo: P2 Chat đơn (kế hoạch ở `docs/P2-work-packages.md`).

### P0 · Foundation: DONE (2026-11-18)
All WPs (A–F) passed review. Gates: backend 79 passed / 3 skipped (DB), frontend 26 passed, lint/mypy/typecheck/build clean.

Open items carried forward:
- [x] DB ready (owner ran create-dev-db.sql). `alembic upgrade head` applied to `vietrp_studio`; the 3 Postgres tests pass on `vietrp_studio_test`. Optional: add `path_separator = os` to alembic.ini (deprecation warning).
- [ ] `npm audit --omit=dev`: 12 issues (react-router moderate, picomatch high via the build chain). Fix at the start of P1 wave 3 or in a hygiene WP.
- [ ] The main JS chunk is ~537 kB; split vendor chunks later.
- [ ] Wire a shared `OpenRouterClient`, `PricingCache`, `CorrectionTable` and the resilient Decision/Extraction clients into app lifespan/deps (P2).
- [ ] `app/llm/templates/*.j2` (fallback prompts) live outside `app/prompts/`; fine for now, revisit in P2.
- [ ] `services/library_service.py` is ~570 lines; split per content type in a hygiene pass.
- [ ] Size limits are now settings in `core/config.py`, but `checked_image` / `io_service` still check the module constants as a second gate, so raising a cap by env alone is refused. Pass settings through (hygiene).
- [ ] No optimistic locking on library edits (concurrent PUTs: last write wins).
- [ ] The `get_secret` decrypt logic is duplicated in `vault_service.py` (method + module function); dedupe in P2.

### P1 · Library: DONE (2026-11-18)
Plan: `docs/P1-work-packages.md`.

| WP | Owner role | Status | Notes |
|---|---|---|---|
| G formats | backend-builder (sonnet) | DONE (108 tests pass; models reject unknown keys; persona/lorebook carry format+spec_version; schemas in frontend/src/types/generated/schemas) | wave 1 |
| H ST import/export | backend-builder (sonnet) | DONE (160 pass / 3 skip; round-trip ccv2/ccv3 json+png lossless via `data.extensions.vietrp`; `FormatError` in `st_import.py`, lead set status 422 / 413 for `file_too_large`; PNG export needs a PNG avatar, else placeholder or `avatar_not_png`) | wave 2 |
| I library API | backend-builder (sonnet) | DONE (clean env 180 pass / 23 skip; with test DB 203 pass. Worlds always send `needs_age: false` and `tagline` = first line of `rules`. Import errors keep WP-H's granular codes (`format_unknown`, `invalid_json`, `png_invalid`, `png_crc_mismatch`, `png_no_card`, `png_card_invalid`, `card_invalid`, `world_invalid`, `lorebook_invalid`, `file_too_large`), not one `format_invalid`. `ImportResponse` omits absent keys. Embedded `character_book` becomes a linked private lorebook. Uploads are read via `request.form()`. The lead pinned `python-multipart==0.0.34` and made `test_migrations` reset the schema first, because fixtures' `create_all` left tables behind) | wave 2 |
| J0 FE types + API client | frontend-builder (sonnet) | DONE (37 FE tests; `npm run gen:types`; hooks in features/library + features/gallery). Follow-ups resolved: WP-I always sends `needs_age: false` for worlds; WP-K narrowed `ImportResult.kind` to `ImportKind` | wave 2 |
| J library pages/editors | frontend-builder (sonnet) | DONE (FE gates green: 82 tests, build OK. Added routes `/library/personas/:id`, `/library/lorebooks/:id`; `:id = new` creates. Native select/textarea styled with tokens. Not done: arrow-key tree navigation, unsaved-changes warning. Not visually verified) | wave 3 |
| K gallery + import/export UI | frontend-builder (sonnet) | DONE (50 FE tests incl. 14 new; `@/features/io` exports `ExportMenu {kind, id, formats?: ExportFormatId[]}` + `ImportButton {onImported?}`; optimistic favorites via `useOptimisticFavorite` (J0 `useToggleFavorite` now unused); tag chips = top-12 tags of loaded items (no tag endpoint); 14 import error codes in `errors.*`. Not visually verified; unused `pages.gallery.*` strings remain) | wave 3 |
| QA + review + DB tests | qa-runner (haiku) + lead | DONE (QA PASS: all gates green, rule greps clean, reference folders untouched since before P1. Review: 2 blockers (B1 `parse_age` picks the wrong of several ages; B2 `nsfw ` tag variants bypass the guard), 3 major (M1 duplicate lorebook link on re-import, M2 import not one transaction, M3 error codes vs contract → doc updated), minors m1–m7. P1-FIX-FE DONE (84 FE tests; shared `errors.*` gained not_found/nsfw_minor_public/invalid_cursor; lorebook Mở → detail; removed unused `pages.gallery.*` and `useToggleFavorite`). P1-FIX-BE DONE: all 10 findings fixed with tests; the lead re-verified B1/B2 by hand. Final gates: BE 264 pass with DB, FE 84 pass + build) | wave 4 |

### P2 handoff notes (from the P1 review)
- `lorebook_links` can outlive a lorebook's public status (vault B links A's public book, then A makes it private). P2 prompt assembly must re-check visibility (`get_visible`) and never trust links alone.
- A duplicate of another vault's public card keeps that vault's lorebook UUIDs in `data.lorebook_ids`; the links are filtered, but consider dropping invisible ids on duplicate.
- `world.py` cycle check is dead code (level ordering already prevents cycles); harmless.

### P2 · Single chat: DONE (2026-11-18)
Plan drafted by the lead: `docs/P2-work-packages.md` (waves: 1 = L + M + C2, 2 = N + O + Q0, 3 = R + S, 4 = QA/review).

| WP | Owner role | Status | Notes |
|---|---|---|---|
| C2 contracts | backend-builder (sonnet) | DONE (17 events, `TurnEvent` discriminated on `type`; `TurnEventEnvelope` RootModel for validation, exported schema root is `TurnEventDoc{event}` so the FE types events from the individual `*Event` interfaces; `ChatSettings` nested per §3.1 with typed `AgentModels`; `StateBondsPatch` for PATCH state; 25 tests) | wave 1 |
| L LLM wiring + agent framework | backend-builder (sonnet) | DONE (305 pass with DB. `agents/base.py`: `AgentContext`, `AgentResult[T]`, `Notice{code, agent, detail}`, `LLMGateway.{complete,stream,decide,extract,drain_usage}`, `run_non_critical`. `core/deps.py`: `GatewayFactoryDep`, `make_key_provider` (secret `OPENROUTER_API_KEY`, 400 `openrouter_key_missing`). `llm/fake.py` `RecordedLLM` is an httpx MockTransport; fixtures carry `"vietrp_fixture": 1`, `match`, `responses`. WP-O maps `Notice`→`notice` and `Usage`→`usage`, and must test stream cancellation) | wave 1 |
| M pipeline core (safety, lorebook, assembler) | backend-builder (sonnet) | DONE (58 pipeline tests; BE suite 363 pass with DB. `safety.apply` always appends `minor_rule` as the last system layer, `verify` re-checks it, and a missing template raises `SafetyConfigError`. Unknown-age NPCs count as minors; a non-NPC with `age None` raises `age_required`; **a persona with `age None` is allowed** (lead accepted; revisit if the owner wants persona age required). Layer order: system, nsfw, lore_before, card, lore_after, persona, bonds, memory, cmd_instruction, minor_rule. User text is never rendered as Jinja. Lead switched `library_service` to `safety.public_nsfw_blocked`, so the rule lives in one module. Hand-off to O/N in the WP-M report: build `AssemblyInput` from chat state, `load_books(repo, vault_id, ids)`, Orchestrator uses `LoreSelection.candidates` + `promote`) | wave 1 |
| N agents | backend-builder (sonnet) | DONE (380 BE tests with DB; 21 agent tests. Signatures and wiring duties for WP-O are in `docs/handoff/P2-N-agents.md`: filter secrets by `plan.secret_ids`, emit usage via `drain_usage`, wrap director/bonds in `run_non_critical`) | wave 2 |
| O chats API + single turn | backend-builder (sonnet) | DONE (418 BE tests with DB, 38 chat tests fake+PG. Turn runs as a task → queue → SSE, typed `ping`, `EventSourceResponse(ping=0)`. A missing key gives 400 `openrouter_key_missing` before anything is saved. The user msg is saved at turn start; AI msg+variant+meta+state_before in one tx. Secrets filtered by `plan.secret_ids`. Lists are bare arrays. All 4 FE assumptions honoured. **Follow-ups:** (1) `mode_unsupported` gives 422 `validation_error` because `ChatCreate.mode` is `Literal['single']`; (2) move `DIRECTOR_MAX_RETRIES` / `history_limit` / `recent_lines` from `TurnConfig` into `core/config.py`; (3) no preset selection per chat: the latest writer preset is applied, so add `settings.preset_id`?; (4) **narrator plans use the character prompt** (no narrator instruction layer), to fix in P3; (5) agent prompt overrides are not wired) | wave 2 |
| Q0 FE chat client | frontend-builder (sonnet) | DONE (93 FE tests. `features/chat/{api,hooks,store,useTurnStream}.ts`; pure `reduceTurn`; `sse.ts` now throws `ApiError` on non-2xx. **Assumptions WP-O must honour:** SSE `data` JSON carries `type`; `POST /stop` → `{stopped: bool}`; `GET /api/models` → `ModelInfo[] {id, name, context_length}`; `PATCH /state` body `{bonds}`; codes `turn_running`, `chat_not_found`, `character_needs_age`, `llm_failed`, `orchestrator_fallback`, `director_failed` in `vi.ts chat.errors/notices`; reconcile after O) | wave 2 |
| R chat page UI | frontend-builder (sonnet) | DONE (104 FE tests; components in `features/chat/components/`; edit/delete/fork shown disabled with a P5 tooltip; meta is a Dialog. Expects from O: speaker ids `user`/`narrator`/other = character; prompt-preview `{budget,total_tokens,layers}`; safety layer named `minor_rule`; `settings.director.stream_mode`. **Not visually verified.** Open: the E-ink token-bar colour steps are indistinguishable (a numeric count line was added); `h-full` inside `<main>` may need flex-col) | wave 3 |
| S new chat + presets + settings | frontend-builder (sonnet) | DONE (109 FE tests. Route `/create/chat?character=`; `ChatChrome` (in ChatPage) fills left = RecentChats and right = ChatSettingsPanel through `usePageChrome`; settings PATCH sends the full merged object; preset layers `system` (+ `nsfw` for writer) match `OVERRIDABLE_LAYERS`; a 'Chat' button was added in `CharacterEditor`. **Not visually verified.** Reconcile with O: `PresetOut{id,agent,name,layers}`, `ChatCreate.persona_id: null`) | wave 3 |
| QA + review | qa-runner (haiku) + lead | DONE (QA PASS: BE 418, FE 109, mypy --strict, greps clean, reference folders untouched. **Lead live smoke test OK** against the real backend + dev DB: vault/card/chat create, greeting at seq 0 with speaker = character id, prompt-preview carries `minor_rule` for an age-16 card, a turn without a key gives 400 `openrouter_key_missing`, a public minor+nsfw card gives 422, and the chat UI renders at 1440 and 375 in both themes. Found: many backend codes missing in vi.ts (generic error shown); typed text lost on a failed send; mobile placeholder clipped; E-ink token-bar steps invisible; `{{user}}` in the greeting preview. **P2-FIX-FE DONE** (all codes in vi.ts; typed text restored on a failed send; short mobile placeholder; E-ink token-bar steps via dash/thickness; `{{user}}` substituted in the preview). **P2-FIX-BE DONE** (`DIRECTOR_MAX_RETRIES`/`TURN_HISTORY_LIMIT`/`ORCHESTRATOR_RECENT_LINES` moved to core/config; `world` → 422 `mode_unsupported`; one canonical `age_required`; narrator layer `_shared/narrator.j2` before `minor_rule`; alembic `path_separator`). The lead re-verified all of it live in the browser. Final gates: BE 419, FE 114, build OK) | wave 4 |

### P3 carry-over (from P2)
- Prompt preview does not pass the narrator flag (it always shows the character prompt).
- `NoticeList` has no link support (`openrouter_key_missing` names /settings in text only).
- There is no per-chat preset selection; the latest writer preset in the vault is applied. Add `settings.preset_id`?
- Agent prompt overrides (presets for the orchestrator/director/bond agents) are not wired.
- The store has no handler for `scene`/`state`/`archivist` events yet (P3/P4).
- `npm audit`: ~22 issues (react-router moderate, picomatch via the build chain): hygiene WP.
- Dev DB holds test vaults named "Smoke"/"UI Smoke" from the lead's smoke tests; harmless.

### P3 · World chat: DONE (2026-11-18)
Plan: `docs/P3-work-packages.md`.

| WP | Owner role | Status | Notes |
|---|---|---|---|
| C3 contracts | backend-builder | DONE (425 BE tests with DB, 31 schema tests; `world_state.py`, `events.py` `PlanSpeaker.order/reason`, `SceneEvent(delta, merged)`, `StateEvent(state: WorldState, changed, confidence)`, `ChatCreate`/`ChatSummary` world fields, `StatePatch`; lead added `WorldState` & `StatePatch` to `export_schema.py` + ran `gen:types`, fixed `ChatView.tsx` optional `character_name`) | wave 1 |
| T scene parser + world assembly | backend-builder | DONE (466 BE tests with DB, 41 new pipeline tests; `scene_parser.py` chunk-safe `<scene` stream filter, lenient JSON repair, `per_character`/`single_call` merge, `visible_scene`; `world_assembly.py` + 5 `_shared/*.j2` templates; safety checks entire cast for `age_required` and applies `minor_rule` last for present+arriving+speaker+persona+npcs) | wave 1 |
| Q1 FE world-chat client | frontend-builder | DONE (122 FE tests incl. 8 new, lint/typecheck/build pass; `store.ts` multi-speaker `speakerOrder`/`speakerBuffers` + `liveScene`/`liveState`/`liveBonds`; `api.ts`/`hooks.ts` `patchState` + `usePatchState` + optional `speaker` on `promptPreview`; `useTurnStream.ts` mid-turn cache sync) | wave 2 |
| U agents for world chat | backend-builder | DONE (481 BE tests incl. 15 new WP-U agent tests, mypy strict 103 files, ruff clean; `core/config.py` thresholds from `group.py`; `orchestrator.run_world` + `nearby_locations` + `mentioned` + strict question budget; `state_keeper` concurrent Decisions+Extractions with hysteresis 0.5/0.2 & `keep_day`; `bond_drafter.world_pairs` + `bonds_for_speaker` respecting `by_character` pins) | wave 2 |
| V world turn pipeline + API | backend-builder | DONE (502 BE tests incl. 21 new `test_world_chat` + `test_world_turn` across fake+PG, mypy strict 104 files, ruff 172 files; `world_turn.py` `per_character` & `single_call`, `<scene>` stream filter + Director stripping, `StateKeeper`, `/force`, `ChatService` world `create`/`patch_state`/`prompt-preview?speaker=`, `chats_repo` `world_id`/`opening_id`) | wave 3 |
| W FE world chat UI | frontend-builder | DONE (135 FE tests incl. 13 new, lint/typecheck/build pass, 0 color/token hits; `newWorldChat/` 4-step flow + `WorldEditor` Chat button; `state/LiveStateEditor` + `ChatChrome` right-sidebar tabs + `ChatSettingsPanel` world group settings; `MessageList`/`StreamingBubble` per-speaker avatars & buffers; `WorldPromptInspector` with speaker selector; `vi.ts` updated) | wave 3 |
| QA + review + smoke | qa-runner + lead-reviewer + lead | DONE (QA & lead review completed; fixed 1 blocker + 3 major + 7 minor: absent minors included in `minor_rule` for `narrator` & `single_call` `safety_cast_ids`; world with `openings=[]` allows `opening_id=null`; `single_call` live `DraftEvent` + Director retry `ResetContentEvent(message_id="group")` + FE `StreamingBubble`/`store.ts` support; skip `_apply_scene_delta` on stopped stream; `useTurnStream` refreshes after completed speaker on mid-turn `error`; `bond_drafter` `max_tokens` scales with pair count; `WorldPromptInspector`/`ChatView` default speaker & `"group"` preview; `ChatChrome` mobile close-button clearance; translated bond change field names; lock `LiveStateEditor` during active turn; E-ink `Check` icon in `WorldPicker`; missing `vi.ts` error/notice codes added. Final gates: BE 508 passed, FE 137 passed + build, smoke_single_chat & smoke_world_chat PASS) | wave 4 |

### P4 carry-over (from P3)
- Split oversized P3 files in a hygiene pass: `backend/app/pipeline/world_turn.py` (~1,130 lines), `backend/app/services/chat_service.py` (~740 lines), `backend/app/agents/orchestrator.py` (combined single + world prompts).
- Run interactive browser visual check at `375px` and `1440px` in both OLED Neon and E-ink themes once the app is opened with a real OpenRouter key, plus live turn smoke tests against OpenRouter Models (`deepseek/deepseek-v4.1-flash-1017`, `microsoft/microsoft-decision-1`).
- Prompt preview `group` mode vs individual character settings: revisit whether `resolve_preview_speaker` should keep `write_mode="per_character"` when inspecting a single character inside a `single_call` chat.

### P4 · Memory / Archivist: DONE (2026-11-19)
Plan: `docs/P4-work-packages.md`. Includes Stage 0 live OpenRouter E2E smoke test (`scripts/dev/smoke_live_openrouter.py`) passing against real OpenRouter (`GET /api/models` 478 models; Single Chat + World Chat live turns with Decisions/Extractions/Writer/Director/Bonds/State Keeper).

| WP | Owner role | Status | Notes |
|---|---|---|---|
| M4 BE Archivist & memory | backend-builder | DONE (522 BE tests with DB, ruff 176 files, mypy strict 106 files; `archivist.py` + `archivist/*.j2`, `messages_repo` `MemorySnapshot` CRUD, `pipeline/memory.py`, `CorrectionTable` feedback from real Writer `prompt_tokens`, `unsummarized_records` history replacement, `MAX_EVENTS=24` + `priority` markers + `overwrite_unpinned` bond refresh, `POST /api/chats/{id}/summarize`; lead updated strict `state == {"bonds": {}}` assertions in `test_chats_api.py` & `test_turn.py`) | wave 1 |
| FE4 FE Memory UI & settings | frontend-builder | DONE (146 FE tests across 18 files, lint/typecheck/build clean, 0 color/UI-literal hits; `MemorySection.tsx` in `LiveStateEditor` & single-chat `ChatSettingsPanel`, `memory.context_length` + `summarize_at` controls, `useSummarizeChat`, `archivist` SSE cache sync, `vi.ts` updated) | wave 2 |

### P5 · Chat UX: DONE (2026-11-19)
Plan: `docs/P5-work-packages.md`.

| WP | Owner role | Status | Notes |
|---|---|---|---|
| C5 P5 contracts & TS types | lead | DONE (`ContinueRequest`, `RegenerateRequest`, `MessageUpdate`, `ActiveVariantRequest`, `ForkRequest`, `UndoResult`, `parent_chat_id` & `forked_at_seq` exported & `gen:types` verified) | wave 1 |
| B5 BE chat actions & commands | backend-builder | DONE (534 BE tests with DB, ruff 178 files, mypy strict 107 files; `/time`, `/move`, `/addnpc`, `/removenpc`, `/listnpc`, `/clearnpc` via `state_commands.py`, anti-repeat `0.6` rewrite + Director rejudge, `continue` skipping `answers_last`/`no_new_events`, `regenerate` + `active-variant` swipe, `PATCH` edit, `DELETE` rewind, `undo`, `fork` copying messages/variants/snapshots/links + `parent_chat_id`/`forked_at_seq`; lead updated `test_world_turn.py` `/time` assertion) | wave 2 |
| F5 FE chat actions & fork tree | frontend-builder | DONE (161 FE tests across 18 files, lint/typecheck/build/prettier clean, 0 color/UI-literal hits; `MessageBubble` swipe/regen/edit/delete/fork, `ChatInput` Continue/Undo + `/` command history in `vietrp_cmd_history`, `NoticeList` command details, `RecentChats` search/group/fork tree + `ChatView` parent link) | wave 3 |

### P6 · Creator & Card Judge: DONE (2026-11-19, lead-reviewed)
Plan: `docs/P6-work-packages.md`.

| WP | Owner role | Status | Notes |
|---|---|---|---|
| B6 BE Creator & Card Judge | backend-builder | DONE (556 BE tests with DB, ruff 187 files, mypy strict 113 files; `creator/pools/*.json`, `card_judge.py` + 18 `.j2` Templates with deterministic safety gate, `creator.py` + 7 `.j2` interview/`draft_raw`/`format_json` + repair, `creator_repo.py` over `creator_sessions`, `characters_repo.py` `judge_score`, `/api/creator/*` + `POST /api/{characters,worlds}/{id}/judge`; lead ran `export_schema` + `npm run gen:types`) | wave 1 |
| F6 FE Creator UI & Judge panel | frontend-builder | DONE (168 FE tests across 19 files, lint/typecheck/build clean) | wave 2 |
| Lead review | lead (Claude) | DONE (gates: BE 559 incl. 3 new, FE 168. **Safety fix:** Creator prompts had no under-18 rule; added `safety.creator_rule()` + `_shared/creator_minor_rule.j2`, sent as a system message in interview, draft_raw and format calls; fails closed; tests in `tests/agents/test_creator_safety.py`. Default `_shared/system.j2` rewritten so characters take initiative and do not end every turn with a question. Removed the dev DB password from `scripts/dev/create-dev-db.sql`. Repo initialised and pushed to GitHub) | review |

### Writer reasoning (2026-11-19, lead)
- `settings.writer.reasoning` (`off|auto|low|medium|high`, default `medium`) → OpenRouter `reasoning`; `WRITER_REASONING_EXTRA_TOKENS = 4000` added to the Writer budget when on.
- New SSE event `reasoning {delta, attempt}` (architecture §8 and AGENTS §4.5 updated). Saved as `meta.reasoning` of the chosen attempt (single + world, per_character + single_call).
- FE: `ReasoningBlock` (open while thinking with a seconds counter, collapsed after; saved reasoning on the newest variant), "Suy luận" select in chat settings.
- Gates: BE 565, FE 173. Live check on a throwaway vault: reasoning starts ~1 s after `speaker_start`, reply follows ~2.5 s later. Not visually checked in the browser.
- Follow-up: with reasoning on, Director retries make a turn ~20-25 s; consider `hold_until_approved` or fewer retries.

### Lorebooks per chat (2026-11-19, lead)
- Card/world lorebook picker has an "Nhập file" button: imported ST World Info is ticked right away.
- `settings.lorebook.book_ids` (null = card/world links from `pack`, exposed as `ChatOut.default_lorebook_ids`); edited in chat settings with the same picker; "Về lại lorebook của card" resets to null. Books are still loaded through `load_books` (own or public only).
- Gates: BE 569, FE 176. Not visually checked in the browser.

### Later phases
P6 creator · P7 deploy. See KIEN-TRUC §13.
