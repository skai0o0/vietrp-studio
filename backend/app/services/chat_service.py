"""Chat use cases: create, read, update, delete, messages, bond edits and the prompt preview.

All database work goes through a unit of work (`UnitOfWork`), so the turn pipeline, which must not hold a session
open while it streams, and the plain routes share one way of reaching repositories. Another vault's chat is
reported as 404, never 403.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Final

from fastapi import Depends
from pydantic import ValidationError

from app.agents import bond_drafter, bond_selector
from app.agents.base import AgentContext, LLMGateway
from app.agents.bond_drafter import FIELD_NAMES, BondRecord
from app.core.config import ARCHIVIST_MANUAL_KEEP_RECENT, Settings, get_settings
from app.core.db import get_sessionmaker
from app.core.deps import (
    GatewayFactory,
    GatewayFactoryDep,
    LLMServicesDep,
    SettingsDep,
    make_key_provider,
)
from app.core.errors import AppError
from app.core.sessions import VaultSession
from app.formats.card import VietrpCard
from app.formats.persona import Persona
from app.formats.world import Opening, VietrpWorld
from app.llm.defaults import DEFAULT_MODELS
from app.llm.deps import LLMServices
from app.llm.tokenizer import CorrectionTable
from app.llm.usage import SqlUsageRecorder
from app.pipeline import safety
from app.pipeline.commands import parse_input
from app.pipeline.context_budget import BudgetSettings
from app.pipeline.lorebook import load_books
from app.pipeline.memory import (
    compress_memory,
    refresh_bonds_on_events,
    select_messages_to_compress,
    unsummarized_records,
)
from app.pipeline.prompt_assembler import FALLBACK_USER_NAME, HistoryMessage, assemble
from app.pipeline.single_turn import (
    NARRATOR_SPEAKER,
    USER_SPEAKER,
    ChatContext,
    TurnConfig,
    bond_records,
    build_assembly_input,
    history_messages,
    select_lore,
)
from app.pipeline.world_assembly import WorldCastEntry, assemble_world
from app.pipeline.world_turn import (
    WorldChatContext,
    build_world_assembly_input,
    resolve_preview_speaker,
    select_world_lore,
    slugify_name,
    world_history_messages,
)
from app.prompts.presets import PresetLayers, resolve_preset, substitute_placeholders
from app.repositories.chats_repo import ChatRecord, ChatRepository, SqlChatRepository, UsageRow
from app.repositories.messages_repo import (
    MemorySnapshotRecord,
    MessageRecord,
    MessageRepository,
    NewVariant,
    SqlMessageRepository,
)
from app.repositories.presets_repo import PresetRepository, SqlPresetRepository
from app.schemas.chat import (
    CastMemberSummary,
    ChatCreate,
    ChatOut,
    ChatSettings,
    ChatSummary,
    ChatUpdate,
    ForkRequest,
    GroupWriteMode,
    MessageOut,
    MessageVariantOut,
    PromptLayer,
    PromptPreview,
    UndoResult,
)
from app.schemas.events import DirectorVerdict
from app.schemas.world_state import SceneState, StatePatch, WorldState
from app.services.asset_service import asset_url
from app.services.library_service import Repos, get_repos

# The preset agent whose layers shape the chat prompt (system and nsfw layers of the assembler).
PRESET_AGENT: Final = "writer"
# Default page size of `GET /chats/{id}/messages` and `GET /chats`.
DEFAULT_MESSAGES_LIMIT: Final = 50
MAX_PAGE_LIMIT: Final = 200
DEFAULT_CHATS_LIMIT: Final = 50


@dataclass(slots=True)
class ChatRepos:
    chats: ChatRepository
    messages: MessageRepository
    presets: PresetRepository
    library: Repos
    # Commits the underlying session; read-only users simply do not call it.
    commit: Callable[[], Awaitable[None]]


UnitOfWork = Callable[[], AbstractAsyncContextManager[ChatRepos]]


def sql_unit_of_work() -> UnitOfWork:
    """One short-lived session per `async with`; leaving without `commit()` rolls back."""

    @asynccontextmanager
    async def begin() -> Any:
        async with get_sessionmaker()() as db:
            yield ChatRepos(
                chats=SqlChatRepository(db),
                messages=SqlMessageRepository(db),
                presets=SqlPresetRepository(db),
                library=get_repos(db),
                commit=db.commit,
            )

    return begin


def get_unit_of_work() -> UnitOfWork:
    return sql_unit_of_work()


UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_unit_of_work)]


def chat_not_found() -> AppError:
    return AppError("chat_not_found", "Chat not found", 404)


def parse_chat_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise chat_not_found() from exc


def message_not_found() -> AppError:
    return AppError("message_not_found", "Message not found", 404)


def parse_message_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise message_not_found() from exc


def _settings_of(record: ChatRecord) -> ChatSettings:
    try:
        return ChatSettings.model_validate(record.settings)
    except ValidationError:
        return ChatSettings()


def to_summary(record: ChatRecord) -> ChatSummary:
    if record.mode == "world":
        cast = [
            CastMemberSummary(
                id=str(c["id"]),
                character_id=str(c["character_id"]),
                name=str(c["name"]),
                tagline=str(c.get("tagline", "")),
                avatar_url=asset_url(uuid.UUID(c["avatar_asset_id"])) if c.get("avatar_asset_id") else None,
            )
            for c in record.pack.get("cast", [])
            if isinstance(c, dict)
        ]
        cover = record.pack.get("cover_asset_id")
        first_cast_avatar = next((member.avatar_url for member in cast if member.avatar_url), None)
        avatar_url = asset_url(uuid.UUID(cover)) if cover else first_cast_avatar
        world_data = record.pack.get("world") or {}
        world_id = str(record.world_id or record.pack.get("world_id") or "") or None
        return ChatSummary(
            id=str(record.id),
            mode="world",
            title=record.title,
            world_id=world_id,
            world_name=str(world_data.get("name", "")) or None,
            opening_id=record.opening_id or record.pack.get("opening_id"),
            cast=cast,
            persona_id=str(record.persona_id) if record.persona_id else None,
            avatar_url=avatar_url,
            parent_chat_id=str(record.parent_chat_id) if record.parent_chat_id else None,
            forked_at_seq=record.forked_at_seq,
            messages_count=record.messages_count,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
    card = record.pack.get("card") or {}
    asset = record.pack.get("avatar_asset_id")
    return ChatSummary(
        id=str(record.id),
        mode="single",
        title=record.title,
        character_id=str(record.pack.get("character_id", "")),
        character_name=str(card.get("name", "")),
        persona_id=str(record.persona_id) if record.persona_id else None,
        avatar_url=asset_url(uuid.UUID(asset)) if asset else None,
        parent_chat_id=str(record.parent_chat_id) if record.parent_chat_id else None,
        forked_at_seq=record.forked_at_seq,
        messages_count=record.messages_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _ids_of(data: Any) -> list[str]:
    raw = data.get("lorebook_ids") if isinstance(data, dict) else None
    return [str(i) for i in raw] if isinstance(raw, list) else []


def pack_lorebook_ids(record: ChatRecord) -> list[str]:
    """Lorebooks linked to the card/world snapshot taken when the chat was created (cast order, no duplicates)."""
    if record.mode == "world":
        ids = _ids_of(record.pack.get("world"))
        for member in record.pack.get("cast", []):
            if isinstance(member, dict):
                ids += _ids_of(member.get("card"))
    else:
        ids = _ids_of(record.pack.get("card"))
    return list(dict.fromkeys(ids))


def chat_lorebook_ids(record: ChatRecord) -> list[uuid.UUID]:
    """The books a turn may use: the chat's own list when set, else the snapshot's links."""
    own = _settings_of(record).lorebook.book_ids
    if own is not None:
        return list(dict.fromkeys(own))
    out: list[uuid.UUID] = []
    for raw in pack_lorebook_ids(record):
        try:
            out.append(uuid.UUID(raw))
        except ValueError:
            continue
    return out


def to_chat_out(record: ChatRecord) -> ChatOut:
    return ChatOut(
        **to_summary(record).model_dump(),
        state=record.state,
        settings=_settings_of(record),
        default_lorebook_ids=pack_lorebook_ids(record),
    )


def to_message_out(record: MessageRecord, *, include_drafts: bool) -> MessageOut:
    variants: list[MessageVariantOut] = []
    for v in record.variants:
        verdict: DirectorVerdict | None = None
        if v.director is not None:
            try:
                verdict = DirectorVerdict.model_validate(v.director)
            except ValidationError:
                verdict = None
        variants.append(
            MessageVariantOut(
                idx=v.idx,
                content=v.content,
                stopped=v.stopped,
                director=verdict,
                created_at=v.created_at,
                draft=v.draft if include_drafts else None,
            )
        )
    return MessageOut(
        id=str(record.id),
        seq=record.seq,
        speaker=record.speaker,
        active_variant=record.active_variant,
        variants=variants,
        meta=record.meta,
        created_at=record.created_at,
    )


async def _load_persona(r: ChatRepos, vault_id: uuid.UUID, persona_id: uuid.UUID | None) -> Persona | None:
    if persona_id is None:
        return None
    record = await r.library.personas.get(vault_id, persona_id)
    if record is None:
        return None
    try:
        return Persona.model_validate(record.data)
    except ValidationError:
        return None


async def _load_preset(r: ChatRepos, vault_id: uuid.UUID) -> PresetLayers:
    preset_rows = await r.presets.list_presets(vault_id, agent=PRESET_AGENT)
    return resolve_preset(preset_rows[0].layers) if preset_rows else resolve_preset(None)


async def load_context(
    r: ChatRepos, vault_id: uuid.UUID, chat_id: uuid.UUID, cfg: TurnConfig
) -> ChatContext | WorldChatContext:
    """Read everything a turn or a preview needs. Lorebook visibility is re-checked here, never trusted from links."""
    chat = await r.chats.get(vault_id, chat_id)
    if chat is None:
        raise chat_not_found()
    persona = await _load_persona(r, vault_id, chat.persona_id)
    history = await r.messages.page(vault_id, chat_id, before=None, limit=cfg.history_limit)
    preset = await _load_preset(r, vault_id)
    if chat.mode == "world":
        world = VietrpWorld.model_validate(chat.pack["world"])
        opening = Opening.model_validate(chat.pack["opening"])
        cast = [
            WorldCastEntry(id=c["id"], card=VietrpCard.model_validate(c["card"])) for c in chat.pack.get("cast", [])
        ]
        books = await load_books(r.library.lorebooks, vault_id, chat_lorebook_ids(chat))
        return WorldChatContext(
            vault_id=vault_id,
            chat_id=chat_id,
            world=world,
            opening=opening,
            cast=cast,
            persona=persona,
            settings=_settings_of(chat),
            state=chat.state,
            books=books,
            history=history,
            preset=preset,
        )
    card = VietrpCard.model_validate(chat.pack["card"])
    books = await load_books(r.library.lorebooks, vault_id, chat_lorebook_ids(chat))
    return ChatContext(
        vault_id=vault_id,
        chat_id=chat_id,
        character_id=str(chat.pack["character_id"]),
        card=card,
        persona=persona,
        settings=_settings_of(chat),
        state=chat.state,
        books=books,
        history=history,
        preset=preset,
    )


def _assign_cast_slugs(cards: Sequence[VietrpCard], opening_present_ids: Sequence[str]) -> list[str]:
    """Derive unique `^[a-z0-9_]{1,40}$` slugs, preferring matching unmatched ids from `opening.present_ids`."""
    full_slugs = [slugify_name(card.name) for card in cards]
    last_slugs = [
        slugify_name(card.name.split()[-1]) if card.name.split() else full_slugs[i] for i, card in enumerate(cards)
    ]
    alias_slugs = [[slugify_name(a) for a in card.aliases if a.strip()] for card in cards]

    unmatched = list(dict.fromkeys(opening_present_ids))
    assigned: list[str | None] = [None] * len(cards)
    used: set[str] = set()

    for idx, full in enumerate(full_slugs):
        if full in unmatched and full not in used:
            assigned[idx] = full
            used.add(full)
            unmatched.remove(full)

    for idx in range(len(cards)):
        if assigned[idx] is not None:
            continue
        candidates = [last_slugs[idx], *alias_slugs[idx]]
        match = next((c for c in candidates if c in unmatched and c not in used), None)
        if match is not None:
            assigned[idx] = match
            used.add(match)
            unmatched.remove(match)

    for idx, full in enumerate(full_slugs):
        if assigned[idx] is not None:
            continue
        slug = full
        suffix_num = 2
        while slug in used:
            suffix = f"_{suffix_num}"
            slug = f"{full[: 40 - len(suffix)].rstrip('_') or 'c'}{suffix}"
            suffix_num += 1
        assigned[idx] = slug
        used.add(slug)

    return [slug for slug in assigned if slug is not None]


def _merge_bonds(state: dict[str, Any], bonds: dict[str, Any]) -> None:
    existing = bond_records(state)
    for pair_id, raw in bonds.items():
        try:
            edited = BondRecord.model_validate(raw)
        except ValidationError as exc:
            raise AppError("validation_error", f"bonds.{pair_id} is invalid", 422) from exc
        old = existing.get(pair_id)
        old_fields = old.fields.model_dump() if old is not None else {}
        new_fields = edited.fields.model_dump()
        touched = {n for n in FIELD_NAMES if old is None or new_fields[n] != old_fields[n]}
        manual = {*(old.manual if old else []), *edited.manual, *touched}
        existing[pair_id] = BondRecord(
            pair_id=pair_id,
            label=edited.label or (old.label if old else pair_id),
            fields=edited.fields,
            pinned=old.pinned if old is not None else edited.pinned,
            manual=[n for n in FIELD_NAMES if n in manual],
            changes=old.changes if old is not None else [],
        )
    state["bonds"] = {key: record.model_dump(mode="json") for key, record in existing.items()}


KeyCheck = Callable[[VaultSession], Awaitable[None]]


class ChatService:
    def __init__(
        self,
        uow: UnitOfWork,
        corrections: CorrectionTable | None = None,
        *,
        gateway_factory: GatewayFactory | None = None,
        services: LLMServices | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._uow = uow
        self._corrections = corrections or (services.corrections if services is not None else CorrectionTable())
        self._gateway_factory = gateway_factory
        self._services = services
        self._settings = settings

    async def create(self, vault_id: uuid.UUID, body: ChatCreate) -> ChatOut:
        if body.mode == "world":
            return await self._create_world(vault_id, body)
        return await self._create_single(vault_id, body)

    async def _create_single(self, vault_id: uuid.UUID, body: ChatCreate) -> ChatOut:
        assert body.character_id is not None
        try:
            character_id = uuid.UUID(body.character_id)
            persona_id = uuid.UUID(body.persona_id) if body.persona_id else None
        except ValueError as exc:
            raise AppError("not_found", "Character or persona not found", 404) from exc
        async with self._uow() as r:
            row = await r.library.characters.get_visible(vault_id, character_id)
            if row is None:
                raise AppError("not_found", "Character not found", 404)
            card = VietrpCard.model_validate(row.data)
            safety.assert_cast_usable([safety.cast_from_card(card)])
            persona: Persona | None = None
            if persona_id is not None:
                persona_row = await r.library.personas.get(vault_id, persona_id)
                if persona_row is None:
                    raise AppError("not_found", "Persona not found", 404)
                persona = Persona.model_validate(persona_row.data)
            greeting: str | None = None
            if card.greetings:
                if body.greeting_index >= len(card.greetings):
                    raise AppError("greeting_index_invalid", "Greeting index is out of range", 422)
                greeting = card.greetings[body.greeting_index]
            settings = body.settings or ChatSettings()
            state: dict[str, Any] = {"bonds": {}, "summary": "", "summary_upto": 0, "events": []}
            pack = {
                "character_id": str(character_id),
                "card": card.model_dump(mode="json"),
                "avatar_asset_id": str(row.asset_id) if row.asset_id else None,
            }
            chat = await r.chats.create(
                vault_id,
                mode="single",
                cast_ids=[character_id],
                persona_id=persona_id,
                pack=pack,
                state=state,
                settings=settings.model_dump(mode="json"),
                title=body.title or card.name,
            )
            if greeting is not None:
                user_name = persona.name if persona is not None else FALLBACK_USER_NAME
                text = substitute_placeholders(greeting, char=card.name, user=user_name)
                await r.messages.add(
                    vault_id,
                    chat.id,
                    message_id=uuid.uuid4(),
                    seq=0,
                    speaker=str(character_id),
                    meta={},
                    state_before=copy.deepcopy(state),
                    variants=[NewVariant(content=text)],
                )
            await r.commit()
            created = await r.chats.get(vault_id, chat.id)
        assert created is not None
        return to_chat_out(created)

    async def _create_world(self, vault_id: uuid.UUID, body: ChatCreate) -> ChatOut:
        if not body.world_id or not body.cast_ids:
            raise AppError("validation_error", "world_id and cast_ids are required when mode is 'world'", 422)
        try:
            world_uuid = uuid.UUID(body.world_id)
            cast_uuids = list(dict.fromkeys(uuid.UUID(cid) for cid in body.cast_ids))
            persona_id = uuid.UUID(body.persona_id) if body.persona_id else None
        except ValueError as exc:
            raise AppError("not_found", "World, character, or persona not found", 404) from exc

        async with self._uow() as r:
            world_row = await r.library.worlds.get_visible(vault_id, world_uuid)
            if world_row is None:
                raise AppError("not_found", "World not found", 404)
            world = VietrpWorld.model_validate(world_row.data)
            if body.opening_id:
                opening = next((o for o in world.openings if o.id == body.opening_id), None)
                if opening is None:
                    raise AppError("opening_not_found", "Opening not found in world", 422)
            elif world.openings:
                raise AppError("validation_error", "opening_id is required when world has openings", 422)
            else:
                opening = Opening(
                    id="default",
                    title="",
                    location_id=world.locations[0].id if world.locations else "",
                    time="",
                    tension=1,
                    present_ids=[],
                    player_role="",
                    message="",
                )

            char_rows = []
            cards: list[VietrpCard] = []
            for cid in cast_uuids:
                char_row = await r.library.characters.get_visible(vault_id, cid)
                if char_row is None:
                    raise AppError("not_found", "Character not found", 404)
                char_rows.append(char_row)
                cards.append(VietrpCard.model_validate(char_row.data))
            safety.assert_cast_usable([safety.cast_from_card(card) for card in cards])

            persona: Persona | None = None
            if persona_id is not None:
                persona_row = await r.library.personas.get(vault_id, persona_id)
                if persona_row is None:
                    raise AppError("not_found", "Persona not found", 404)
                persona = Persona.model_validate(persona_row.data)

            slugs = _assign_cast_slugs(cards, opening.present_ids)
            cast_entries = [WorldCastEntry(id=slug, card=card) for slug, card in zip(slugs, cards, strict=True)]
            pack_cast = [
                {
                    "id": slug,
                    "character_id": str(cid),
                    "name": card.name,
                    "tagline": card.tagline,
                    "avatar_asset_id": str(row.asset_id) if row.asset_id else None,
                    "card": card.model_dump(mode="json"),
                }
                for slug, cid, card, row in zip(slugs, cast_uuids, cards, char_rows, strict=True)
            ]
            pack = {
                "world_id": str(world_uuid),
                "world": world.model_dump(mode="json"),
                "opening_id": opening.id,
                "opening": opening.model_dump(mode="json"),
                "cover_asset_id": str(world_row.asset_id) if world_row.asset_id else None,
                "cast": pack_cast,
            }

            slug_set = set(slugs)
            if opening.present_ids:
                present_ids = [s for s in dict.fromkeys(opening.present_ids) if s in slug_set]
            else:
                present_ids = list(slugs)

            pairs = bond_drafter.world_pairs(cast_entries, persona, FALLBACK_USER_NAME)
            pinned_records = bond_selector.apply_selection({}, pairs, {}, seq=0)
            initial_bonds = {key: record.model_dump(mode="json") for key, record in pinned_records.items()}

            settings = body.settings or ChatSettings()
            state = WorldState(
                location_id=opening.location_id,
                time=opening.time,
                tension=opening.tension,
                present_ids=present_ids,
                awaiting_reply=[],
                silence={cid: 0 for cid in present_ids},
                scene=SceneState(),
                bonds=initial_bonds,
                npcs=[],
                manual=[],
            ).model_dump(mode="json")
            default_title = f"{world.name} — {opening.title}" if opening.title else world.name
            chat = await r.chats.create(
                vault_id,
                mode="world",
                world_id=world_uuid,
                opening_id=opening.id,
                cast_ids=cast_uuids,
                persona_id=persona_id,
                pack=pack,
                state=state,
                settings=settings.model_dump(mode="json"),
                title=body.title or default_title,
            )
            if opening.message.strip():
                user_name = persona.name if persona is not None else FALLBACK_USER_NAME
                char_label = (
                    ", ".join(e.card.name for e in cast_entries if e.id in present_ids)
                    or ", ".join(e.card.name for e in cast_entries)
                    or world.name
                )
                text = substitute_placeholders(opening.message, char=char_label, user=user_name)
                await r.messages.add(
                    vault_id,
                    chat.id,
                    message_id=uuid.uuid4(),
                    seq=0,
                    speaker=NARRATOR_SPEAKER,
                    meta={},
                    state_before=state,
                    variants=[NewVariant(content=text)],
                )
            await r.commit()
            created = await r.chats.get(vault_id, chat.id)
        assert created is not None
        return to_chat_out(created)

    async def list_chats(self, vault_id: uuid.UUID, *, limit: int, offset: int) -> list[ChatSummary]:
        async with self._uow() as r:
            return [to_summary(c) for c in await r.chats.list_chats(vault_id, limit=limit, offset=offset)]

    async def get(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> ChatOut:
        async with self._uow() as r:
            chat = await r.chats.get(vault_id, chat_id)
        if chat is None:
            raise chat_not_found()
        return to_chat_out(chat)

    async def update(self, vault_id: uuid.UUID, chat_id: uuid.UUID, body: ChatUpdate) -> ChatOut:
        fields: dict[str, Any] = {}
        async with self._uow() as r:
            chat = await r.chats.get(vault_id, chat_id)
            if chat is None:
                raise chat_not_found()
            if body.title is not None:
                fields["title"] = body.title
            if body.settings is not None:
                fields["settings"] = body.settings.model_dump(mode="json")
            if "persona_id" in body.model_fields_set:
                if body.persona_id is None:
                    fields["persona_id"] = None
                    new_user_name = FALLBACK_USER_NAME
                else:
                    try:
                        persona_id = uuid.UUID(body.persona_id)
                    except ValueError as exc:
                        raise AppError("not_found", "Persona not found", 404) from exc
                    persona_row = await r.library.personas.get(vault_id, persona_id)
                    if persona_row is None:
                        raise AppError("not_found", "Persona not found", 404)
                    fields["persona_id"] = persona_id
                    new_user_name = Persona.model_validate(persona_row.data).name
                raw_bonds = chat.state.get("bonds") if isinstance(chat.state, dict) else None
                if isinstance(raw_bonds, dict) and any(str(pid).endswith(":user") for pid in raw_bonds):
                    next_state = copy.deepcopy(chat.state)
                    next_bonds = dict(next_state.get("bonds") or {})
                    for pid, rec in next_bonds.items():
                        if not str(pid).endswith(":user") or not isinstance(rec, dict):
                            continue
                        old_label = str(rec.get("label") or "")
                        char_prefix = old_label.partition(" ↔ ")[0].strip() if " ↔ " in old_label else ""
                        if char_prefix:
                            next_bonds[pid] = {**rec, "label": f"{char_prefix} ↔ {new_user_name}"}
                    next_state["bonds"] = next_bonds
                    fields["state"] = next_state
            updated = await r.chats.update(vault_id, chat_id, fields)
            assert updated is not None
            await r.commit()
        return to_chat_out(updated)

    async def remove(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> None:
        async with self._uow() as r:
            if not await r.chats.delete(vault_id, chat_id):
                raise chat_not_found()
            await r.commit()

    async def messages(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID, *, before: int | None, limit: int, include_drafts: bool
    ) -> list[MessageOut]:
        async with self._uow() as r:
            if await r.chats.get(vault_id, chat_id) is None:
                raise chat_not_found()
            rows = await r.messages.page(vault_id, chat_id, before=before, limit=limit)
        return [to_message_out(row, include_drafts=include_drafts) for row in rows]

    async def usage_rows(self, vault_id: uuid.UUID, chat_id: uuid.UUID | None, *, limit: int) -> list[UsageRow]:
        async with self._uow() as r:
            if chat_id is not None and await r.chats.get(vault_id, chat_id) is None:
                raise chat_not_found()
            return await r.chats.usage_rows(vault_id, chat_id, limit=limit)

    async def patch_bonds(self, vault_id: uuid.UUID, chat_id: uuid.UUID, bonds: dict[str, Any]) -> ChatOut:
        """Hand edit of `state.bonds`. Edited fields join `manual`, so agents never overwrite them again."""
        return await self.patch_state(vault_id, chat_id, StatePatch(bonds=bonds))

    async def patch_state(self, vault_id: uuid.UUID, chat_id: uuid.UUID, body: StatePatch) -> ChatOut:
        """Apply Live State Editor edits to `chat.state` and record touched keys in `manual`."""
        async with self._uow() as r:
            chat = await r.chats.get(vault_id, chat_id)
            if chat is None:
                raise chat_not_found()
            if chat.mode == "single":
                world_only = ("location_id", "time", "tension", "present_ids", "awaiting_reply", "silence", "scene")
                if any(getattr(body, name) is not None for name in world_only):
                    raise AppError("validation_error", "World state fields are not valid for single chats", 422)
                state = dict(chat.state)
                if body.bonds is not None:
                    _merge_bonds(state, body.bonds)
                for key in ("npcs", "summary", "events"):
                    val = getattr(body, key)
                    if val is not None:
                        state[key] = val
            else:
                world_state = WorldState.model_validate(chat.state)
                state = world_state.model_dump(mode="json")
                manual = list(world_state.manual)
                world = VietrpWorld.model_validate(chat.pack["world"])
                cast_ids = {str(c["id"]) for c in chat.pack.get("cast", []) if isinstance(c, dict)}
                valid_locations = {loc.id for loc in world.locations}

                if body.bonds is not None:
                    _merge_bonds(state, body.bonds)
                    if "bonds" not in manual:
                        manual.append("bonds")

                editable = (
                    "location_id",
                    "time",
                    "tension",
                    "present_ids",
                    "awaiting_reply",
                    "silence",
                    "scene",
                    "npcs",
                    "summary",
                    "events",
                )
                for field_name in editable:
                    val = getattr(body, field_name)
                    if val is None:
                        continue
                    if field_name == "location_id":
                        if valid_locations and val not in valid_locations:
                            raise AppError("validation_error", "Unknown location_id", 422)
                        state["location_id"] = val
                    elif field_name in ("present_ids", "awaiting_reply"):
                        unknown = [cid for cid in val if cid not in cast_ids]
                        if unknown:
                            raise AppError("validation_error", f"Unknown cast id in {field_name}", 422)
                        state[field_name] = list(dict.fromkeys(val))
                    elif field_name == "silence":
                        unknown = [cid for cid in val if cid not in cast_ids]
                        if unknown:
                            raise AppError("validation_error", "Unknown cast id in silence", 422)
                        if any(turns < 0 for turns in val.values()):
                            raise AppError("validation_error", "Silence counts must be non-negative", 422)
                        state["silence"] = dict(val)
                    elif field_name == "scene":
                        state["scene"] = val.model_dump(mode="json")
                    else:
                        state[field_name] = val
                    if field_name not in manual:
                        manual.append(field_name)

                state["manual"] = manual
                state = WorldState.model_validate(state).model_dump(mode="json")

            updated = await r.chats.update(vault_id, chat_id, {"state": state})
            assert updated is not None
            await r.commit()
        return to_chat_out(updated)

    async def prompt_preview(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID, text: str, *, speaker: str | None = None
    ) -> PromptPreview:
        """The prompt the next turn would start from (no LLM call, so no Orchestrator: keyword lore, default fields)."""
        cfg = TurnConfig()
        async with self._uow() as r:
            ctx = await load_context(r, vault_id, chat_id, cfg)
        parsed = parse_input(text)
        if isinstance(ctx, WorldChatContext):
            world_state = WorldState.model_validate(ctx.state)
            cast_by_id = {entry.id: entry for entry in ctx.cast}
            messages = world_history_messages(unsummarized_records(ctx.history, ctx.state), cast_by_id)
            if parsed.message.strip():
                messages.append(HistoryMessage("user", parsed.message))
            selection = select_world_lore(ctx, messages)
            speaker_id = resolve_preview_speaker(ctx, world_state, speaker)
            write_mode: GroupWriteMode = (
                "single_call"
                if (speaker_id == "group" or ctx.settings.group.write_mode == "single_call")
                else "per_character"
            )
            assembled = assemble_world(
                build_world_assembly_input(
                    ctx,
                    world_state,
                    messages,
                    speaker_id=speaker_id,
                    corrections=self._corrections,
                    lore=selection,
                    write_mode=write_mode,
                    command=parsed if parsed.kind == "cmd" else None,
                )
            )
        else:
            messages = history_messages(unsummarized_records(ctx.history, ctx.state))
            if parsed.message.strip():
                messages.append(HistoryMessage("user", parsed.message))
            selection = select_lore(ctx, messages)
            assembled = assemble(
                build_assembly_input(
                    ctx,
                    messages,
                    corrections=self._corrections,
                    lore=selection,
                    command=parsed if parsed.kind == "cmd" else None,
                )
            )
        budget = BudgetSettings.from_memory(ctx.settings.memory.model_dump())
        return PromptPreview(
            layers=[PromptLayer(name=la.name, tokens=la.tokens, text=la.text) for la in assembled.layers],
            total_tokens=assembled.total_tokens,
            budget=budget.context_length,
        )

    async def summarize(
        self,
        vault_session: VaultSession,
        chat_id: uuid.UUID,
        *,
        key_check: KeyCheck | None = None,
    ) -> ChatOut:
        """Manually compress older unsummarized messages via Archivist and save a `MemorySnapshot`."""
        vault_id = vault_session.vault_id
        async with self._uow() as r:
            ctx = await load_context(r, vault_id, chat_id, TurnConfig())

        state = copy.deepcopy(ctx.state)
        if not isinstance(ctx, WorldChatContext):
            state.setdefault("bonds", {})
            state.setdefault("summary", "")
            state.setdefault("summary_upto", 0)
            state.setdefault("events", [])

        unsummarized = unsummarized_records(ctx.history, state)
        if not unsummarized:
            raise AppError("nothing_to_summarize", "No unsummarized messages to summarize", 422)

        if key_check is not None:
            await key_check(vault_session)

        if self._gateway_factory is not None:
            gateway = self._gateway_factory(vault_session, chat_id)
        elif self._services is not None:
            gateway = LLMGateway(
                self._services,
                vault_id=vault_id,
                chat_id=chat_id,
                api_key=make_key_provider(vault_session),
                recorder=SqlUsageRecorder(get_sessionmaker()),
            )
        else:
            raise AppError("openrouter_key_missing", "No OpenRouter API key is stored in this vault", 400)

        # Resolve the key before entering `run_non_critical`, which would swallow an `AppError`.
        await gateway._api_key()

        keep_recent = ARCHIVIST_MANUAL_KEEP_RECENT if len(unsummarized) > ARCHIVIST_MANUAL_KEEP_RECENT else 0
        to_compress = select_messages_to_compress(ctx.history, state, keep_recent=keep_recent)
        if not to_compress:
            raise AppError("nothing_to_summarize", "No unsummarized messages to summarize", 422)

        user_name = ctx.persona.name if ctx.persona is not None else FALLBACK_USER_NAME
        if isinstance(ctx, WorldChatContext):
            speaker_names = {entry.id: entry.card.name for entry in ctx.cast}
            pairs = bond_drafter.world_pairs(ctx.cast, ctx.persona, FALLBACK_USER_NAME)
        else:
            speaker_names = {ctx.character_id: ctx.card.name}
            pairs = [bond_drafter.user_pair(ctx.card, ctx.character_id, ctx.persona, FALLBACK_USER_NAME)]

        settings_obj = self._settings or get_settings()
        agent_ctx = AgentContext(vault_id=vault_id, chat_id=chat_id, llm=gateway, settings=settings_obj)
        arch_model = ctx.settings.models.archivist or DEFAULT_MODELS["archivist"]

        async def _save_snapshot(
            *, upto_seq: int, summary: str, events: Sequence[dict[str, Any]]
        ) -> MemorySnapshotRecord:
            async with self._uow() as r:
                snap = await r.messages.add_snapshot(
                    vault_id, chat_id, upto_seq=upto_seq, summary=summary, events=events
                )
                await r.commit()
                return snap

        async def _set_state(new_state: dict[str, Any]) -> None:
            payload = (
                WorldState.model_validate(new_state).model_dump(mode="json")
                if isinstance(ctx, WorldChatContext)
                else new_state
            )
            async with self._uow() as r:
                await r.chats.update(vault_id, chat_id, {"state": payload})
                await r.commit()

        arch_out, _notices, _usages = await compress_memory(
            agent_ctx,
            arch_model,
            state,
            to_compress,
            user_name=user_name,
            speaker_names=speaker_names,
            save_snapshot=_save_snapshot,
            set_state=_set_state,
        )
        if arch_out is None:
            raise AppError("archivist_failed", "Archivist failed to summarize chat", 502)

        if arch_out.events_added > 0 and pairs:
            latest_seq = ctx.history[-1].seq if ctx.history else 0
            await refresh_bonds_on_events(
                agent_ctx,
                ctx.settings,
                pairs,
                state,
                seq=latest_seq,
                set_state=_set_state,
            )

        async with self._uow() as r:
            updated = await r.chats.get(vault_id, chat_id)
        if updated is None:
            raise chat_not_found()
        return to_chat_out(updated)

    @staticmethod
    async def _all_messages(r: ChatRepos, vault_id: uuid.UUID, chat_id: uuid.UUID) -> list[MessageRecord]:
        chunks: list[list[MessageRecord]] = []
        before: int | None = None
        while True:
            batch = await r.messages.page(vault_id, chat_id, before=before, limit=MAX_PAGE_LIMIT)
            if not batch:
                break
            chunks.append(batch)
            if len(batch) < MAX_PAGE_LIMIT:
                break
            before = batch[0].seq
        out: list[MessageRecord] = []
        for chunk in reversed(chunks):
            out.extend(chunk)
        return out

    @staticmethod
    async def _get_scoped_message(
        r: ChatRepos, vault_id: uuid.UUID, message_id: uuid.UUID, chat_id: uuid.UUID | None
    ) -> tuple[ChatRecord, MessageRecord]:
        chat: ChatRecord | None = None
        if chat_id is not None:
            chat = await r.chats.get(vault_id, chat_id)
            if chat is None:
                raise chat_not_found()
        msg = await r.messages.get_message(vault_id, message_id)
        if msg is None or (chat_id is not None and msg.chat_id != chat_id):
            raise message_not_found()
        if chat is None:
            chat = await r.chats.get(vault_id, msg.chat_id)
            if chat is None:
                raise chat_not_found()
        return chat, msg

    @staticmethod
    async def _rewind_from_message(
        r: ChatRepos, vault_id: uuid.UUID, chat: ChatRecord, target: MessageRecord
    ) -> UndoResult:
        removed = await r.messages.delete_from_seq(vault_id, chat.id, target.seq)
        await r.messages.delete_snapshots_after(vault_id, chat.id, target.seq)
        fields: dict[str, Any] = (
            {"state": copy.deepcopy(target.state_before)} if target.state_before is not None else {}
        )
        updated_chat = await r.chats.update(vault_id, chat.id, fields)
        if updated_chat is None:
            raise chat_not_found()
        await r.commit()
        return UndoResult(removed_count=removed, chat=to_chat_out(updated_chat))

    async def set_active_variant(
        self,
        vault_id: uuid.UUID,
        message_id: uuid.UUID,
        variant_idx: int,
        *,
        chat_id: uuid.UUID | None = None,
    ) -> MessageOut:
        async with self._uow() as r:
            chat, msg = await self._get_scoped_message(r, vault_id, message_id, chat_id)
            if not any(v.idx == variant_idx for v in msg.variants):
                raise AppError("variant_not_found", "Variant not found", 422)
            updated = await r.messages.set_active_variant(vault_id, message_id, variant_idx)
            if updated is None:
                raise message_not_found()
            await r.chats.update(vault_id, chat.id, {})
            await r.commit()
        return to_message_out(updated, include_drafts=False)

    async def edit_message(
        self,
        vault_id: uuid.UUID,
        message_id: uuid.UUID,
        content: str,
        *,
        chat_id: uuid.UUID | None = None,
    ) -> MessageOut:
        if not content.strip():
            raise AppError("validation_error", "Message content cannot be blank", 422)
        async with self._uow() as r:
            chat, _msg = await self._get_scoped_message(r, vault_id, message_id, chat_id)
            updated = await r.messages.update_variant_content(vault_id, message_id, content)
            if updated is None:
                raise message_not_found()
            await r.chats.update(vault_id, chat.id, {})
            await r.commit()
        return to_message_out(updated, include_drafts=False)

    async def delete_message(
        self,
        vault_id: uuid.UUID,
        message_id: uuid.UUID,
        *,
        chat_id: uuid.UUID | None = None,
    ) -> UndoResult:
        async with self._uow() as r:
            chat, target = await self._get_scoped_message(r, vault_id, message_id, chat_id)
            if target.seq == 0:
                raise AppError("cannot_delete_greeting", "Cannot delete the opening greeting message", 422)
            return await self._rewind_from_message(r, vault_id, chat, target)

    async def undo(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> UndoResult:
        async with self._uow() as r:
            chat = await r.chats.get(vault_id, chat_id)
            if chat is None:
                raise chat_not_found()
            msgs = await r.messages.page(vault_id, chat_id, before=None, limit=MAX_PAGE_LIMIT)
            candidates = [m for m in msgs if m.seq >= 1]
            if not candidates:
                raise AppError("nothing_to_undo", "Nothing to undo in this chat", 422)
            last = candidates[-1]
            if last.speaker != USER_SPEAKER and last.meta.get("is_continue"):
                turn_id = last.meta.get("turn_id")
                target = last
                if isinstance(turn_id, str) and turn_id:
                    for item in reversed(candidates[:-1]):
                        if item.speaker != USER_SPEAKER and item.meta.get("turn_id") == turn_id:
                            target = item
                        else:
                            break
            else:
                last_user = next((m for m in reversed(candidates) if m.speaker == USER_SPEAKER), None)
                target = last_user if last_user is not None else last
            return await self._rewind_from_message(r, vault_id, chat, target)

    async def fork(self, vault_id: uuid.UUID, chat_id: uuid.UUID, body: ForkRequest | None = None) -> ChatOut:
        async with self._uow() as r:
            source_chat = await r.chats.get(vault_id, chat_id)
            if source_chat is None:
                raise chat_not_found()
            msgs = await self._all_messages(r, vault_id, chat_id)

            if body is not None and body.message_id is not None:
                msg_uuid = parse_message_id(body.message_id)
                msg = await r.messages.get_message(vault_id, msg_uuid)
                if msg is None or msg.chat_id != chat_id:
                    raise message_not_found()
                if body.upto_seq is not None and body.upto_seq != msg.seq:
                    raise AppError("validation_error", "message_id and upto_seq do not match", 422)
                resolved_seq = msg.seq
            elif body is not None and body.upto_seq is not None:
                if not msgs:
                    if body.upto_seq != 0:
                        raise AppError("validation_error", "upto_seq is out of range", 422)
                elif body.upto_seq > msgs[-1].seq:
                    raise AppError("validation_error", "upto_seq is out of range", 422)
                resolved_seq = body.upto_seq
            else:
                resolved_seq = msgs[-1].seq if msgs else 0

            next_msg = next((m for m in msgs if m.seq > resolved_seq), None)
            if next_msg is not None and next_msg.state_before is not None:
                initial_state = copy.deepcopy(next_msg.state_before)
            else:
                initial_state = copy.deepcopy(source_chat.state)

            raw_title = body.title.strip() if (body is not None and body.title is not None) else ""
            title = raw_title if raw_title else f"{source_chat.title[:190]} (nhánh)"
            forked = await r.messages.fork_chat(
                vault_id,
                source_chat,
                upto_seq=resolved_seq,
                initial_state=initial_state,
                title=title,
            )
            await r.commit()
        return to_chat_out(forked)


def get_chat_service(
    uow: UnitOfWorkDep,
    services: LLMServicesDep,
    gateway_factory: GatewayFactoryDep,
    settings: SettingsDep,
) -> ChatService:
    return ChatService(
        uow,
        services.corrections,
        gateway_factory=gateway_factory,
        services=services,
        settings=settings,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
