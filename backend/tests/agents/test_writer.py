from __future__ import annotations

import json

from app.agents.base import AgentContext
from app.agents.writer import AgentConfig, WriterDelta, WriterDone, WriterInput, build_messages, run
from app.llm.fake import RecordedLLM
from app.pipeline.prompt_assembler import AssembledLayer, AssembledPrompt
from tests.conftest import make_settings
from tests.llm.test_wiring import make_gateway


def _prompt(with_prefill: bool = False) -> AssembledPrompt:
    messages = [
        {"role": "system", "content": "luật"},
        {"role": "system", "content": "quy tắc an toàn"},
        {"role": "user", "content": "Chào"},
    ]
    layers = [AssembledLayer("history", 3, "user: Chào")]
    if with_prefill:
        messages.append({"role": "assistant", "content": "Mai"})
        layers.append(AssembledLayer("prefill", 1, "Mai"))
    return AssembledPrompt(messages=messages, layers=layers, total_tokens=10)


def test_fix_hints_are_a_user_message_before_the_prefill() -> None:
    inp = WriterInput(_prompt(with_prefill=True), fix_hints=["Phản hồi thẳng."], rejected_draft="bản cũ")
    messages = build_messages(inp)
    assert [m["role"] for m in messages] == ["system", "system", "user", "user", "assistant"]
    assert "Phản hồi thẳng." in messages[3]["content"] and "bản cũ" in messages[3]["content"]
    # The safety layer stays the last system message; the input is not mutated.
    assert messages[1]["content"] == "quy tắc an toàn" and len(inp.prompt.messages) == 4


def test_no_hints_leaves_messages_unchanged() -> None:
    assert build_messages(WriterInput(_prompt())) == _prompt().messages


async def _collect(inp: WriterInput) -> tuple[list[WriterDelta | WriterDone], RecordedLLM]:
    llm = RecordedLLM.from_dir(names=["writer_stream.json", "writer_stream_plain.json", "wiring_models.json"])
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=gateway.chat_id, llm=gateway, settings=make_settings())
    try:
        return [e async for e in run(ctx, AgentConfig(), inp)], llm
    finally:
        await services.aclose()


async def test_streams_deltas_then_done() -> None:
    events, _ = await _collect(WriterInput(_prompt()))
    deltas = [e.text for e in events if isinstance(e, WriterDelta)]
    done = events[-1]
    assert isinstance(done, WriterDone)
    assert "".join(deltas) == done.text == 'Mai ngẩng lên. "Chào cậu."'
    assert done.finish_reason == "stop" and done.usage is not None and done.usage.completion_tokens == 9


async def test_retry_sends_hints_to_the_model() -> None:
    events, llm = await _collect(WriterInput(_prompt(), fix_hints=["Bỏ lời thoại của người chơi."]))
    done = events[-1]
    assert isinstance(done, WriterDone) and done.text == "Mai mỉm cười."
    body = json.loads(llm.requests[-1].content)
    assert body["messages"][-1]["role"] == "user" and "Bỏ lời thoại" in body["messages"][-1]["content"]


def test_config_for_grows_the_budget_only_with_reasoning() -> None:
    from app.agents.writer import config_for
    from app.core.config import WRITER_REASONING_EXTRA_TOKENS

    assert config_for("m", "off").max_tokens == AgentConfig().max_tokens
    on = config_for("m", "high")
    assert on.reasoning == "high" and on.max_tokens == AgentConfig().max_tokens + WRITER_REASONING_EXTRA_TOKENS
