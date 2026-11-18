"""Jinja2 environment for the LLM layer's own (infrastructure) prompt templates."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache
def _env() -> Environment:
    # autoescape is off on purpose: output is a model prompt, not HTML.
    return Environment(  # noqa: S701
        loader=FileSystemLoader(TEMPLATE_DIR),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=False,
    )


def render(name: str, **variables: Any) -> str:
    return _env().get_template(name).render(**variables).strip()
