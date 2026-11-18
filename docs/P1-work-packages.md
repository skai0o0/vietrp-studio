# P1 — Library: work packages

Phase goal (KIEN-TRUC-VIETRP.md §13, P1): CRUD for `vietrp-card`, `vietrp-world`, lorebook and persona; SillyTavern CCv2/CCv3 import/export; editing forms; Gallery (public library + favorites). **No chat, no agents** (P2+). Card Judge is P6.

The team, the rules and the file-ownership discipline are the same as P0 (`docs/P0-work-packages.md`, AGENTS.md §8–9). Backend port 7880; frontend dev port 5173.

## Waves

| Wave | WPs (parallel) | Depends on |
|---|---|---|
| 1 | **G** formats (models, validation, JSON Schema export) | P0 |
| 2 | **H** ST import/export · **I** library API · **J0** frontend types + library API client | G (H, I, J0); I calls H only through the function signatures in WP-H |
| 3 | **J** library pages + editors · **K** Gallery + import/export UI | I, J0 |
| 4 | qa-runner → lead review → fixes; run the DB tests against `vietrp_studio_test` | all |

---

## WP-G · Formats (backend-builder)

**Owns:** `backend/app/formats/**` (except `st_import.py`, `st_export.py`, `png.py`, which belong to WP-H), `backend/tests/formats/test_models*.py`, `backend/tests/formats/test_schema_export.py`, `frontend/src/types/generated/schemas/*.json` (generated output only).

**Build:**
1. Pydantic v2 models, defined once (AGENTS.md §4.6), in `formats/`:
   - `common.py`:
     - `Slug` (`^[a-z0-9_]{1,40}$`), `Visibility` (`public` | `private`), `SpecVersion`.
     - `FormatWarning {path, code, message}`: soft issues, not errors.
   - `card.py`: `VietrpCard`, exactly the fields in KIEN-TRUC §4.1:
     - `format = "vietrp-card"`, `spec_version = "1.0"`, `name` (1–80), `age: int | None` (0–10000; `None` only allowed via import, see below), `is_fictional: Literal[True]`, `aliases[]`, `tagline` (≤140).
     - Free-text fields: `appearance`, `personality`, `backstory`, `goals`.
     - `limits[]`, `secrets[{id: Slug, content, reveal_when}]`, `speech {style, catchphrases[], examples[]}`.
     - `addressing {default, user, by_character: dict[Slug, str]}`, `relationships {user, by_character: dict[Slug, str]}`.
     - `greetings[]`, `lorebook_ids: list[UUID]`, `extras: dict[Slug, str]`, `tags[]` (lowercase, ≤20, each ≤32).
     - `id`, `owner_id`, `created_at`, `updated_at` are **not** in the stored `data`; they live in DB columns and are added on export.
   - `world.py`: `VietrpWorld`, per §4.2:
     - `name`, `rules`, `tags[]`, `lorebook_ids[]`;
     - `locations[{id: Slug, parent_id: Slug | None, level, name, description}]`, with `level` ∈ `galaxy, star_system, planet, country, province, district, area, place`;
     - `openings[{id: Slug, title, message, time, location_id, present_ids[], tension 0–4, player_role}]`.
     - Validators: location ids unique; `parent_id` exists; no cycles; a child's level is deeper than its parent's level; `opening.location_id` exists.
   - `persona.py`: `Persona` per §4.3 (`name`, `aliases[]`, `age`, `gender`, `pronouns`, `appearance`, `personality`, `background`, `notes`).
   - `lorebook.py`:
     - `LorebookEntry {id: Slug, title, keys[], secondary_keys[], selective, constant, priority (int), position ("before_char" | "after_char"), select_mode ("keyword" | "ai" | "both"), content, enabled}`.
     - `Lorebook {name, description, scan_depth (default 50), token_budget (default 500), entries[]}`.
2. `formats/validate.py`:
   - `validate_card(data, *, allow_missing_age: bool) -> (VietrpCard, list[FormatWarning])`, and the same for world, persona and lorebook.
   - Soft warnings (do not reject):
     - a free-text field over 300 characters (`field_long`; the convention from KIEN-TRUC §4.1);
     - text written as an instruction, e.g. starting with "Hãy" or "Bạn là" (`imperative_text`);
     - `age is None` (`age_missing`).
   - `card_has_minor(card) -> bool` (`age is not None and age < 18`).
   - `is_nsfw_tagged(tags) -> bool` (`"nsfw"` in tags).
