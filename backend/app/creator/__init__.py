"""Creator helpers: pool loading from disk and default card/world templates."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.formats.common import CURRENT_SPEC_VERSION

POOLS_DIR = Path(__file__).resolve().parent / "pools"

PoolData = dict[str, dict[str, list[str]]]


def _read_pool_file(path: Path) -> PoolData:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"pool file {path.name} must contain a JSON object")
    out: PoolData = {}
    for section_name, section_value in raw.items():
        if not isinstance(section_value, dict):
            continue
        section: dict[str, list[str]] = {}
        for key, items in section_value.items():
            if isinstance(items, list):
                section[str(key)] = [str(item) for item in items]
        out[str(section_name)] = section
    return out


@lru_cache(maxsize=4)
def _load_cached(path_str: str) -> PoolData:
    return _read_pool_file(Path(path_str))


def load_character_pools(pools_dir: Path | None = None) -> PoolData:
    """Load character creator pools from `character_pools.json`."""
    path = (pools_dir or POOLS_DIR) / "character_pools.json"
    return copy.deepcopy(_load_cached(str(path.resolve())))


def load_world_pools(pools_dir: Path | None = None) -> PoolData:
    """Load world creator pools from `world_pools.json`."""
    path = (pools_dir or POOLS_DIR) / "world_pools.json"
    return copy.deepcopy(_load_cached(str(path.resolve())))


def clear_pools_cache() -> None:
    """Clear the cached pool JSON payloads (useful when pool files change on disk)."""
    _load_cached.cache_clear()


def card_defaults() -> dict[str, Any]:
    """Minimal default structure for a `vietrp-card` payload."""
    return {
        "format": "vietrp-card",
        "spec_version": CURRENT_SPEC_VERSION,
        "name": "",
        "age": None,
        "is_fictional": True,
        "aliases": [],
        "tagline": "",
        "appearance": "",
        "personality": "",
        "backstory": "",
        "goals": "",
        "limits": [],
        "secrets": [],
        "speech": {"style": "", "catchphrases": [], "examples": []},
        "addressing": {"default": "", "user": "", "by_character": {}},
        "relationships": {"user": "", "by_character": {}},
        "greetings": [],
        "lorebook_ids": [],
        "extras": {},
        "tags": [],
    }


def world_defaults() -> dict[str, Any]:
    """Minimal default structure for a `vietrp-world` payload."""
    return {
        "format": "vietrp-world",
        "spec_version": CURRENT_SPEC_VERSION,
        "name": "",
        "rules": "",
        "tags": [],
        "lorebook_ids": [],
        "locations": [],
        "openings": [],
    }


__all__ = [
    "POOLS_DIR",
    "PoolData",
    "card_defaults",
    "clear_pools_cache",
    "load_character_pools",
    "load_world_pools",
    "world_defaults",
]
