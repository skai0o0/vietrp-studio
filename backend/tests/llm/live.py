"""Opt-in marker for tests that hit the real OpenRouter API: `@live` runs only with `-m live` and VIETRP_LIVE=1."""

from __future__ import annotations

import os

import pytest

requires_live = pytest.mark.skipif(os.environ.get("VIETRP_LIVE") != "1", reason="set VIETRP_LIVE=1 to run live tests")
live = pytest.mark.live
