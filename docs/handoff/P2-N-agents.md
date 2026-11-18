# WP-N hand-off: agent signatures for WP-O

The lead's condensed copy of the WP-N builder report (2026-11-18). Code: `backend/app/agents/*.py`. Tests: `tests/agents/`. Fixtures: `tests/fixtures/llm/{orchestrator,writer,director,bond_*}*.json`.

## Usage accounting
- `AgentResult.usage` is informational only. Emit `usage` SSE events from `ctx.llm.drain_usage()`, or usage is counted twice.
- Build `AgentContext(settings=...)` so the Decisions question budget comes from `decisions_max_questions`.

## Orchestrator
`orchestrator.run(ctx, cfg, OrchestratorInput) -> AgentResult[OrchestratorPlan]`. It never raises.

- **Input:** `OrchestratorInput(card, character_id, user_name, user_message, recent: Sequence[str] = (), candidates: Sequence[LoreHit] = ())`.
  - `recent` holds lines formatted `"Name: text"`.
  - `candidates` must be `LoreSelection.candidates`, never a whole book.
- **`OrchestratorPlan` fields:**
  - `turn_type`: `dialogue` / `action` / `narration`;
  - `speaker_id`: the `character_id`, or `"narrator"`;
  - `speaker_kind`: `character` / `narrator`;
  - `sentences`;
  - `addressed_to`: `character` / `nobody`;
  - `lore_entry_ids`, `card_fields`, `secret_ids`, `fallback`.
  - `.to_event()` returns a `PlanEvent`.
- **Then:**
  - `lorebook.promote(selection, plan.lore_entry_ids)`;
  - `AssemblyInput.card_fields = plan.card_fields`.
- **Secrets (WP-O must do this):** the assembler sends every secret on the card it gets.
  - Before assembly, filter `card.secrets` down to `plan.secret_ids`.
  - When `secret_ids` is empty, `"secrets"` is not in `card_fields`, so pass a card with `secrets = []` to be safe.
- **On failure:** a narrator plan with core fields, plus `Notice("orchestrator_fallback", agent="orchestrator")`.

## Writer
`writer.run(ctx, cfg, WriterInput) -> AsyncIterator[WriterDelta | WriterDone]`

- **Input:** `WriterInput(prompt: AssembledPrompt, fix_hints: Sequence[str] = (), rejected_draft: str | None = None)`.
- **Output:** `WriterDelta(text)` per chunk, then `WriterDone(text, finish_reason, usage)`.
- **Early stop:** there is no `WriterDone`. Keep the accumulated deltas as the `stopped` partial. Closing the iterator closes the upstream stream, and usage so far is still recorded.
- **Retry hints** are a user-role message placed before the prefill, never a system layer, so the safety rule stays the last system layer.

## Director
`director.run(ctx, cfg, DirectorInput) -> AgentResult[DirectorOutcome]`

- **Input:** `DirectorInput(character_name, user_name, user_message, draft, attempt=0)`.
- **Outcome:**
  - `verdict` is a `DirectorVerdict`, the body of the `director` event. Store `verdict.model_dump()` in the variant's `director` JSON.
  - `.passed`, `.score`, and `.priority` (0–2), which goes in `meta.priority`.
- **Helpers:**
  - `director.fix_hints(verdict) -> list[str]` feeds `WriterInput.fix_hints`;
  - `director.better(a, b)` keeps the higher score (ties keep `a`).
- **Criteria:** `answers_last`, `no_new_events`, `no_player_voice`, `no_assistant_voice`. `probability` always means "satisfied". `no_new_events` is waived when the player led the event (`user_led`).
- **Errors:** LLM errors are not caught. Wrap the call in `run_non_critical`; on failure, keep the draft.
- **Threshold:** default 0.8.

## Bonds (single chat: first user message only)
- `bond_drafter.user_pair(card, character_id, persona, user_fallback) -> BondPair`. The pair id is `"{character_id}:user"`. Pinned values come from `card.addressing.user` and `card.relationships.user`.
- `bond_drafter.run(ctx, cfg, DrafterInput(pairs, opening="")) -> AgentResult[DraftedBonds]`.
  - A malformed reply gives empty options + `Notice("bond_drafter_malformed")`.
  - Transport errors propagate: wrap the call in `run_non_critical`.
- `bond_selector.run(ctx, cfg, SelectorInput(pairs, drafted, opening="")) -> AgentResult[dict[str, BondFields]]`. When Decisions fails, the first option wins + `Notice("bond_selector_fallback")`.
- `bond_selector.apply_selection(existing, pairs, selected, seq, *, overwrite_unpinned=False) -> dict[str, BondRecord]`.
- `bond_drafter.bond_views(records) -> list[BondView]` builds the prompt layer and leaves out pinned fields.

## State
- `chat.state.bonds = {pair_id: BondRecord.model_dump()}`.
- A `BondRecord` holds `pair_id`, `label`, `fields` (addressing, nickname, relationship, stance, closeness 0–4, history), `pinned`, `manual`, and `changes` (`[{seq, field, old, new}]`).
- `PATCH /state` must add the edited field names to `manual`, so agents never overwrite them.

## Not wired
- Preset overrides (`PresetLayers`) are not applied to agent prompts; WP-M presets cover only the assembler's system/NSFW layers.
- The `/api/alpha/decisions` shape follows `llm/decisions.py`. It has not been tested live.
