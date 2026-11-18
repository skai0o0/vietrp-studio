from __future__ import annotations

import pytest

from app.pipeline.scene_parser import (
    SCENE_CLOSE_TAG,
    SCENE_OPEN_TAG,
    SCENE_PREFIX,
    SceneStreamFilter,
    merge_scene,
    parse_scene_block,
    strip_scene_block,
    visible_scene,
)
from app.schemas.world_state import CharacterSceneState, SceneDelta, SceneState


def test_stream_filter_plain_text_forwards_immediately() -> None:
    flt = SceneStreamFilter()
    assert flt.feed("Chào ") == "Chào "
    assert flt.feed("bạn nhé!") == "bạn nhé!"
    trailing, block = flt.finish()
    assert trailing == ""
    assert block is None
    assert flt.visible_text == "Chào bạn nhé!"
    assert flt.scene_buffer == ""


def test_stream_filter_handles_split_scene_tag_across_chunks() -> None:
    flt = SceneStreamFilter()
    emitted: list[str] = []
    chunks = [
        "Vy mỉm cười.<sc",
        'ene>\n{"env": {"weather": "mưa"}, ',
        '"chars": {"vy": {"mood": "vui"}}}\n</scene>',
    ]
    for chunk in chunks:
        emitted.append(flt.feed(chunk))
    trailing, block = flt.finish()
    emitted.append(trailing)

    assert "".join(emitted) == "Vy mỉm cười."
    assert flt.visible_text == "Vy mỉm cười."
    assert block == '<scene>\n{"env": {"weather": "mưa"}, "chars": {"vy": {"mood": "vui"}}}\n</scene>'
    assert flt.scene_buffer == block
    # Calling finish again is idempotent.
    assert flt.finish() == ("", block)


def test_stream_filter_one_char_chunks_and_case_insensitive_tag() -> None:
    text = 'Cô bước vào.<Scene>\n{"env": {"ambience": "ồn"}}\n</Scene>'
    flt = SceneStreamFilter()
    out = [flt.feed(ch) for ch in text]
    trailing, block = flt.finish()
    assert "".join(out) + trailing == "Cô bước vào."
    assert flt.visible_text == "Cô bước vào."
    assert block == '<Scene>\n{"env": {"ambience": "ồn"}}\n</Scene>'


def test_stream_filter_releases_false_positive_prefixes() -> None:
    flt = SceneStreamFilter()
    out1 = flt.feed("A < B và <sc")
    assert out1 == "A < B và "
    out2 = flt.feed("ript>test</script> và <3")
    assert out2 == "<script>test</script> và <3"
    trailing, block = flt.finish()
    assert trailing == ""
    assert block is None
    assert flt.visible_text == "A < B và <script>test</script> và <3"


def test_stream_filter_flushes_trailing_partial_prefix_on_finish() -> None:
    flt = SceneStreamFilter()
    assert flt.feed("Nhìn kia <sc") == "Nhìn kia "
    trailing, block = flt.finish()
    assert trailing == "<sc"
    assert block is None
    assert flt.visible_text == "Nhìn kia <sc"


def test_stream_filter_handles_false_prefix_followed_immediately_by_scene() -> None:
    flt = SceneStreamFilter()
    assert flt.feed("abc<sc") == "abc"
    assert flt.feed("<scene>{}</scene>") == "<sc"
    trailing, block = flt.finish()
    assert trailing == ""
    assert block == "<scene>{}</scene>"
    assert flt.visible_text == "abc<sc"


def test_constants_and_strip_scene_block() -> None:
    assert SCENE_OPEN_TAG == "<scene>"
    assert SCENE_CLOSE_TAG == "</scene>"
    assert SCENE_PREFIX == "<scene"

    assert strip_scene_block("Chỉ là lời thoại.") == ("Chỉ là lời thoại.", None)
    visible, block = strip_scene_block('Cô ấy gật đầu.\n\n<scene>\n{"env": {"light": "tối"}}\n</scene>')
    assert visible == "Cô ấy gật đầu."
    assert block == '<scene>\n{"env": {"light": "tối"}}\n</scene>'


