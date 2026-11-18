# P3 — World chat (Chat Thực tại): work packages

Phase goal (KIEN-TRUC §13, P3): `mode = "world"` end to end.
- A world + opening + cast + persona.
- Orchestrator multi-speaker plans.
- `group.write_mode` `per_character` (default) and `single_call`.
- State Keeper for the structured state (location on the tree, time, tension, present, awaiting reply, silence).
- The `<scene>` block for free-form scene state.
- Bonds for every pair in the cast.
- The Live State Editor.

**Out of scope:** Archivist / summary (P4); swipe/regenerate, fork, undo, `/time` `/move` `/addnpc` (P5); Creator / Card Judge (P6).

Same team, rules and file-ownership discipline as P0–P2. Drafted by the lead at the end of P2 (2026-11-18). Read `docs/PROGRESS.md` (the "P3 carry-over" list) and `docs/handoff/P2-N-agents.md` first.

Reference (read-only): `vietrp-agent/backend/vietrp/engine/group.py`:
- `direct()`: arriving/addressee/owed/silence logic → our Orchestrator;
- `update_state()`: presence hysteresis 0.5 in / 0.2 out, chain reactions, `keep_day` → our State Keeper;
- `writer_messages()`: narrator vs. character roles, "don't write other main characters' lines".

## Waves

| Wave | WPs (parallel) | Depends on |
|---|---|---|
| 1 | **C3** contracts (world chat schemas, state shape, `scene`/`state` events filled in) · **T** scene parser + world assembler extensions | P2 |
| 2 | **U** agents: Orchestrator multi-speaker, State Keeper, bonds for N pairs · **Q1** FE world-chat client (store handles `scene`/`state`/`bonds`) | C3, T |
| 3 | **V** world turn pipeline + chats API for `world` · **W** FE: new world chat flow + Live State Editor + per-speaker bubbles | U, Q1 |
| 4 | qa-runner → lead smoke test (live backend) → fixes | all |

---

## WP-C3 · Contracts (backend-builder)

**Owns:** `backend/app/schemas/{chat,events,world_state}.py`, `backend/tests/schemas/**`, and the generated `frontend/src/types/generated/schemas/*.json` (export only).

**Build:**
- `ChatCreate` for world: `{mode: "world", world_id, opening_id, cast_ids: uuid[], persona_id?, title?, settings?}`. The single-chat fields stay as they are. `ChatSummary/ChatOut.mode` accept `"world"`.
- `WorldState` (KIEN-TRUC §4.5):
  - structured part: `location_id`, `time`, `tension` 0–4, `present_ids[]`, `awaiting_reply[]`, `silence{id: int}`;
  - `scene {env{}, chars{id: {mood, outfit, pose, holding, condition}}, items[]}`;
  - also `bonds{}`, `npcs[]`, and the P4 placeholders `summary`, `summary_upto`, `events[]`.
- Events:
  - `state {state: WorldState, changed: [keys], confidence: {key: p}}`;
  - `scene {delta, merged}`;
  - `plan.speakers` already supports several speakers; add `order` and `reason`.
- `StatePatch` for the Live State Editor. Every key above is editable; record `manual` keys like bonds.

## WP-T · Scene parser + world assembler (backend-builder)

**Owns:** `backend/app/pipeline/{scene_parser,world_assembly}.py`, `backend/app/prompts/_shared/{scene_instruction,world_rules,location_path,present_cast}.j2`, `backend/tests/pipeline/test_scene_*.py`, `test_world_assembly.py`.

**Build:**
- **`scene_parser`** (KIEN-TRUC §4.6, AGENTS §4.5):
  - a streaming filter that forwards text until `<scene` appears, then buffers the rest;
  - `parse(block) -> SceneDelta | None`, a lenient JSON parse with a light repair (trailing commas, single quotes); a broken block returns `None` plus a notice code `scene_parse_failed`;
  - `merge(scene, delta, speaker_id, mode)`: in `per_character` a speaker may only touch `chars.<self>`, `env` and `items`;
  - structured state wins: chars no longer present are hidden.
- **`world_assembly`**: extends `AssemblyInput` for world chat with world rules, the location path (`Trái Đất › … › Phố đi bộ`), the present cast lines, the speaker's role instruction (character vs. narrator, "do not write other main characters' lines"), the scene instruction (append a `<scene>` block with only what changed), and the bonds of every pair involving the speaker.
  - The safety cast is **everyone present + the persona + NPCs**, so `minor_rule` is applied when any of them is a minor and stays the last system layer.
  - Tests mirror `test_safety.py` for world assembly.

