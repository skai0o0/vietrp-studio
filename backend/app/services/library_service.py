"""Library use cases: characters, worlds, personas and lorebooks of one vault.

Every method takes the acting `vault_id`; another vault's private item is reported as 404, never 403.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import Depends
from pydantic import ValidationError

from app.agents import card_judge
from app.agents.base import AgentContext
from app.core.config import Settings
from app.core.deps import GatewayFactory, SessionDep
from app.core.errors import AppError
from app.core.sessions import VaultSession
from app.formats.common import FormatWarning, Visibility
from app.formats.validate import (
    validate_card,
    validate_lorebook,
    validate_persona,
    validate_world,
)
from app.llm.client import LLMError
from app.pipeline.safety import public_nsfw_blocked
from app.repositories.assets_repo import AssetRepository, SqlAssetRepository
from app.repositories.characters_repo import (
    ContentRecord,
    ContentRepository,
    Cursor,
    InvalidCursorError,
    SqlCharacterRepository,
    decode_cursor,
    encode_cursor,
)
from app.repositories.favorites_repo import FavoriteRepository, SqlFavoriteRepository
from app.repositories.lorebooks_repo import LorebookRecord, LorebookRepository, SqlLorebookRepository
from app.repositories.personas_repo import PersonaRecord, PersonaRepository, SqlPersonaRepository
from app.repositories.worlds_repo import SqlWorldRepository
from app.schemas.library import (
    CharacterOut,
    CharacterSummary,
    LorebookOut,
    LorebookSummary,
    PersonaOut,
    TargetType,
    WorldOut,
    WorldSummary,
)
from app.services.asset_service import asset_url, checked_image

# World "tagline" is derived from the start of its rules text (worlds have no tagline field).
WORLD_TAGLINE_MAX = 140


@dataclass(slots=True)
class Repos:
    """All repositories of one request, sharing one database session."""

    characters: ContentRepository
    worlds: ContentRepository
    personas: PersonaRepository
    lorebooks: LorebookRepository
    favorites: FavoriteRepository
    assets: AssetRepository

    async def commit(self) -> None:
        await self.characters.commit()


def get_repos(db: SessionDep) -> Repos:
    return Repos(
        characters=SqlCharacterRepository(db),
        worlds=SqlWorldRepository(db),
        personas=SqlPersonaRepository(db),
        lorebooks=SqlLorebookRepository(db),
        favorites=SqlFavoriteRepository(db),
        assets=SqlAssetRepository(db),
    )


ReposDep = Annotated[Repos, Depends(get_repos)]


# --- shared helpers ---


def not_found(what: str = "Item") -> AppError:
    return AppError("not_found", f"{what} not found", 404)


def validation_failed(exc: Exception) -> AppError:
    """422 with locations and messages only: never echo the submitted values."""
    if isinstance(exc, ValidationError):
        detail = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors())
    else:
        detail = str(exc)
    return AppError("validation_error", f"data is invalid: {detail}", 422)


def parse_cursor(value: str | None) -> Cursor | None:
    if value is None:
        return None
    try:
        return decode_cursor(value)
    except InvalidCursorError as exc:
        raise AppError("invalid_cursor", "Cursor is invalid", 422) from exc


def paginate[T](rows: Sequence[T], limit: int, make_cursor: Callable[[T], Cursor]) -> tuple[list[T], str | None]:
    """Repositories return `limit + 1` rows; the extra one only signals that another page exists."""
    if len(rows) > limit:
        kept = list(rows[:limit])
        return kept, encode_cursor(make_cursor(kept[-1]))
    return list(rows), None


def _uuid_list(values: Any) -> list[uuid.UUID]:
    return [uuid.UUID(str(v)) for v in values or []]


# --- character / world kinds ---


@dataclass(frozen=True, slots=True)
class Validated:
    data: dict[str, Any]
    warnings: list[FormatWarning]


@dataclass(frozen=True, slots=True)
class ContentKind:
    """What differs between characters and worlds."""

    target_type: TargetType
    asset_kind: str
    validate: Callable[[dict[str, Any], str, bool], Validated]
    tagline: Callable[[dict[str, Any]], str]
    needs_age: Callable[[dict[str, Any]], bool]


def _validate_character(data: dict[str, Any], visibility: str, imported: bool) -> Validated:
    try:
        card, warnings = validate_card(data, allow_missing_age=imported)
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise validation_failed(exc) from exc
    # Minor safety (AGENTS.md section 2.1); the rule itself lives only in pipeline/safety.py.
    if public_nsfw_blocked(card, visibility):
        raise AppError("nsfw_minor_public", "A public card with a character under 18 cannot be tagged nsfw", 422)
    return Validated(card.model_dump(mode="json"), warnings)


def _validate_world(data: dict[str, Any], visibility: str, imported: bool) -> Validated:
    try:
        world, warnings = validate_world(data)
    except ValueError as exc:
        raise validation_failed(exc) from exc
    return Validated(world.model_dump(mode="json"), warnings)


def _world_tagline(data: dict[str, Any]) -> str:
    rules = str(data.get("rules", "")).strip()
    return rules.splitlines()[0][:WORLD_TAGLINE_MAX] if rules else ""


CHARACTER_KIND = ContentKind(
    "character",
    "avatar",
    _validate_character,
    lambda data: str(data.get("tagline", "")),
    lambda data: data.get("age") is None,
)
WORLD_KIND = ContentKind("world", "cover", _validate_world, _world_tagline, lambda data: False)


class ContentManager:
    """CRUD for one content kind. Characters and worlds share all of it."""

    def __init__(self, kind: ContentKind, repo: ContentRepository, repos: Repos) -> None:
        self.kind = kind
        self._repo = repo
        self._repos = repos

    @property
    def repo(self) -> ContentRepository:
        return self._repo

    # --- output shaping ---

    def _summary_fields(self, record: ContentRecord) -> dict[str, Any]:
        data = record.data
        return {
            "id": str(record.id),
            "name": data.get("name", ""),
            "tagline": self.kind.tagline(data),
            "tags": data.get("tags", []),
            "visibility": record.visibility,
            "needs_age": self.kind.needs_age(data),
            "updated_at": record.updated_at,
        }

    def summary(self, record: ContentRecord) -> CharacterSummary | WorldSummary:
        fields = self._summary_fields(record)
        url = asset_url(record.asset_id)
        if self.kind.target_type == "character":
            return CharacterSummary(**fields, avatar_url=url)
        return WorldSummary(**fields, cover_url=url)

    def out(
        self, record: ContentRecord, vault_id: uuid.UUID, warnings: list[FormatWarning] | None = None
    ) -> CharacterOut | WorldOut:
        fields = self._summary_fields(record)
        url = asset_url(record.asset_id)
        extra: dict[str, Any] = {
            "data": record.data,
            "is_owner": record.vault_id == vault_id,
            "author": record.author,
            "created_at": record.created_at,
            "warnings": self._read_warnings(record.data) if warnings is None else warnings,
            "judge_score": record.judge_score,
        }
        if self.kind.target_type == "character":
            return CharacterOut(**fields, avatar_url=url, **extra)
        return WorldOut(**fields, cover_url=url, **extra)

    def _read_warnings(self, data: dict[str, Any]) -> list[FormatWarning]:
        try:
            return self.kind.validate(data, "private", True).warnings
        except AppError:
            return []

    # --- queries ---

    async def list_items(
        self, vault_id: uuid.UUID, *, q: str | None, tag: str | None, limit: int, cursor: str | None
    ) -> tuple[list[CharacterSummary | WorldSummary], str | None]:
        rows = await self._repo.list_owned(vault_id, q=q, tag=tag, limit=limit, cursor=parse_cursor(cursor))
        kept, next_cursor = paginate(rows, limit, lambda r: Cursor(r.updated_at, r.id))
        return [self.summary(r) for r in kept], next_cursor

    async def get_record(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> ContentRecord:
        """Own item or any vault's public item; anything else is 404."""
        record = await self._repo.get_visible(vault_id, item_id)
        if record is None:
            raise not_found()
        return record

    async def get(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> CharacterOut | WorldOut:
        return self.out(await self.get_record(vault_id, item_id), vault_id)

    # --- writes ---

    async def _sync_links(self, vault_id: uuid.UUID, record: ContentRecord) -> list[FormatWarning]:
        wanted = _uuid_list(record.data.get("lorebook_ids"))
        visible = await self._repos.lorebooks.visible_ids(vault_id, wanted)
        await self._repos.lorebooks.sync_links(
            vault_id, self.kind.target_type, record.id, [i for i in wanted if i in visible]
        )
        return [
            FormatWarning(
                path="lorebook_ids", code="lorebook_not_found", message=f"lorebook {i} was not found and is not linked"
            )
            for i in wanted
            if i not in visible
        ]

    async def create(
        self,
        vault_id: uuid.UUID,
        data: dict[str, Any],
        visibility: Visibility,
        *,
        imported: bool = False,
        image: bytes | None = None,
        commit: bool = True,
    ) -> CharacterOut | WorldOut:
        """Create an item. `commit=False` leaves the transaction open for a caller that commits once."""
        validated = self.kind.validate(data, visibility, imported)
        record = await self._repo.create(vault_id, data=validated.data, visibility=visibility)
        if image is not None:
            record = await self._attach_image(vault_id, record, image)
        warnings = validated.warnings + await self._sync_links(vault_id, record)
        if commit:
            await self._repos.commit()
        return self.out(record, vault_id, warnings)

    async def update(
        self, vault_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any], visibility: Visibility
    ) -> CharacterOut | WorldOut:
        if await self._repo.get_owned(vault_id, item_id) is None:
            raise not_found()
        validated = self.kind.validate(data, visibility, False)
        record = await self._repo.update(vault_id, item_id, data=validated.data, visibility=visibility)
        if record is None:
            raise not_found()
        warnings = validated.warnings + await self._sync_links(vault_id, record)
        await self._repos.commit()
        return self.out(record, vault_id, warnings)

    async def delete(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> None:
        record = await self._repo.get_owned(vault_id, item_id)
        if record is None:
            raise not_found()
        await self._repo.delete(vault_id, item_id)
        if record.asset_id:
            await self._repos.assets.delete(vault_id, record.asset_id)
        await self._repos.favorites.delete_for_target(self.kind.target_type, item_id)
        await self._repos.lorebooks.delete_links_for_target(vault_id, self.kind.target_type, item_id)
        await self._repos.commit()

    async def duplicate(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> CharacterOut | WorldOut:
        """A private copy in the acting vault; works on public items of other vaults."""
        source = await self.get_record(vault_id, item_id)
        data = copy.deepcopy(source.data)
        validated = self.kind.validate(data, "private", self.kind.needs_age(data))
        record = await self._repo.create(vault_id, data=validated.data, visibility="private")
        if source.asset_id:
            asset = await self._repos.assets.get(source.asset_id)
            if asset is not None:
                copied = await self._repos.assets.create(vault_id, kind=asset.kind, mime=asset.mime, data=asset.data)
                record = await self._set_asset(vault_id, record.id, copied.id)
        warnings = validated.warnings + await self._sync_links(vault_id, record)
        await self._repos.commit()
        return self.out(record, vault_id, warnings)

    # --- image ---

    async def _set_asset(self, vault_id: uuid.UUID, item_id: uuid.UUID, asset_id: uuid.UUID | None) -> ContentRecord:
        record = await self._repo.set_asset(vault_id, item_id, asset_id)
        if record is None:
            raise not_found()
        return record

    async def _attach_image(self, vault_id: uuid.UUID, record: ContentRecord, content: bytes) -> ContentRecord:
        mime = checked_image(content)
        asset = await self._repos.assets.create(vault_id, kind=self.kind.asset_kind, mime=mime, data=content)
        updated = await self._set_asset(vault_id, record.id, asset.id)
        if record.asset_id:
            await self._repos.assets.delete(vault_id, record.asset_id)
        return updated

    async def set_image(self, vault_id: uuid.UUID, item_id: uuid.UUID, content: bytes) -> CharacterOut | WorldOut:
        record = await self._repo.get_owned(vault_id, item_id)
        if record is None:
            raise not_found()
        updated = await self._attach_image(vault_id, record, content)
        await self._repos.commit()
        return self.out(updated, vault_id)

    async def clear_image(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> CharacterOut | WorldOut:
        record = await self._repo.get_owned(vault_id, item_id)
        if record is None:
            raise not_found()
        updated = await self._set_asset(vault_id, item_id, None)
        if record.asset_id:
            await self._repos.assets.delete(vault_id, record.asset_id)
        await self._repos.commit()
        return self.out(updated, vault_id)

    async def judge(
        self,
        vault_session: VaultSession,
        item_id: uuid.UUID,
        gateway_factory: GatewayFactory,
        settings: Settings,
    ) -> CharacterOut | WorldOut:
        """Score an owned character or world with Card Judge and persist `judge_score`."""
        record = await self._repo.get_owned(vault_session.vault_id, item_id)
        if record is None:
            raise not_found()
        gateway = gateway_factory(vault_session, None)
        agent_ctx = AgentContext(
            vault_id=vault_session.vault_id,
            chat_id=None,
            llm=gateway,
            settings=settings,
        )
        try:
            outcome = await card_judge.run(
                agent_ctx,
                card_judge.AgentConfig(),
                card_judge.CardJudgeInput(
                    target_type=self.kind.target_type,
                    data=record.data,
                    visibility=record.visibility,
                ),
            )
        except LLMError as exc:
            raise AppError("llm_failed", f"Card Judge failed ({exc.code})", 502) from exc
        score_payload = outcome.value.model_dump(mode="json")
        updated = await self._repo.set_judge_score(vault_session.vault_id, item_id, score_payload)
        if updated is None:
            raise not_found()
        await self._repos.commit()
        return self.out(updated, vault_session.vault_id)


# --- personas ---


class PersonaManager:
    def __init__(self, repos: Repos) -> None:
        self._repos = repos
        self._repo = repos.personas

    @staticmethod
    def out(record: PersonaRecord) -> PersonaOut:
        return PersonaOut(
            id=str(record.id),
            data=record.data,
            avatar_url=asset_url(record.asset_id),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _validate(data: dict[str, Any]) -> dict[str, Any]:
        try:
            persona, _ = validate_persona(data)
        except ValueError as exc:
            raise validation_failed(exc) from exc
        return persona.model_dump(mode="json")

    async def list_items(self, vault_id: uuid.UUID) -> list[PersonaOut]:
        return [self.out(r) for r in await self._repo.list(vault_id)]

    async def create(self, vault_id: uuid.UUID, data: dict[str, Any]) -> PersonaOut:
        record = await self._repo.create(vault_id, data=self._validate(data))
        await self._repos.commit()
        return self.out(record)

    async def get(self, vault_id: uuid.UUID, persona_id: uuid.UUID) -> PersonaOut:
        record = await self._repo.get(vault_id, persona_id)
        if record is None:
            raise not_found("Persona")
        return self.out(record)

    async def update(self, vault_id: uuid.UUID, persona_id: uuid.UUID, data: dict[str, Any]) -> PersonaOut:
        if await self._repo.get(vault_id, persona_id) is None:
            raise not_found("Persona")
        record = await self._repo.update(vault_id, persona_id, data=self._validate(data))
        if record is None:
            raise not_found("Persona")
        await self._repos.commit()
        return self.out(record)

    async def delete(self, vault_id: uuid.UUID, persona_id: uuid.UUID) -> None:
        record = await self._repo.get(vault_id, persona_id)
        if record is None:
            raise not_found("Persona")
        await self._repo.delete(vault_id, persona_id)
        if record.asset_id:
            await self._repos.assets.delete(vault_id, record.asset_id)
        await self._repos.commit()

    async def set_image(self, vault_id: uuid.UUID, persona_id: uuid.UUID, content: bytes | None) -> PersonaOut:
        """Replace the avatar with `content`, or remove it when `content` is None."""
        old = await self._repo.get(vault_id, persona_id)
        if old is None:
            raise not_found("Persona")
        asset_id: uuid.UUID | None = None
        if content is not None:
            mime = checked_image(content)
            asset_id = (await self._repos.assets.create(vault_id, kind="avatar", mime=mime, data=content)).id
        record = await self._repo.set_asset(vault_id, persona_id, asset_id)
        if record is None:
            raise not_found("Persona")
        if old.asset_id:
            await self._repos.assets.delete(vault_id, old.asset_id)
        await self._repos.commit()
        return self.out(record)


# --- lorebooks ---


class LorebookManager:
    def __init__(self, repos: Repos) -> None:
        self._repos = repos
        self._repo = repos.lorebooks

    @staticmethod
    def summary(record: LorebookRecord) -> LorebookSummary:
        return LorebookSummary(
            id=str(record.id),
            name=record.name,
            entry_count=record.entry_count,
            visibility=record.visibility,
            updated_at=record.updated_at,
        )

    @staticmethod
    def data_of(record: LorebookRecord) -> dict[str, Any]:
        return {**record.settings, "name": record.name, "entries": record.entries}

    @classmethod
    def out(cls, record: LorebookRecord, vault_id: uuid.UUID) -> LorebookOut:
        data = cls.data_of(record)
        return LorebookOut(
            **cls.summary(record).model_dump(),
            data=data,
            is_owner=record.vault_id == vault_id,
            author=record.author,
        )

    @staticmethod
    def split(data: dict[str, Any]) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        """Validate and split into (name, book-level settings, entries) for storage."""
        try:
            book, _ = validate_lorebook(data)
        except ValueError as exc:
            raise validation_failed(exc) from exc
        dumped = book.model_dump(mode="json")
        entries = dumped.pop("entries")
        name = dumped.pop("name")
        return name, dumped, entries

    async def list_items(
        self, vault_id: uuid.UUID, *, q: str | None, limit: int, cursor: str | None
    ) -> tuple[list[LorebookSummary], str | None]:
        rows = await self._repo.list_owned(vault_id, q=q, limit=limit, cursor=parse_cursor(cursor))
        kept, next_cursor = paginate(rows, limit, lambda r: Cursor(r.updated_at, r.id))
        return [self.summary(r) for r in kept], next_cursor

    async def get_record(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> LorebookRecord:
        record = await self._repo.get_visible(vault_id, lorebook_id)
        if record is None:
            raise not_found("Lorebook")
        return record

    async def get(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> LorebookOut:
        return self.out(await self.get_record(vault_id, lorebook_id), vault_id)

    async def create(
        self, vault_id: uuid.UUID, data: dict[str, Any], visibility: Visibility, *, commit: bool = True
    ) -> LorebookOut:
        name, settings, entries = self.split(data)
        record = await self._repo.create(vault_id, name=name, visibility=visibility, settings=settings, entries=entries)
        if commit:
            await self._repos.commit()
        return self.out(record, vault_id)

    async def update(
        self, vault_id: uuid.UUID, lorebook_id: uuid.UUID, data: dict[str, Any], visibility: Visibility
    ) -> LorebookOut:
        owned = await self._repo.get_visible(vault_id, lorebook_id)
        if owned is None or owned.vault_id != vault_id:
            raise not_found("Lorebook")
        name, settings, entries = self.split(data)
        record = await self._repo.update(
            vault_id, lorebook_id, name=name, visibility=visibility, settings=settings, entries=entries
        )
        if record is None:
            raise not_found("Lorebook")
        await self._repos.commit()
        return self.out(record, vault_id)

    async def delete(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> None:
        if not await self._repo.delete(vault_id, lorebook_id):
            raise not_found("Lorebook")
        await self._repos.commit()

    async def duplicate(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> LorebookOut:
        source = await self.get_record(vault_id, lorebook_id)
        record = await self._repo.create(
            vault_id,
            name=source.name,
            visibility="private",
            settings=copy.deepcopy(source.settings),
            entries=copy.deepcopy(source.entries),
        )
        await self._repos.commit()
        return self.out(record, vault_id)


class LibraryService:
    """Entry point used by routers and by the gallery and import services."""

    def __init__(self, repos: Repos) -> None:
        self.repos = repos
        self.characters = ContentManager(CHARACTER_KIND, repos.characters, repos)
        self.worlds = ContentManager(WORLD_KIND, repos.worlds, repos)
        self.personas = PersonaManager(repos)
        self.lorebooks = LorebookManager(repos)

    def content(self, target_type: Literal["character", "world"]) -> ContentManager:
        return self.characters if target_type == "character" else self.worlds


def get_library_service(repos: ReposDep) -> LibraryService:
    return LibraryService(repos)


LibraryServiceDep = Annotated[LibraryService, Depends(get_library_service)]


__all__ = [
    "ContentManager",
    "LibraryService",
    "LibraryServiceDep",
    "Repos",
    "ReposDep",
    "get_library_service",
    "get_repos",
    "not_found",
    "paginate",
    "parse_cursor",
]
