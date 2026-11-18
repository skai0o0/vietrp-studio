"""Default model ids per agent. This is the only place that defines them (AGENTS.md section 4.4)."""

from __future__ import annotations

from typing import Literal, get_args

AgentId = Literal[
    "orchestrator",
    "writer",
    "director",
    "state_keeper",
    "archivist",
    "creator",
    "card_judge",
    "bond_drafter",
    "bond_selector",
]

_CHAT_MODEL = "deepseek/deepseek-v4.1-flash-1017"
_DECISION_MODEL = "microsoft/microsoft-decision-1"

DEFAULT_MODELS: dict[AgentId, str] = {
    "writer": _CHAT_MODEL,
    "creator": _CHAT_MODEL,
    "archivist": _CHAT_MODEL,
    "bond_drafter": _CHAT_MODEL,
    "orchestrator": _DECISION_MODEL,
    "director": _DECISION_MODEL,
    "state_keeper": _DECISION_MODEL,
    "card_judge": _DECISION_MODEL,
    "bond_selector": _DECISION_MODEL,
}

# The Extractions API has no agent of its own; it defaults to the decision model.
DEFAULT_EXTRACTIONS_MODEL = _DECISION_MODEL

# Decisions/Extractions are alpha APIs; when they fail, this plain chat model answers the same questions.
FALLBACK_CHAT_MODEL = _CHAT_MODEL

AGENT_IDS: tuple[str, ...] = get_args(AgentId)
