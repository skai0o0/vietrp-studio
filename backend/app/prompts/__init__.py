"""Jinja2 loader for prompt templates under `app/prompts/` (one folder per agent, plus `_shared`)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROMPTS_DIR = Path(__file__).parent


@lru_cache
def _env() -> Environment:
    # autoescape is off on purpose: output is a model prompt, not HTML. StrictUndefined catches typos in variables.
    return Environment(  # noqa: S701
        loader=FileSystemLoader(PROMPTS_DIR),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )


def render_prompt(template: str, **variables: Any) -> str:
    """Render e.g. `_shared/card.j2`. User-authored text is passed as a variable, never as template source."""
    return _env().get_template(template).render(**variables).strip()
