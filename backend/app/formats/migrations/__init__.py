"""Format migrators, keyed by (kind, from_version). Empty for spec 1.0."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.formats.common import CURRENT_SPEC_VERSION

Migrator = Callable[[dict[str, Any]], dict[str, Any]]

# A migrator takes data at `from_version` and returns data at the next version,
# with `spec_version` updated.
MIGRATORS: dict[tuple[str, str], Migrator] = {}


def migrate(
    kind: str,
    data: dict[str, Any],
    *,
    registry: dict[tuple[str, str], Migrator] | None = None,
) -> dict[str, Any]:
    """Upgrade `data` to the current spec version by chaining registered migrators."""
    migrators = MIGRATORS if registry is None else registry
    current = dict(data)
    seen: set[str] = set()
    while True:
        version = str(current.get("spec_version", CURRENT_SPEC_VERSION))
        if version == CURRENT_SPEC_VERSION:
            return current
        migrator = migrators.get((kind, version))
        if migrator is None or version in seen:
            raise ValueError(f"no migration path for {kind} spec_version {version}")
        seen.add(version)
        current = migrator(current)
