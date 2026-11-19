from __future__ import annotations

import uuid

from app.formats.card import VietrpCard
from app.formats.lorebook import LorebookEntry
from app.formats.persona import Persona
from app.llm.tokenizer import CorrectionTable
from app.pipeline.context_budget import BudgetSettings
from app.pipeline.lorebook import LoreHit
from app.pipeline.prompt_assembler import AssemblyInput, BondView, HistoryMessage, assemble
from app.prompts.presets import resolve_preset


def make(**overrides: object) -> AssemblyInput:
    values: dict[str, object] = {
        "card": VietrpCard(name="Lan", age=25, personality="trầm tính", backstory="đã từng đi xa"),
        "messages": [HistoryMessage("user", "Chào chị")],
        "model": "m/x",
    }
    values.update(overrides)
    return AssemblyInput(**values)  # type: ignore[arg-type]


def test_layer_order_and_content() -> None:
    before = LoreHit(uuid.uuid4(), LorebookEntry(id="a", content="LORE_A", position="before_char"), 3, "keyword")
    after = LoreHit(uuid.uuid4(), LorebookEntry(id="b", content="LORE_B", position="after_char"), 3, "keyword")
    prompt = assemble(
        make(
            persona=Persona(name="Nam", age=22, gender="nam"),
            bonds=[BondView("Lan ↔ Nam", {"addressing": "chị-em", "closeness": "0"})],
            lore=[after, before],
            summary="Hai người quen nhau.",
            events=["Cứu nhau"],
            nsfw=True,
        )
    )
    assert [layer.name for layer in prompt.layers] == [
        "system",
        "nsfw",
        "lore_before",
        "card",
        "lore_after",
        "persona",
        "bonds",
        "memory",
        "history",
    ]
    text = {layer.name: layer.text for layer in prompt.layers}
    assert "Lan, 25 tuổi" in text["card"]
    assert "độ thân (0-4): 0" in text["bonds"]
    assert "Nam" in text["persona"]
    assert prompt.total_tokens > 0
    assert prompt.messages[-1] == {"role": "user", "content": "Chào chị"}


def test_card_field_selection_and_secrets() -> None:
    card = VietrpCard.model_validate(
        {
            "name": "Lan",
            "age": 25,
            "personality": "TRAM",
            "backstory": "QUAKHU",
            "secrets": [{"id": "s1", "content": "BIMAT", "reveal_when": "tin tưởng"}],
        }
    )
    default = assemble(make(card=card)).messages[1]["content"]
    assert "TRAM" in default
    assert "QUAKHU" in default
    assert "BIMAT" not in default
    picked = assemble(make(card=card, card_fields={"personality", "secrets"})).messages[1]["content"]
    assert "TRAM" in picked
    assert "QUAKHU" not in picked
    assert "BIMAT" in picked


def test_user_text_is_never_rendered_as_template() -> None:
    preset = resolve_preset({"system": "{{ 7*7 }} {{char}} với {{user}} {% if %}"})
    prompt = assemble(make(preset=preset, persona=Persona(name="Nam", age=20)))
    assert prompt.messages[0]["content"] == "{{ 7*7 }} Lan với Nam {% if %}"
    odd = assemble(make(card=VietrpCard(name="Lan", age=25, personality="{{ 7*7 }} {% x %}")))
    assert "{{ 7*7 }} {% x %}" in odd.messages[1]["content"]


def test_budget_trimming_keeps_newest_messages() -> None:
    history = [
        HistoryMessage("user" if i % 2 == 0 else "assistant", f"tin nhắn số {i} " + "chữ " * 30) for i in range(20)
    ]
    wide = assemble(make(messages=history, budget=BudgetSettings(context_length=100_000)))
    assert wide.history_dropped == 0
    fixed = sum(layer.tokens + 4 for layer in wide.layers if layer.name != "history")
    small = BudgetSettings(context_length=fixed + 600, response_reserve=0)
    prompt = assemble(make(messages=history, budget=small))
    kept = [m["content"] for m in prompt.messages if m["role"] != "system"]
    assert 0 < len(kept) < 20
    assert prompt.history_dropped == 20 - len(kept)
    assert kept == [m.content for m in history[-len(kept) :]]
    assert prompt.total_tokens <= small.prompt_budget
    assert not prompt.over_budget


def test_newest_message_kept_even_if_over_budget() -> None:
    huge = HistoryMessage("user", "x " * 5000)
    prompt = assemble(make(messages=[HistoryMessage("user", "cũ"), huge], budget=BudgetSettings(context_length=300)))
    assert prompt.messages[-1]["content"] == huge.content
    assert prompt.over_budget
    assert prompt.history_dropped == 1


def test_correction_factor_inflates_counts() -> None:
    base = assemble(make())
    table = CorrectionTable()
    table.observe("m/x", base.total_tokens, base.total_tokens * 2)
    corrected = assemble(make(corrections=table))
    assert corrected.total_tokens > base.total_tokens


def test_substitutes_user_and_char_placeholders_and_keeps_minor_rule_last() -> None:
    from uuid import uuid4

    from app.formats.card import Addressing, VietrpCard
    from app.formats.lorebook import LorebookEntry
    from app.formats.persona import Persona
    from app.pipeline.lorebook import LoreHit
    from app.pipeline.prompt_assembler import AssemblyInput, HistoryMessage, assemble

    card = VietrpCard(
        name="Linh",
        age=17,
        personality="{{char}} luôn giữ khoảng cách với {{user}}.",
        addressing=Addressing(user="{{char}} gọi {{user}} là cậu"),
    )
    lore = [
        LoreHit(
            book_id=uuid4(),
            entry=LorebookEntry(
                id="truoc",
                title="Quán quen",
                position="before_char",
                content="{{user}} hay ghé quán của {{char}}.",
            ),
            tokens=12,
            reason="constant",
        ),
        LoreHit(
            book_id=uuid4(),
            entry=LorebookEntry(
                id="sau",
                title="Quy ước",
                position="after_char",
                content="{{char}} nhớ tên {{user}}.",
            ),
            tokens=10,
            reason="keyword",
        ),
    ]
    prompt = assemble(
        AssemblyInput(
            card=card,
            persona=Persona(name="Minh", age=20),
            messages=[
                HistoryMessage("user", "Chào {{char}}, mình là {{user}}"),
                HistoryMessage("assistant", "{{char}} gật đầu với {{user}}"),
            ],
            lore=lore,
            summary="{{user}} đã gặp {{char}} tối qua.",
            prefill="{{char}} nhìn {{user}}:",
            model="m/x",
            nsfw=True,
        )
    )
    all_text = "\n".join(layer.text for layer in prompt.layers)
    assert "{{user}}" not in all_text
    assert "{{char}}" not in all_text
    assert "Linh luôn giữ khoảng cách với Minh." in all_text
    assert "Linh gọi Minh là cậu" in all_text
    assert "Minh hay ghé quán của Linh." in all_text
    assert "Linh nhớ tên Minh." in all_text
    assert "Minh đã gặp Linh tối qua." in all_text
    assert prompt.messages[-2]["content"] == "Linh gật đầu với Minh"
    assert prompt.messages[-1] == {"role": "assistant", "content": "Linh nhìn Minh:"}

    system_names = [layer.name for layer in prompt.layers if layer.name not in {"history", "prefill"}]
    assert system_names[-1] == "minor_rule"

    no_persona = assemble(AssemblyInput(card=card, messages=[], model="m/x"))
    card_layer = next(layer.text for layer in no_persona.layers if layer.name == "card")
    assert "người chơi" in card_layer
    assert "{{user}}" not in card_layer
