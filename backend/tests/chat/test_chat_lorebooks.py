"""Per-chat lorebook list: defaults to the card snapshot, can add books linked later, and can drop books."""

from __future__ import annotations

from typing import Any

from tests.chat.conftest import ChatEnv, make_character, make_chat
from tests.chat.test_world_chat import make_lorebook


async def lore_text(env: ChatEnv, chat_id: str, text: str) -> str:
    preview = (await env.a.get(f"/api/chats/{chat_id}/prompt-preview", params={"text": text})).json()
    return " ".join(la["text"] for la in preview["layers"] if la["name"].startswith("lore"))


async def set_books(env: ChatEnv, chat: dict[str, Any], book_ids: list[str] | None) -> dict[str, Any]:
    lorebook = dict(chat["settings"]["lorebook"], book_ids=book_ids)
    response = await env.a.patch(
        f"/api/chats/{chat['id']}", json={"settings": dict(chat["settings"], lorebook=lorebook)}
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_chat_lorebooks_default_add_and_remove(env: ChatEnv) -> None:
    old_book = await make_lorebook(env.a, "Nha", ["phòng trọ"], "Phòng trọ của Mai ở tầng ba.")
    character_id = await make_character(env.a, lorebook_ids=[old_book])
    chat = await make_chat(env.a, character_id)
    assert chat["default_lorebook_ids"] == [old_book]
    assert chat["settings"]["lorebook"]["book_ids"] is None
    assert "tầng ba" in await lore_text(env, chat["id"], "về phòng trọ")

    # A book created after the chat (e.g. imported World Info) reaches this chat once added to its list.
    new_book = await make_lorebook(env.a, "Truong", ["trường"], "Trường của Mai tên Lê Lợi.")
    assert "Lê Lợi" not in await lore_text(env, chat["id"], "ở trường")
    chat = await set_books(env, chat, [old_book, new_book])
    assert chat["settings"]["lorebook"]["book_ids"] == [old_book, new_book]
    assert "Lê Lợi" in await lore_text(env, chat["id"], "ở trường")

    # Dropping the card's own book only affects this chat; the card keeps its link.
    chat = await set_books(env, chat, [new_book])
    assert "tầng ba" not in await lore_text(env, chat["id"], "về phòng trọ")
    card = (await env.a.get(f"/api/characters/{character_id}")).json()["character"]
    assert card["data"]["lorebook_ids"] == [old_book]

    # Back to the card default.
    chat = await set_books(env, chat, None)
    assert "tầng ba" in await lore_text(env, chat["id"], "về phòng trọ")


async def test_chat_lorebooks_ignore_books_of_other_vaults(env: ChatEnv) -> None:
    other_book = await make_lorebook(env.b, "Khac", ["bí mật"], "BOOK_OF_ANOTHER_VAULT")
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    await set_books(env, chat, [other_book])
    assert "BOOK_OF_ANOTHER_VAULT" not in await lore_text(env, chat["id"], "bí mật")
