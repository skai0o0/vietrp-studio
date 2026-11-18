"""Creator session persistence. Every method takes `vault_id` and filters on it."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import CreatorSession

UPDATABLE_FIELDS = frozenset({"seed", "messages", "raw", "result"})


@dataclass(frozen=True, slots=True)
class CreatorSessionRecord:
    id: uuid.UUID
    vault_id: uuid.UUID
    mode: str
    seed: dict[str, Any]
    messages: list[dict[str, Any]]
    raw: str | None
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class CreatorRepository(Protocol):
    async def create(self, vault_id: uuid.UUID, *, mode: str, seed: dict[str, Any]) -> CreatorSessionRecord: ...

    async def get(self, vault_id: uuid.UUID, session_id: uuid.UUID) -> CreatorSessionRecord | None: ...

    async def update(
        self, vault_id: uuid.UUID, session_id: uuid.UUID, fields: dict[str, Any]
    ) -> CreatorSessionRecord | None: ...

    async def delete(self, vault_id: uuid.UUID, session_id: uuid.UUID) -> bool: ...

    async def commit(self) -> None: ...


def _to_record(row: CreatorSession) -> CreatorSessionRecord:
    return CreatorSessionRecord(
        id=row.id,
        vault_id=row.vault_id,
        mode=row.mode,
        seed=copy.deepcopy(row.seed),
        messages=copy.deepcopy(list(row.messages)),
        raw=row.raw,
        result=copy.deepcopy(row.result) if row.result is not None else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlCreatorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _row(self, vault_id: uuid.UUID, session_id: uuid.UUID) -> CreatorSession | None:
        return await self._session.scalar(
            select(CreatorSession).where(CreatorSession.id == session_id, CreatorSession.vault_id == vault_id)
        )

    async def create(self, vault_id: uuid.UUID, *, mode: str, seed: dict[str, Any]) -> CreatorSessionRecord:
        now = datetime.now(UTC)
        row = CreatorSession(
            id=uuid.uuid4(),
            vault_id=vault_id,
            mode=mode,
            seed=copy.deepcopy(seed),
            messages=[],
            raw=None,
            result=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_record(row)

    async def get(self, vault_id: uuid.UUID, session_id: uuid.UUID) -> CreatorSessionRecord | None:
        row = await self._row(vault_id, session_id)
        return _to_record(row) if row else None

    async def update(
        self, vault_id: uuid.UUID, session_id: uuid.UUID, fields: dict[str, Any]
    ) -> CreatorSessionRecord | None:
        row = await self._row(vault_id, session_id)
        if row is None:
            return None
        for key, value in fields.items():
            if key not in UPDATABLE_FIELDS:
                raise ValueError(f"cannot update creator session field {key!r}")
            setattr(row, key, copy.deepcopy(value))
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _to_record(row)

    async def delete(self, vault_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(CreatorSession)
            .where(CreatorSession.id == session_id, CreatorSession.vault_id == vault_id)
            .returning(CreatorSession.id)
        )
        return result.first() is not None

    async def commit(self) -> None:
        await self._session.commit()
