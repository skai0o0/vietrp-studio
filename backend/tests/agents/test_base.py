from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from app.agents.base import AgentContext, AgentResult, LLMGateway, Notice, run_non_critical
from app.llm.client import LLMError
from app.llm.deps import build_llm_services
from app.llm.fake import RecordedLLM
from app.llm.usage import Usage
from tests.conftest import make_settings
from tests.llm.helpers import FAKE_KEY


async def _key() -> str:
    return FAKE_KEY


async def _ok() -> AgentResult[str]:
    return AgentResult(value="fine", usage=[Usage(prompt_tokens=3)])


async def test_run_non_critical_passes_success_through() -> None:
    result = await run_non_critical("state_keeper", _ok())
    assert result.value == "fine" and result.notices == [] and result.usage[0].prompt_tokens == 3


async def test_run_non_critical_turns_failure_into_notice() -> None:
    async def boom() -> AgentResult[str]:
        raise LLMError("llm_upstream_error", 503, f"HTTP 503: down {FAKE_KEY}")

    result = await run_non_critical("archivist", boom())
    assert result.value is None
    assert result.notices == [Notice(code="agent_failed", agent="archivist", detail="llm_upstream_error")]
    # Free-text exception content is never copied into a notice.
    assert FAKE_KEY not in repr(result)


async def test_run_non_critical_names_unexpected_errors_by_type_only() -> None:
    async def boom() -> AgentResult[str]:
        raise ValueError(f"secret {FAKE_KEY}")

    result = await run_non_critical("bond_selector", boom())
    assert result.notices[0].detail == "ValueError" and FAKE_KEY not in repr(result)


async def test_run_non_critical_does_not_swallow_cancellation() -> None:
    async def cancelled() -> AgentResult[str]:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_non_critical("card_judge", cancelled())


async def test_agent_context_defaults_to_utc_clock() -> None:
    services = build_llm_services(make_settings(), transport=RecordedLLM().transport())
    try:
        vault_id = uuid.uuid4()
        gateway = LLMGateway(services, vault_id=vault_id, chat_id=None, api_key=_key)
        ctx = AgentContext(vault_id=vault_id, chat_id=None, llm=gateway, settings=make_settings())
    finally:
        await services.aclose()
    now = ctx.clock()
    assert isinstance(now, datetime) and now.tzinfo is UTC
