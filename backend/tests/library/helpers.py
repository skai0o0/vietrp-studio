from __future__ import annotations

import struct
import zlib
from typing import Any

import httpx


def card(name: str = "Lan", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": "vietrp-card",
        "spec_version": "1.0",
        "name": name,
        "age": 25,
        "tagline": f"{name} tagline",
        "personality": "Điềm tĩnh",
        "greetings": ["Xin chào"],
        "tags": ["slice"],
    }
    data.update(overrides)
    return data


def world(name: str = "Hà Thành", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": "vietrp-world",
        "spec_version": "1.0",
        "name": name,
        "rules": "Thế giới yên bình.\nKhông phép thuật.",
        "tags": ["modern"],
        "locations": [{"id": "city", "level": "province", "name": "Thành phố"}],
        "openings": [{"id": "start", "location_id": "city", "message": "Mở đầu"}],
    }
    data.update(overrides)
    return data


def lorebook(name: str = "Sổ tay", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": "vietrp-lorebook",
        "spec_version": "1.0",
        "name": name,
        "entries": [{"id": "e1", "keys": ["kiếm"], "content": "Thanh kiếm cổ."}],
    }
    data.update(overrides)
    return data


def persona(name: str = "Minh") -> dict[str, Any]:
    return {"format": "vietrp-persona", "spec_version": "1.0", "name": name, "age": 20}


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def tiny_png() -> bytes:
    """A valid 1x1 PNG."""
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def upload(content: bytes, filename: str = "file.png") -> dict[str, Any]:
    return {"files": {"file": (filename, content, "application/octet-stream")}}


async def post_card(client: httpx.AsyncClient, visibility: str = "private", **kwargs: Any) -> dict[str, Any]:
    response = await client.post("/api/characters", json={"data": card(**kwargs), "visibility": visibility})
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()["character"]
    return result
