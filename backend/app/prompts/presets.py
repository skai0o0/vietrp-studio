"""Default preset loading and layer overrides.

A preset replaces text layers of the prompt. The safety rule is not a preset layer: it is injected by
`pipeline/safety.py` after presets, so a preset cannot override or remove it.
User-authored layer text is plain text with `{{char}}` / `{{user}}` placeholders; it is never run as a template.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from app.prompts import render_prompt

# Layers a user preset may override; any other key is ignored.
OVERRIDABLE_LAYERS = ("system", "nsfw")


@dataclass(frozen=True, slots=True)
class PresetLayers:
    """Resolved preset text. `None` means "use the default template" for that layer."""

    system: str | None = None
    nsfw: str | None = None


def resolve_preset(overrides: Mapping[str, str] | None) -> PresetLayers:
    """Build layers from a user's stored preset (`{"system": "...", "nsfw": "..."}`); blanks fall back to defaults."""
    layers = PresetLayers()
    for key, value in (overrides or {}).items():
        if key in OVERRIDABLE_LAYERS and isinstance(value, str) and value.strip():
            layers = replace(layers, **{key: value.strip()})
    return layers


def substitute_placeholders(text: str, *, char: str, user: str) -> str:
    return text.replace("{{char}}", char).replace("{{user}}", user)


def system_text(preset: PresetLayers, *, char: str, user: str) -> str:
    if preset.system is not None:
        return substitute_placeholders(preset.system, char=char, user=user)
    return render_prompt("_shared/system.j2", char=char, user=user)


def nsfw_text(preset: PresetLayers, *, char: str, user: str) -> str:
    if preset.nsfw is not None:
        return substitute_placeholders(preset.nsfw, char=char, user=user)
    return render_prompt("_shared/nsfw.j2")
