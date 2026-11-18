"""Utility routes: model list, token counting and usage rows."""

from __future__ import annotations

import datetime as dt
import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.deps import LLMServicesDep, VaultSessionDep
from app.core.errors import AppError
from app.llm.client import LLMError
from app.llm.pricing import MODELS_PATH
from app.llm.tokenizer import count_text
from app.services.chat_service import ChatServiceDep, parse_chat_id

router = APIRouter(prefix="/api", tags=["utility"])

# Most usage rows one request returns.
USAGE_ROWS_LIMIT = 200


class ModelInfo(BaseModel):
    id: str
    name: str
    context_length: int | None = None


class TokenCountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    # When given, the estimate is multiplied by that model's learned correction factor.
    model: str | None = None


class TokenCount(BaseModel):
    tokens: int = Field(ge=0)


class UsageRowOut(BaseModel):
    agent: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost: float
    created_at: dt.datetime


@router.get("/models", response_model=list[ModelInfo])
async def list_models(_session: VaultSessionDep, services: LLMServicesDep) -> list[ModelInfo]:
    """The public OpenRouter model list (no key needed), trimmed to what the UI shows."""
    try:
        data = await services.client.get_json(MODELS_PATH)
        entries = data["data"]
    except (LLMError, KeyError, TypeError) as exc:
        raise AppError("llm_failed", "Could not load the model list", 502) from exc
    models: list[ModelInfo] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        length = entry.get("context_length")
        models.append(
            ModelInfo(
                id=entry["id"],
                name=str(entry.get("name") or entry["id"]),
                context_length=length if isinstance(length, int) and not isinstance(length, bool) else None,
            )
        )
    return models


@router.post("/tokens/count", response_model=TokenCount)
async def count_tokens(body: TokenCountRequest, _session: VaultSessionDep, services: LLMServicesDep) -> TokenCount:
    factor = services.corrections.factor(body.model) if body.model else 1.0
    return TokenCount(tokens=math.ceil(count_text(body.text) * factor))


@router.get("/usage", response_model=list[UsageRowOut])
async def usage(
    session: VaultSessionDep, service: ChatServiceDep, chat_id: Annotated[str | None, Query()] = None
) -> list[UsageRowOut]:
    parsed: uuid.UUID | None = parse_chat_id(chat_id) if chat_id else None
    rows = await service.usage_rows(session.vault_id, parsed, limit=USAGE_ROWS_LIMIT)
    return [UsageRowOut.model_validate(row, from_attributes=True) for row in rows]