@pytest.mark.parametrize("raw", [None, "", "   ", "<scene></scene>", "<scene>\n  \n</scene>"])
def test_parse_scene_block_empty_returns_none_without_notice(raw: str | None) -> None:
    delta, notice = parse_scene_block(raw)
    assert delta is None
    assert notice is None


def test_parse_scene_block_valid_architecture_example() -> None:
    raw = """<scene>
{"env": {"weather": "mưa lất phất", "ambience": "căn tin vắng"},
 "chars": {"vy": {"mood": "dỗi", "outfit": "áo khoác đồng phục",
                  "pose": "ngồi vắt chân", "holding": "ly trà sữa", "condition": ""}},
 "items": ["cuốn sổ của Hân rơi dưới gầm bàn"]}
</scene>"""
    delta, notice = parse_scene_block(raw)
    assert notice is None
    assert delta is not None
    assert delta.env == {"weather": "mưa lất phất", "ambience": "căn tin vắng"}
    assert delta.chars["vy"].mood == "dỗi"
    assert delta.chars["vy"].holding == "ly trà sữa"
    assert delta.chars["vy"].condition == ""
    assert delta.chars["vy"].model_fields_set == {"mood", "outfit", "pose", "holding", "condition"}
    assert delta.items == ["cuốn sổ của Hân rơi dưới gầm bàn"]


def test_parse_scene_block_strips_code_fences_and_trailing_text() -> None:
    raw = '<scene>\n```json\n{"env": {"weather": "nắng"}}\n```\n</scene>\n(Ghi chú thừa ngoài thẻ)'
    delta, notice = parse_scene_block(raw)
    assert notice is None
    assert delta == SceneDelta(env={"weather": "nắng"})


def test_parse_scene_block_repairs_trailing_commas_single_quotes_and_unclosed_brace() -> None:
    # Trailing commas + commas inside string values preserved
    raw_commas = '<scene>{"env": {"a": "một, } hai",}, "items": ["sổ",],}</scene>'
    delta1, n1 = parse_scene_block(raw_commas)
    assert n1 is None
    assert delta1 is not None and delta1.env == {"a": "một, } hai"} and delta1.items == ["sổ"]

    # Single quotes + apostrophe inside double quotes + double quotes inside single quotes
    raw_quotes = (
        "<scene>{'env': {'note': \"it's ok\", 'quote': 'nói \"ừ\"'}, 'chars': {'vy': {'mood': 'vui',}}}</scene>"
    )
    delta2, n2 = parse_scene_block(raw_quotes)
    assert n2 is None
    assert delta2 is not None
    assert delta2.env == {"note": "it's ok", "quote": 'nói "ừ"'}
    assert delta2.chars["vy"].mood == "vui"
    assert delta2.chars["vy"].model_fields_set == {"mood"}

    # Unclosed outer brace (truncated stream)
    raw_unclosed = '<scene>{"env": {"weather": "gió mạnh"}, "items": ["ô"'
    delta3, n3 = parse_scene_block(raw_unclosed)
    assert n3 is None
    assert delta3 is not None and delta3.env == {"weather": "gió mạnh"} and delta3.items == ["ô"]

    # Python literals with single quotes
    raw_py = "<scene>{'env': {'rain': True, 'none_val': None}}</scene>"
    delta4, n4 = parse_scene_block(raw_py)
    assert n4 is None
    assert delta4 is not None and delta4.env == {"rain": "true", "none_val": ""}


def test_parse_scene_block_lenient_scalars_and_unknown_char_keys() -> None:
    raw = """<scene>
    {"env": {"temp": 27, "raining": false},
     "chars": {"vy": {"mood": "bình tĩnh", "extra_ignored": "foo", "holding": ""}}}
    </scene>"""
    delta, notice = parse_scene_block(raw)
    assert notice is None
    assert delta is not None
    assert delta.env == {"temp": "27", "raining": "false"}
    assert delta.chars["vy"].mood == "bình tĩnh"
    assert delta.chars["vy"].holding == ""
    assert delta.chars["vy"].model_fields_set == {"mood", "holding"}


