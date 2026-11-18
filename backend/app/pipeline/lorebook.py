"""Lorebook selection (architecture section 4.4), after `viet-rp-glow/src/utils/promptBuilder.ts`.

Pure and DB-free: callers hand over already-loaded books. `load_books` is the one async helper and it
re-checks visibility for every id, because `lorebook_links` can outlive a book's public status.
"""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import ValidationError

from app.core.config import LORE_AI_CANDIDATES
from app.formats.lorebook import Lorebook, LorebookEntry
from app.llm.tokenizer import count_text
from app.repositories.lorebooks_repo import LorebookRecord

LoreMode = Literal["keyword", "ai", "hybrid"]


@dataclass(frozen=True, slots=True)
class LoreBook:
    id: uuid.UUID
    vault_id: uuid.UUID
    visibility: str
    name: str
    entries: tuple[LorebookEntry, ...]
    scan_depth: int = 50
    token_budget: int = 500


@dataclass(frozen=True, slots=True)
class LoreHit:
    book_id: uuid.UUID
    entry: LorebookEntry
    tokens: int
    reason: Literal["constant", "keyword", "candidate"]


@dataclass(slots=True)
class LoreSelection:
    """`hits` go straight into the prompt; `candidates` are for the Orchestrator to judge (hybrid/ai only)."""

    hits: list[LoreHit] = field(default_factory=list)
    candidates: list[LoreHit] = field(default_factory=list)
    dropped_over_budget: list[LoreHit] = field(default_factory=list)


class _LorebookReader(Protocol):
    async def get_visible(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> LorebookRecord | None: ...


def is_visible(book: LoreBook, vault_id: uuid.UUID) -> bool:
    return book.vault_id == vault_id or book.visibility == "public"


def book_from_record(record: LorebookRecord) -> LoreBook:
    """Convert a repository record; entries that fail validation are skipped, never fatal."""
    entries: list[LorebookEntry] = []
    for raw in record.entries:
        try:
            entries.append(LorebookEntry.model_validate(raw))
        except ValidationError:
            continue
    defaults = Lorebook(name=record.name or "lorebook")
    scan_depth = record.settings.get("scan_depth")
    token_budget = record.settings.get("token_budget")
    return LoreBook(
        id=record.id,
        vault_id=record.vault_id,
        visibility=record.visibility,
        name=record.name,
        entries=tuple(entries),
        scan_depth=scan_depth if isinstance(scan_depth, int) and scan_depth >= 1 else defaults.scan_depth,
        token_budget=token_budget if isinstance(token_budget, int) and token_budget >= 0 else defaults.token_budget,
    )


async def load_books(repo: _LorebookReader, vault_id: uuid.UUID, lorebook_ids: Iterable[uuid.UUID]) -> list[LoreBook]:
    """Load books the vault may see right now (own or public); everything else is silently dropped."""
    books: list[LoreBook] = []
    for lorebook_id in dict.fromkeys(lorebook_ids):
        record = await repo.get_visible(vault_id, lorebook_id)
        if record is None:
            continue
        book = book_from_record(record)
        if is_visible(book, vault_id):
            books.append(book)
    return books


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _contains_any(haystack: str, keys: Iterable[str]) -> bool:
    return any(folded and folded in haystack for folded in (_fold(key.strip()) for key in keys))


def _keyword_match(entry: LorebookEntry, text_by_depth: str) -> bool:
    if not entry.keys or not _contains_any(text_by_depth, entry.keys):
        return False
    if entry.selective and entry.secondary_keys:
        return _contains_any(text_by_depth, entry.secondary_keys)
    return True


def _entry_tokens(entry: LorebookEntry) -> int:
    return count_text(f"{entry.title}: {entry.content}" if entry.title else entry.content)


def _keyword_eligible(mode: LoreMode, entry: LorebookEntry) -> bool:
    return mode != "ai" and entry.select_mode != "ai"


def _ai_eligible(mode: LoreMode, entry: LorebookEntry) -> bool:
    # The global mode decides. `select_mode` defaults to "keyword" on every entry, so honouring it here would make
    # hybrid mode a no-op for ordinary books; per-entry `select_mode` only stops keyword matching (see above).
    del entry
    return mode in ("ai", "hybrid")


def select(
    books: Sequence[LoreBook],
    recent_texts: Sequence[str],
    *,
    vault_id: uuid.UUID,
    mode: LoreMode = "hybrid",
    max_candidates: int = LORE_AI_CANDIDATES,
    visible: Callable[[LoreBook], bool] | None = None,
) -> LoreSelection:
    """Pick lore for one turn.

    - `keyword`: constant + keyword hits only.
    - `hybrid`: the same hits, plus up to `max_candidates` other entries for the Orchestrator.
    - `ai`: no automatic hits except constants; every enabled non-constant entry competes for the candidate slots.
    Per entry, `select_mode == "ai"` never matches by keyword.
    Hits are ordered by priority (high first) and trimmed to each book's token budget.
    """
    is_ok = visible if visible is not None else (lambda book: is_visible(book, vault_id))
    result = LoreSelection()
    all_candidates: list[tuple[int, int, LoreHit]] = []
    order = 0
    for book in books:
        if not is_ok(book):
            continue
        scanned = _fold("\n".join(recent_texts[-book.scan_depth :]))
        matched: list[tuple[int, int, LoreHit]] = []
        for entry in book.entries:
            order += 1
            if not entry.enabled:
                continue
            tokens = _entry_tokens(entry)
            if entry.constant:
                matched.append((entry.priority, order, LoreHit(book.id, entry, tokens, "constant")))
            elif _keyword_eligible(mode, entry) and _keyword_match(entry, scanned):
                matched.append((entry.priority, order, LoreHit(book.id, entry, tokens, "keyword")))
            elif _ai_eligible(mode, entry):
                all_candidates.append((entry.priority, order, LoreHit(book.id, entry, tokens, "candidate")))
        matched.sort(key=lambda item: (-item[0], item[1]))
        spent = 0
        for _, _, hit in matched:
            if spent + hit.tokens > book.token_budget:
                result.dropped_over_budget.append(hit)
                continue
            spent += hit.tokens
            result.hits.append(hit)
    all_candidates.sort(key=lambda item: (-item[0], item[1]))
    result.candidates = [hit for _, _, hit in all_candidates[: max(0, max_candidates)]]
    return result


def order_by_position(hits: Sequence[LoreHit]) -> tuple[list[LoreHit], list[LoreHit]]:
    """Split into (before_char, after_char), keeping selection order inside each group."""
    before = [hit for hit in hits if hit.entry.position == "before_char"]
    after = [hit for hit in hits if hit.entry.position == "after_char"]
    return before, after


def promote(selection: LoreSelection, chosen_entry_ids: Iterable[str]) -> LoreSelection:
    """Move candidates the Orchestrator accepted into `hits` (budget is not re-applied: the model chose them)."""
    chosen = set(chosen_entry_ids)
    accepted = [hit for hit in selection.candidates if hit.entry.id in chosen]
    return LoreSelection(
        hits=[*selection.hits, *accepted],
        candidates=[hit for hit in selection.candidates if hit.entry.id not in chosen],
        dropped_over_budget=selection.dropped_over_budget,
    )