3. `formats/migrations/__init__.py`: `migrate(kind, data) -> data`, a registry keyed by `(kind, from_version)`. It is empty for 1.0, but the mechanism is tested with a fake 0.9 → 1.0 migrator in tests.
4. `formats/export_schema.py`: `python -m app.formats.export_schema <out_dir>` writes `vietrp-card.schema.json`, `vietrp-world.schema.json`, `persona.schema.json` and `lorebook.schema.json`. Run it, writing to `../frontend/src/types/generated/schemas/`.
5. Tests:
   - valid and invalid examples for every model;
   - every world tree validator (cycle, missing parent, level order);
   - the warnings;
   - `card_has_minor`;
   - the migrate registry;
   - the schema export is deterministic (byte-identical across runs).

---

## WP-H · SillyTavern import/export (backend-builder)

**Owns:** `backend/app/formats/{st_import,st_export,png}.py`, `backend/tests/formats/test_st_*.py`, `backend/tests/formats/test_png.py`, `backend/tests/fixtures/st/**`.

Reference (read-only): `vietrp-agent/backend/vietrp/engine/rpformat.py` and `llm.py` (PNG card reading), `viet-rp-glow/src/types/taverncard.ts`, `viet-rp-glow/src/utils/importCharacterJson.ts`.

**Signatures** (WP-I calls only these):

```python
@dataclass
class ImportResult:
    kind: Literal["character", "world", "lorebook"]
    data: dict                        # validated VietrpCard / VietrpWorld / Lorebook as JSON-ready dict
    avatar: tuple[bytes, str] | None  # (image bytes, mime) for PNG cards
    lorebook: dict | None             # embedded character_book converted to a Lorebook dict, if any
    warnings: list[FormatWarning]
    needs_age: bool

def import_file(content: bytes, filename: str) -> ImportResult          # raises FormatError(code, message)
def export_character(card: dict, *, fmt: Literal["vietrp","ccv2","ccv3"], as_: Literal["json","png"],
                     avatar: bytes | None, lorebook: dict | None, meta: dict) -> tuple[bytes, str, str]  # (body, mime, filename)
def export_world(world: dict, *, meta: dict) -> tuple[bytes, str, str]                      # vietrp json only
def export_lorebook(book: dict, *, fmt: Literal["vietrp","st"], meta: dict) -> tuple[bytes, str, str]
```

**Build:**
1. `png.py`: read and write tEXt chunks. Read `chara` (base64 CCv2 JSON) and `ccv3` (base64 CCv3 JSON; preferred when both exist). Write both chunks on export. Verify CRCs; reject non-PNG files; cap input at 20 MB.
2. Import detection by content:
   - `vietrp-card`, `vietrp-world`, vietrp `lorebook`;
   - CCv2 (`spec: chara_card_v2`), CCv3 (`spec: chara_card_v3`), and a V1-style bare `{name, description, ...}`;
   - ST World Info (`{entries: {...}}`).
   - Anything else raises `FormatError("format_unknown")`.
3. ST → vietrp mapping (KIEN-TRUC §4.1):
   - If `data.extensions.vietrp` exists, restore it **losslessly** and skip heuristics.
   - Otherwise:
     - `description` → `backstory`/`appearance` heuristics are not required; put the description in `personality` if it is short, else in `extras.description`;
     - `personality` → `personality`; `first_mes` + `alternate_greetings` → `greetings`;
     - `mes_example` → `speech.examples` (split on `<START>`, strip `{{char}}:` prefixes);
     - `scenario` → `extras.scenario`; `creator_notes` → `extras.creator_notes`;
     - `tags` → `tags`; `character_book` → `ImportResult.lorebook`;
     - replace `{{char}}` with the name; keep `{{user}}` as-is.
   - Age: parse an explicit age only (e.g. "20 tuổi", "age: 20", "20 years old"). Otherwise `None`, and set `needs_age = True`. Never guess (AGENTS.md §4.6).
   - Always set `is_fictional: True`.
