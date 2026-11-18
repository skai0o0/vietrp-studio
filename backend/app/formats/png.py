"""Minimal PNG chunk reader/writer for SillyTavern cards (tEXt chunks only, stdlib only)."""

from __future__ import annotations

import struct
import zlib

from app.core.errors import AppError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Upper bound on accepted input size (WP-H: cap at 20 MB).
MAX_PNG_BYTES = 20 * 1024 * 1024

_CHUNK_OVERHEAD = 12  # length(4) + type(4) + crc(4)
_PLACEHOLDER_SIZE = 8
_PLACEHOLDER_RGB = bytes((24, 24, 32))


class PngError(AppError):
    """Raised for unreadable or unsafe PNG input."""

    def __init__(self, code: str, message: str) -> None:
        # Contract (P1 WP-I): oversized input is 413, any other format problem is 422.
        super().__init__(code, message, status=413 if code == "file_too_large" else 422)


def is_png(data: bytes) -> bool:
    return data.startswith(PNG_SIGNATURE)


def _crc(chunk_type: bytes, body: bytes) -> int:
    return zlib.crc32(chunk_type + body) & 0xFFFFFFFF


def _make_chunk(chunk_type: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + chunk_type + body + struct.pack(">I", _crc(chunk_type, body))


def _iter_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Parse all chunks, verifying the signature, every CRC and the presence of IEND."""
    if len(data) > MAX_PNG_BYTES:
        raise PngError("file_too_large", "PNG exceeds the size limit")
    if not is_png(data):
        raise PngError("png_invalid", "Not a PNG file")
    chunks: list[tuple[bytes, bytes]] = []
    pos = len(PNG_SIGNATURE)
    seen_iend = False
    while pos < len(data):
        if pos + _CHUNK_OVERHEAD > len(data):
            raise PngError("png_invalid", "Truncated PNG chunk header")
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        chunk_type = data[pos + 4 : pos + 8]
        body_end = pos + 8 + length
        if body_end + 4 > len(data):
            raise PngError("png_invalid", "Truncated PNG chunk body")
        body = data[pos + 8 : body_end]
        (expected,) = struct.unpack(">I", data[body_end : body_end + 4])
        if _crc(chunk_type, body) != expected:
            raise PngError("png_crc_mismatch", "PNG chunk CRC mismatch")
        chunks.append((chunk_type, body))
        pos = body_end + 4
        if chunk_type == b"IEND":
            seen_iend = True
            break
    if not chunks or chunks[0][0] != b"IHDR" or not seen_iend:
        raise PngError("png_invalid", "PNG is missing IHDR or IEND")
    return chunks


def read_text_chunks(data: bytes) -> dict[str, str]:
    """Return tEXt chunks as {keyword: text}. The first chunk wins for a repeated keyword."""
    out: dict[str, str] = {}
    for chunk_type, body in _iter_chunks(data):
        if chunk_type != b"tEXt":
            continue
        keyword, sep, text = body.partition(b"\x00")
        if not sep:
            continue
        out.setdefault(keyword.decode("latin-1"), text.decode("latin-1"))
    return out


def write_text_chunks(png: bytes, texts: dict[str, str]) -> bytes:
    """Return `png` with the given tEXt chunks inserted before IEND.

    Existing tEXt chunks that share a keyword with `texts` are dropped; everything else is kept.
    """
    chunks = _iter_chunks(png)
    out = [PNG_SIGNATURE]
    for chunk_type, body in chunks[:-1]:
        if chunk_type == b"tEXt" and body.partition(b"\x00")[0].decode("latin-1") in texts:
            continue
        out.append(_make_chunk(chunk_type, body))
    for keyword, text in texts.items():
        out.append(_make_chunk(b"tEXt", keyword.encode("latin-1") + b"\x00" + text.encode("latin-1")))
    out.append(_make_chunk(b"IEND", b""))
    return b"".join(out)


def placeholder_png() -> bytes:
    """A tiny solid-color PNG used when a card has no avatar."""
    size = _PLACEHOLDER_SIZE
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    row = b"\x00" + _PLACEHOLDER_RGB * size
    idat = zlib.compress(row * size)
    return PNG_SIGNATURE + _make_chunk(b"IHDR", ihdr) + _make_chunk(b"IDAT", idat) + _make_chunk(b"IEND", b"")


_TEXT_CHUNK_TYPES = frozenset((b"tEXt", b"iTXt", b"zTXt"))


def strip_text_chunks(png: bytes) -> bytes:
    """Return `png` without tEXt/iTXt/zTXt chunks, so an avatar cannot carry the original card JSON."""
    out = [PNG_SIGNATURE]
    out.extend(_make_chunk(t, b) for t, b in _iter_chunks(png) if t not in _TEXT_CHUNK_TYPES)
    return b"".join(out)
