"""Process-wide LLM objects, built once in the app lifespan and shared by every request.

None of these hold an API key: the key is read from the vault per call (see `agents.base.ApiKeyProvider`).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.llm.client import OpenRouterClient
from app.llm.config import LLMConfig
from app.llm.decisions import (
    ChatFallbackDecisionClient,
    DecisionClient,
    OpenRouterDecisionClient,
    ResilientDecisionClient,
)
from app.llm.extractions import (
    ChatFallbackExtractionClient,
    ExtractionClient,
    OpenRouterExtractionClient,
    ResilientExtractionClient,
)
from app.llm.pricing import PricingCache
from app.llm.tokenizer import CorrectionTable

# Vault secret that holds the user's OpenRouter key (must be in `Settings.allowed_secret_names`).
OPENROUTER_KEY_SECRET = "OPENROUTER_API_KEY"


@dataclass(slots=True)
class LLMServices:
    cfg: LLMConfig
    client: OpenRouterClient
    pricing: PricingCache
    corrections: CorrectionTable
    decisions: DecisionClient
    extractions: ExtractionClient

    async def aclose(self) -> None:
        await self.client.aclose()


def build_llm_services(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    cfg: LLMConfig | None = None,
) -> LLMServices:
    """`transport` lets tests route every call to a `RecordedLLM` instead of the network."""
    cfg = cfg or LLMConfig.from_settings(settings)
    client = OpenRouterClient(cfg, transport=transport)
    return LLMServices(
        cfg=cfg,
        client=client,
        pricing=PricingCache(client),
        corrections=CorrectionTable(cfg),
        decisions=ResilientDecisionClient(OpenRouterDecisionClient(client), ChatFallbackDecisionClient(client)),
        extractions=ResilientExtractionClient(OpenRouterExtractionClient(client), ChatFallbackExtractionClient(client)),
    )
