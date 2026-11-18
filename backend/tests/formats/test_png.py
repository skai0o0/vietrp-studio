from __future__ import annotations

import struct

import pytest

from app.formats.png import (
    MAX_PNG_BYTES,
    PngError,
    placeholder_png,
    read_text_chunks,
    write_text_chunks,
)


def test_write_then_read_text_chunks() -> None:
    png = write_text_chunks(placeholder_png(), {"chara": "YWJj", "ccv3": "ZGVm"})
    assert read_text_chunks(png) == {"chara": "YWJj", "ccv3": "ZGVm"}


def test_write_replaces_same_keyword() -> None:
    first = write_text_chunks(placeholder_png(), {"chara": "one"})
    second = write_text_chunks(first, {"chara": "two"})
    assert read_text_chunks(second) == {"chara": "two"}


def test_rejects_non_png() -> None:
    with pytest.raises(PngError) as exc:
        read_text_chunks(b"not a png")
    assert exc.value.code == "png_invalid"


def test_rejects_corrupt_crc() -> None:
    png = bytearray(write_text_chunks(placeholder_png(), {"chara": "abc"}))
    idx = bytes(png).index(b"tEXt")
    png[idx + 6] ^= 0xFF  # flip a byte inside the chunk body
    with pytest.raises(PngError) as exc:
        read_text_chunks(bytes(png))
    assert exc.value.code == "png_crc_mismatch"


def test_rejects_truncated() -> None:
    png = placeholder_png()
    with pytest.raises(PngError):
        read_text_chunks(png[:-5])


def test_rejects_oversized() -> None:
    with pytest.raises(PngError) as exc:
        read_text_chunks(b"\x89PNG\r\n\x1a\n" + b"\x00" * MAX_PNG_BYTES)
    assert exc.value.code == "file_too_large"


def test_placeholder_is_valid_png() -> None:
    png = placeholder_png()
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (8, 8)
    assert read_text_chunks(png) == {}


def test_strip_text_chunks_removes_all_text_kinds() -> None:
    from app.formats.png import _iter_chunks, _make_chunk, strip_text_chunks

    base = write_text_chunks(placeholder_png(), {"chara": "YWJj"})
    chunks = _iter_chunks(base)
    extra = [_make_chunk(b"iTXt", b"k\x00\x00\x00\x00\x00v"), _make_chunk(b"zTXt", b"k\x00\x00x")]
    body = b"".join(_make_chunk(t, b) for t, b in chunks[:-1]) + b"".join(extra) + _make_chunk(b"IEND", b"")
    dirty = b"\x89PNG\r\n\x1a\n" + body
    clean = strip_text_chunks(dirty)
    kinds = [t for t, _ in _iter_chunks(clean)]
    assert not {b"tEXt", b"iTXt", b"zTXt"} & set(kinds)
    assert kinds[0] == b"IHDR" and kinds[-1] == b"IEND" and b"IDAT" in kinds
    assert read_text_chunks(clean) == {}