## WP-U · Agents for world chat (backend-builder)

**Owns:** `backend/app/agents/{orchestrator,state_keeper,bond_drafter,bond_selector}.py`. Changes to orchestrator and bonds are additive: keep the single-chat signatures working. Also `backend/app/prompts/{orchestrator,state_keeper,bond_*}/*.j2` and `backend/tests/agents/**` (new tests; existing ones keep passing).

**Build:**
- **Orchestrator `run_world`:**
  - candidates are present + arriving characters + narrator;
  - questions:
    - who the user addresses (atomic);
    - who speaks next and in what order, capped by `group.chain_max`;
    - who is arriving among the absent (`ARRIVE_THRESHOLD`);
    - lore and fields per speaker;
  - silence priority and owed replies, as in the reference;
  - nearby location nodes only (current, parent, siblings, children);
  - **question budget enforced**.
  - Fallback: narrator only + a notice.
- **`state_keeper`** (new, non-critical):
  - Decisions for presence with hysteresis (enter ≥ 0.5, leave only < 0.2, arriving 0.2);
  - `chen__` chain-reaction wishes; location `choice` among the nearby nodes; tension `score`;
  - Extractions for time, with the reference's `keep_day`;
  - returns `WorldState` plus confidences and the next-speaker suggestion.
  - Thresholds live in `core/config.py` with comments that cite the reference.
- **Bonds for N pairs:** drafter and selector over every character↔character and character↔persona pair. Pinned values come from `card.relationships.by_character` / `addressing.by_character`.

## WP-Q1 · FE world-chat client (frontend-builder)

**Owns:** additions in `frontend/src/features/chat/{api,hooks,store,useTurnStream}.ts`, `src/types/chat.ts`, and tests.

**Build:**
- The store handles `plan` with several speakers, `speaker_start`/`speaker_end` per speaker (separate buffers keyed by `message_id`), `scene`, `state` and `bonds`, so a live world state is available.
- Hooks for `PATCH /state` with the full `StatePatch`.

## WP-V · World turn pipeline + API (backend-builder)

**Owns:** `backend/app/pipeline/world_turn.py`, changes to `app/services/{chat_service,turn_service}.py` and `app/api/{chats,turns}.py` for the world mode, `backend/tests/chat/test_world_*.py`.

**Build** (KIEN-TRUC §5.2):
- **Create:**
  - `assert_cast_usable` for the whole cast;
  - snapshot the world, the cast and the opening into `pack`;
  - seq 0 = the opening message (speaker `narrator`);
  - initial state from the opening (`location_id`, `time`, `present_ids`, `tension`);
  - bonds for all pairs (non-critical).
- **Turn:**
  - commands → Orchestrator plan;
  - for each speaker in order (`per_character`): assemble (WP-T), Writer stream with the scene filter, Director with retries (P2 logic), `scene` merge, persist message + variant + `state_before` in one tx;
  - `single_call`: one Writer call with a speaker-tagged format, then split into messages;
  - after the last speaker, State Keeper (non-critical) → `state` → `done`;
  - stop/disconnect is handled per speaker.
- **API:**
  - `mode_unsupported` is removed for `world`;
  - `PATCH /state` accepts `StatePatch`;
  - prompt preview supports world chats (choose a speaker: `?speaker=`).

## WP-W · FE world chat UI (frontend-builder)

**Owns:**
- `frontend/src/features/chat/newWorldChat/**`
- `frontend/src/features/chat/state/**` (Live State Editor)
- small additions in `features/chat/components/{MessageList,MessageBubble}.tsx` for per-speaker avatars/names
- appended `worldChat.*` / `stateEditor.*` keys in `vi.ts`

**Build:**
- **New world chat:** pick world → swipe opening → pick cast (library cards; `needs_age` blocked) → persona → create.
- **Right sidebar tab "Trạng thái"** (KIEN-TRUC §9.1), the Live State Editor:
  - location picked from the world tree;
  - time, tension, the present list, awaiting reply;
  - the Scene section (env, per-character, items);
  - bonds;
  - every value is editable and goes through `PATCH /state`; manual edits are marked.
- Per-speaker bubbles with avatars; narrator style.
- Both themes, 375px, no gesture-only actions.

## Lead notes
- Keep the P2 single-chat path unchanged. Every existing chat test must still pass.
- Safety: the world cast includes every present character, the persona and NPCs. The lead re-verifies `minor_rule` placement in the world path by hand (prompt preview with a 16-year-old in the cast).
- Live LLM quality cannot be verified until the owner saves an OpenRouter key. After P3, ask the owner to try a real chat.