@pytest.mark.parametrize(
    "raw",
    [
        "<scene>không phải json</scene>",
        '<scene>{"env": "unclosed</scene>',
        "<scene>[1, 2, 3]</scene>",
        '<scene>{"items": "must-be-list"}</scene>',
        '<scene>{"chars": "must-be-object"}</scene>',
        '<scene>{"env": {"nested": {"bad": 1}}}</scene>',
    ],
)
def test_parse_scene_block_broken_returns_notice_and_never_raises(raw: str) -> None:
    delta, notice = parse_scene_block(raw)
    assert delta is None
    assert notice is not None
    assert notice.code == "scene_parse_failed"
    assert notice.agent == "writer"
    assert notice.detail.isascii()


def test_merge_scene_per_character_restricts_other_chars() -> None:
    initial = SceneState(
        env={"weather": "nắng", "ambience": "sân trường"},
        chars={
            "vy": CharacterSceneState(mood="vui", outfit="áo dài", holding="cặp"),
            "han": CharacterSceneState(mood="buồn", outfit="váy"),
        },
        items=["ghế đá"],
    )
    delta, _ = parse_scene_block(
        '<scene>{"env": {"weather": "mây"}, '
        '"chars": {"vy": {"mood": "ngại", "holding": ""}, "han": {"mood": "giận"}}, '
        '"items": ["ghế đá", "bút"]}</scene>'
    )
    merged = merge_scene(initial, delta, speaker_id="vy", write_mode="per_character")

    assert merged.env == {"weather": "mây", "ambience": "sân trường"}
    assert merged.items == ["ghế đá", "bút"]
    # vy updated mood and explicitly cleared holding, while keeping outfit
    assert merged.chars["vy"] == CharacterSceneState(mood="ngại", outfit="áo dài", holding="")
    # han was protected from vy's per_character edit
    assert merged.chars["han"] == CharacterSceneState(mood="buồn", outfit="váy")
    # Input was not mutated
    assert initial.chars["vy"].holding == "cặp"


def test_merge_scene_narrator_and_single_call_allow_multiple_chars() -> None:
    initial = SceneState(
        chars={
            "vy": CharacterSceneState(mood="bình thường", outfit="đồng phục"),
            "han": CharacterSceneState(mood="tò mò", pose="đứng"),
        },
        items=["ly nước"],
    )
    delta = SceneDelta.model_validate(
        {
            "chars": {
                "vy": {"mood": "căng thẳng"},
                "han": {"pose": "ngồi xuống", "holding": "túi xách"},
            },
            "items": None,
        }
    )

    as_narrator = merge_scene(initial, delta, speaker_id="narrator", write_mode="per_character")
    assert as_narrator.chars["vy"].mood == "căng thẳng"
    assert as_narrator.chars["vy"].outfit == "đồng phục"
    assert as_narrator.chars["han"].pose == "ngồi xuống"
    assert as_narrator.chars["han"].holding == "túi xách"
    assert as_narrator.items == ["ly nước"]

    as_single = merge_scene(initial, delta, speaker_id="group", write_mode="single_call")
    assert as_single == as_narrator


def test_visible_scene_and_merge_scene_hide_absent_characters() -> None:
    scene = SceneState(
        env={"ambience": "yên tĩnh"},
        chars={
            "vy": CharacterSceneState(mood="vui"),
            "han": CharacterSceneState(mood="mệt"),
        },
        items=["đèn pin"],
    )
    shown = visible_scene(scene, ["vy"])
    assert list(shown.chars) == ["vy"]
    assert shown.env == {"ambience": "yên tĩnh"}
    assert shown.items == ["đèn pin"]
    assert "han" in scene.chars  # original preserved

    merged = merge_scene(scene, None, speaker_id="vy", write_mode="per_character", present_ids=["vy"])
    assert list(merged.chars) == ["vy"]
