from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.formats.lorebook import LorebookEntry
from app.pipeline import lorebook as lb
from app.repositories.lorebooks_repo import LorebookRecord

VAULT = uuid.uuid4()
OTHER = uuid.uuid4()


def entry(eid: str, **kw: object) -> LorebookEntry:
    values: dict[str, object] = {"id": eid, "content": f"nội dung {eid}", "keys": [eid]}
    values.update(kw)
    return LorebookEntry.model_validate(values)


def book(entries: list[LorebookEntry], **kw: object) -> lb.LoreBook:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "vault_id": VAULT,
        "visibility": "private",
        "name": "b",
        "entries": tuple(entries),
        "token_budget": 10_000,
    }
    values.update(kw)
    return lb.LoreBook(**values)  # type: ignore[arg-type]


def ids(hits: list[lb.LoreHit]) -> list[str]:
    return [hit.entry.id for hit in hits]


def test_keyword_case_insensitive_and_scan_depth() -> None:
    b = book([entry("rong", keys=["Rồng"])], scan_depth=2)
    assert ids(lb.select([b], ["có con RỒNG"], vault_id=VAULT, mode="keyword").hits) == ["rong"]
    # The keyword is 3 messages back; depth 2 does not see it.
    assert lb.select([b], ["rồng", "a", "b"], vault_id=VAULT, mode="keyword").hits == []


def test_disabled_and_empty_keys_ignored() -> None:
    b = book([entry("a", enabled=False), entry("b", keys=[]), entry("c", keys=["  "])])
    assert lb.select([b], ["a b c"], vault_id=VAULT, mode="keyword").hits == []


def test_selective_requires_secondary() -> None:
    b = book([entry("kiem", selective=True, secondary_keys=["đền"])])
    assert lb.select([b], ["kiem"], vault_id=VAULT, mode="keyword").hits == []
    assert ids(lb.select([b], ["kiem trong đền"], vault_id=VAULT, mode="keyword").hits) == ["kiem"]


def test_selective_without_secondary_keys_behaves_as_plain() -> None:
    b = book([entry("x", selective=True, secondary_keys=[])])
    assert ids(lb.select([b], ["x"], vault_id=VAULT, mode="keyword").hits) == ["x"]


def test_constant_always_included() -> None:
    b = book([entry("luat", constant=True, keys=[])])
    sel = lb.select([b], ["không liên quan"], vault_id=VAULT, mode="keyword")
    assert ids(sel.hits) == ["luat"]
    assert sel.hits[0].reason == "constant"


def test_priority_order_and_budget_drops_lowest() -> None:
    big = "từ " * 40
    low = entry("low", priority=1, content=big)
    high = entry("high", priority=9, content=big)
    one_cost = lb._entry_tokens(high)
    b = book([low, high], token_budget=one_cost + 1)
    sel = lb.select([b], ["low high"], vault_id=VAULT, mode="keyword")
    assert ids(sel.hits) == ["high"]
    assert ids(sel.dropped_over_budget) == ["low"]


def test_priority_orders_hits() -> None:
    b = book([entry("a", priority=1), entry("b", priority=5)])
    assert ids(lb.select([b], ["a b"], vault_id=VAULT, mode="keyword").hits) == ["b", "a"]


def test_budget_is_per_book() -> None:
    b1, b2 = book([entry("a")], token_budget=0), book([entry("b")])
    sel = lb.select([b1, b2], ["a b"], vault_id=VAULT, mode="keyword")
    assert ids(sel.hits) == ["b"]


def test_position_split() -> None:
    b = book([entry("a", position="after_char"), entry("b", position="before_char")])
    sel = lb.select([b], ["a b"], vault_id=VAULT, mode="keyword")
    before, after = lb.order_by_position(sel.hits)
    assert ids(before) == ["b"]
    assert ids(after) == ["a"]


def test_hybrid_candidates_capped_and_ranked() -> None:
    b = book([entry(f"e{i}", priority=i, keys=[f"zz{i}"]) for i in range(30)])
    sel = lb.select([b], ["không khớp"], vault_id=VAULT, mode="hybrid", max_candidates=5)
    assert sel.hits == []
    assert ids(sel.candidates) == ["e29", "e28", "e27", "e26", "e25"]
    default = lb.select([b], ["không khớp"], vault_id=VAULT, mode="hybrid")
    assert 0 < len(default.candidates) <= 12


def test_hybrid_excludes_matched_entries() -> None:
    b = book([entry("hit"), entry("other", keys=["yy"])])
    sel = lb.select([b], ["hit"], vault_id=VAULT, mode="hybrid")
    assert ids(sel.hits) == ["hit"]
    assert ids(sel.candidates) == ["other"]


def test_keyword_mode_has_no_candidates_and_ai_mode_has_no_keyword_hits() -> None:
    b = book([entry("a"), entry("c", constant=True)])
    assert lb.select([b], ["x"], vault_id=VAULT, mode="keyword").candidates == []
    ai = lb.select([b], ["a"], vault_id=VAULT, mode="ai")
    assert ids(ai.hits) == ["c"]
    assert ids(ai.candidates) == ["a"]


def test_ai_select_mode_entry_never_keyword_matches() -> None:
    b = book([entry("a", select_mode="ai")])
    sel = lb.select([b], ["a"], vault_id=VAULT, mode="hybrid")
    assert sel.hits == []
    assert ids(sel.candidates) == ["a"]


def test_foreign_private_book_excluded_public_included() -> None:
    private = book([entry("a")], vault_id=OTHER, visibility="private")
    public = book([entry("b")], vault_id=OTHER, visibility="public")
    sel = lb.select([private, public], ["a b"], vault_id=VAULT, mode="keyword")
    assert ids(sel.hits) == ["b"]
    custom = lb.select([public], ["b"], vault_id=VAULT, mode="keyword", visible=lambda _b: False)
    assert custom.hits == []


def test_promote_accepts_candidates() -> None:
    b = book([entry("a", keys=["q"])])
    sel = lb.select([b], ["nothing"], vault_id=VAULT, mode="hybrid")
    promoted = lb.promote(sel, ["a", "unknown"])
    assert ids(promoted.hits) == ["a"]
    assert promoted.candidates == []


class FakeRepo:
    def __init__(self, records: dict[uuid.UUID, LorebookRecord]) -> None:
        self.records = records

    async def get_visible(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> LorebookRecord | None:
        return self.records.get(lorebook_id)


def record(owner: uuid.UUID, visibility: str, entries: list[dict[str, object]]) -> LorebookRecord:
    now = datetime.now(UTC)
    return LorebookRecord(
        id=uuid.uuid4(),
        vault_id=owner,
        visibility=visibility,
        name="r",
        settings={"scan_depth": 3, "token_budget": 99},
        created_at=now,
        updated_at=now,
        author="a",
        entries=entries,
    )


async def test_load_books_rechecks_visibility_and_skips_bad_entries() -> None:
    own = record(VAULT, "private", [{"id": "a", "keys": ["a"], "content": "x"}, {"id": "BAD ID"}])
    stale_link = record(OTHER, "private", [])  # the link outlived the book's public status
    public = record(OTHER, "public", [])
    repo = FakeRepo({r.id: r for r in (own, stale_link, public)})
    books = await lb.load_books(repo, VAULT, [own.id, stale_link.id, public.id, uuid.uuid4(), own.id])
    assert [b.id for b in books] == [own.id, public.id]
    assert [e.id for e in books[0].entries] == ["a"]
    assert (books[0].scan_depth, books[0].token_budget) == (3, 99)