4. vietrp → ST export: compose `description`, `personality`, `scenario`, `first_mes` (= `greetings[0]`), `alternate_greetings`, `mes_example` (`<START>` blocks), `tags`, and `character_book` from the lorebook. Store the full vietrp card + lorebook in `data.extensions.vietrp`. CCv3 also sets `spec_version: "3.0"` and the v3 fields it needs.
5. World Info import/export maps `keys`, `keysecondary`, `selective`, `constant`, `order`/`insertion_order` → `priority`, `position`, `content`, `comment` → `title`, and `disable` → `enabled`.
6. Tests with fixtures in `tests/fixtures/st/` (small hand-made CCv2 JSON, CCv3 JSON, a PNG built in the test with both chunks, a World Info JSON):
   - each import path;
   - age parsing (explicit → int; none → `None` + `needs_age`);
   - **round-trip vietrp → ccv2 / ccv3 json / png → vietrp equals the original** (mandatory);
   - a corrupt PNG CRC is rejected;
   - an unknown format is rejected.

---

## WP-I · Library API (backend-builder)

**Owns:**
- `backend/app/api/{library,gallery,assets,io}.py`
- registration lines in `backend/app/api/__init__.py`
- `backend/app/schemas/library.py`
- `backend/app/services/{library_service,gallery_service,asset_service,io_service}.py`
- `backend/app/repositories/{characters_repo,worlds_repo,personas_repo,lorebooks_repo,favorites_repo,assets_repo}.py`
- `backend/tests/library/**`

Do not edit models or migrations. If a column is missing, report it; the lead adds migration `0002`.

Rules:
- Every route requires the vault (`require_vault`), except none: Gallery also needs an unlocked vault, because the app is private.
- Owned queries take `vault_id`. A private item owned by another vault returns **404 `not_found`**, never 403, so its existence does not leak.
- `data` is validated with WP-G validators on every write. `age` may be `null` only for cards created through import, and such cards keep `needs_age: true` until they are edited with an age.
- **Minor + NSFW guard** (AGENTS.md §2.1): saving a card with `visibility = public` while `card_has_minor` and `is_nsfw_tagged` are both true → 422 `nsfw_minor_public`. Put this in `library_service` with a test; P2 moves the shared rules into `pipeline/safety.py`.
- `lorebook_links` is kept in sync with `lorebook_ids` in card/world data on every save (in the same transaction).

**API contract** (WP-J0, J and K build against this exactly):

| Method + path | Request | Success | Errors |
|---|---|---|---|
| `GET /api/characters` | `?q=&tag=&limit=(≤100, default 30)&cursor=` (own vault only) | 200 `{items: CharacterSummary[], next_cursor: string \| null}` | 401 |
| `POST /api/characters` | `{data: VietrpCard, visibility}` | 201 `{character: CharacterOut}` | 422 `validation_error` / `nsfw_minor_public` |
| `GET /api/characters/{id}` | — | 200 `{character: CharacterOut}` (own, or public of any vault) | 404 |
| `PUT /api/characters/{id}` | `{data, visibility}` | 200 `{character}` | 404, 422 |
| `DELETE /api/characters/{id}` | — | 204 | 404 |
| `POST /api/characters/{id}/duplicate` | — | 201 `{character}`: a private copy in your vault (works on public items of other vaults) | 404 |
| `PUT /api/characters/{id}/avatar` | multipart `file` (png/jpeg/webp, ≤ 5 MB) | 200 `{character}` | 404, 413 `file_too_large`, 415 `unsupported_media` |
| `DELETE /api/characters/{id}/avatar` | — | 200 `{character}` | 404 |
| `GET /api/characters/{id}/export` | `?format=vietrp\|ccv2\|ccv3&as=json\|png` | 200 file download (`Content-Disposition: attachment`) | 404, 422 |
| *the same 9 routes for* `/api/worlds` | (`cover` instead of `avatar`; export only `format=vietrp&as=json`) | `WorldSummary` / `WorldOut` | |
| `GET/POST /api/personas`, `GET/PUT/DELETE /api/personas/{id}`, `PUT/DELETE /api/personas/{id}/avatar` | `{data: Persona}` | `{items: PersonaOut[]}` / `{persona: PersonaOut}` | 404, 422 |
| `GET/POST /api/lorebooks`, `GET/PUT/DELETE /api/lorebooks/{id}`, `POST /api/lorebooks/{id}/duplicate`, `GET /api/lorebooks/{id}/export?format=vietrp\|st` | `{data: Lorebook, visibility}` | `{items: LorebookSummary[], next_cursor}` / `{lorebook: LorebookOut}` | 404, 422 |
| `GET /api/gallery` | `?type=character\|world&q=&tag=&sort=recent\|favorites&limit=&cursor=` | 200 `{items: GalleryItem[], next_cursor}`: public items of all vaults | 401 |
| `GET /api/favorites` | — | 200 `{items: GalleryItem[]}` | 401 |
| `PUT /api/favorites/{target_type}/{id}` / `DELETE …` | — | 204 | 404 |
| `POST /api/import` | multipart `file` (.json/.png, ≤ 20 MB) | 201 `{kind, character?: CharacterOut, world?: WorldOut, lorebook?: LorebookOut, warnings: FormatWarning[], needs_age: bool}` | 413 `file_too_large`, 415 `unsupported_media`, 422 `format_unknown` / `invalid_json` / `png_invalid` / `png_crc_mismatch` / `png_no_card` / `png_card_invalid` / `card_invalid` / `world_invalid` / `lorebook_invalid` (granular codes from WP-H, adopted at P1 review) |
| `GET /api/assets/{asset_id}` | — | 200 image bytes with `Cache-Control: private, max-age=86400`; allowed when the asset is yours or belongs to a public item | 404 |

