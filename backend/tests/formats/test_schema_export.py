from __future__ import annotations

import json
from pathlib import Path

from app.formats.export_schema import SCHEMAS, export_schemas


def test_schema_export_is_deterministic(tmp_path: Path) -> None:
    first = export_schemas(tmp_path / "a")
    second = export_schemas(tmp_path / "b")
    assert [p.name for p in first] == list(SCHEMAS)
    for a, b in zip(first, second, strict=True):
        assert a.read_bytes() == b.read_bytes()
        assert json.loads(a.read_text(encoding="utf-8"))["type"] == "object"