Shapes:
- `CharacterSummary = {id, name, tagline, tags, visibility, avatar_url: string | null, needs_age: bool, updated_at}`
- `CharacterOut = CharacterSummary + {data: VietrpCard, is_owner: bool, author: string (vault display_name), created_at, warnings: FormatWarning[]}`
- `WorldSummary` / `WorldOut` mirror these, with `cover_url`.
- `PersonaOut = {id, data: Persona, avatar_url, created_at, updated_at}`.
- `LorebookSummary = {id, name, entry_count, visibility, updated_at}`; `LorebookOut = LorebookSummary + {data: Lorebook, is_owner, author}`.
- `GalleryItem = {type, id, name, tagline, tags, image_url, author, is_owner, is_favorite, favorite_count, updated_at}`.
- `avatar_url` / `cover_url` / `image_url` = `/api/assets/{asset_id}` or `null`.
- Cursor = opaque base64 of `(updated_at, id)`.

**Tests:** CRUD for each type, plus the import → export round-trip through the API, using in-memory fake repositories like `tests/vault/fakes.py`. Also:
- the vault isolation matrix (own, other private → 404, other public → read-only, and PUT/DELETE on another vault's public item → 404);
- `nsfw_minor_public`;
- `lorebook_links` sync;
- the asset access rules;
- the cursor pagination.

Postgres variants run when `VIETRP_TEST_DATABASE_URL` is set.

---

## WP-J0 · Frontend types + library API client (frontend-builder)

**Owns:** `frontend/package.json` (adding `json-schema-to-typescript` as a dev dependency and a `gen:types` script only), `frontend/scripts/gen-types.mjs`, `frontend/src/types/generated/*.ts` (generated), `frontend/src/features/library/api.ts`, `frontend/src/features/library/hooks.ts`, `frontend/src/features/gallery/api.ts`, `frontend/src/features/gallery/hooks.ts`, `frontend/src/types/library.ts` (API response shapes from WP-I, hand-written), tests for these.

**Build:**
- `npm run gen:types` turns `src/types/generated/schemas/*.json` into `.ts` files.
- Typed fetchers and TanStack Query hooks for every WP-I route:
  - query keys: `["characters", params]`, `["character", id]`, and so on;
  - mutations invalidate the matching lists;
  - multipart upload helper; download helper (export via `fetch` → blob → `a[download]`).
- Infinite queries for cursor lists.
- Tests with mocked fetch.

---

## WP-J · Library pages + editors (frontend-builder) — wave 3

**Owns:**
- `frontend/src/features/library/**`, except the `api.ts`, `hooks.ts` and tests from J0
- `frontend/src/pages/{LibraryPages,DetailPages}.tsx` (replace the placeholders)
- route elements in `src/app/router.tsx` for the `/library/*`, `/characters/:id` and `/worlds/:id` lines only
- appended `library.*` keys in `vi.ts`

**Build** (KIEN-TRUC §9.2):
1. Pages:
   - `/library/characters`, `/library/worlds`, `/library/personas`, `/library/lorebooks`;
   - each has a search box, a tag filter where relevant, a responsive grid of cards (avatar/cover, name, tagline, a "Thiếu tuổi" badge when `needs_age`, a public/private badge), "Tạo mới", and an empty state.
2. Detail/editor `/characters/:id` (and `new`). Sections follow §4.1:
   - basics (name, age, aliases, tagline, tags, visibility);
   - appearance / personality / backstory / goals;
   - limits;
   - secrets (list editor with `reveal_when`);
   - speech (style, catchphrases, examples);
   - addressing / relationships, with a note that empty fields are filled by bond agents in chat;
   - greetings (list, reorder);
   - lorebooks (multi-select);
   - extras (key/value).
   - **Per-field soft warnings** from `warnings` (e.g. a long-field hint near ~300 characters).
   - Save / duplicate / delete (confirm) / export menu (vietrp, CCv2, CCv3 × json/png).
   - Read-only view when `is_owner` is false, with "Thêm vào thư viện của tôi" (duplicate).
3. `/worlds/:id` editor:
   - basics and rules;
   - **location tree editor**: indented tree; add child or sibling; choose level (only levels deeper than the parent); rename; delete with its subtree (confirm); keyboard-accessible; move by drag **and** by "Chuyển lên/xuống/đổi cha" buttons;
   - openings list: each has a title, message, time, start location (picked from the tree), present characters (free slugs for now), tension 0–4 and player_role; reorder;
   - lorebooks.
4. Persona editor (§4.3) and lorebook editor:
   - lorebook: book settings, plus an entries table with inline editing of keys (chips), select_mode, constant/selective toggles, priority, position, enabled and content.
5. Server validation errors map to field-level messages. There is no client-only validation that disagrees with the server; use the generated types.

---

## WP-K · Gallery + import/export UI (frontend-builder) — wave 3

**Owns:**
- `frontend/src/features/gallery/**` (except J0's `api.ts`, `hooks.ts`)
- `frontend/src/pages/GalleryPage.tsx`
- `frontend/src/features/io/**`
- appended `gallery.*` and `io.*` keys in `vi.ts`

**Build:**
1. Gallery (`/`), styled like glow's `HomePage` but with our tokens:
   - tabs Nhân vật / Thực tại; search; tag chips; sort (Mới nhất / Yêu thích);
   - an infinite grid (2 columns on mobile → 7 on wide desktop, KIEN-TRUC/glow guideline);
   - each card shows the image, name, tagline, author, a favorite toggle (optimistic) and a "Thêm vào thư viện" (duplicate) button;
   - clicking opens the detail route;
   - a "Yêu thích của tôi" section at the top when it is not empty.
2. Import dialog, reachable from the IconRail/BottomNav "Tạo mới" page and from the library pages through a shared `ImportButton` exported from `features/io`:
   - drag-and-drop or file picker (.json/.png);
   - upload → result panel: kind, warnings list, a clear "Cần điền tuổi" call-out linking to the editor when `needs_age`, and an "Mở" button.
3. Shared `ExportMenu` component (used by WP-J) in `features/io`. **WP-K must land `ExportMenu` and `ImportButton` with stable props before WP-J uses them.** Props:
   - `ExportMenu {kind, id, formats}`;
   - `ImportButton {onImported?}`.

   If WP-J runs at the same time, WP-J imports them from `@/features/io` and the lead resolves any mismatch.

---

## Lead notes

- If WP-I needs a schema change (e.g. a column for `needs_age` or `favorite_count`), the lead adds Alembic `0002` before or with wave 2. `needs_age` can be derived from `data->>'age' IS NULL`, and `favorite_count` from `favorites`, so no column should be needed.
- DB tests: `backend/.env` holds `VIETRP_TEST_DATABASE_URL` once the owner has run `scripts/dev/create-dev-db.sql`. Load it into the environment before `pytest`.
