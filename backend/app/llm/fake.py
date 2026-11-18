"""`RecordedLLM`: replays recorded OpenRouter traffic so tests never touch the network.

It is an `httpx` transport, so the real client, streaming parser, Decisions/Extractions normalizers, retry logic and
usage accounting all run unchanged. Build services with `build_llm_services(settings, transport=llm.transport())`.

Fixture file format (`tests/fixtures/llm/*.json`; files without `"vietrp_fixture": 1` are plain response bodies
used by the P0 client tests and are ignored here):

    {
      "vietrp_fixture": 1,
      "match": {                        # every key is optional; all given keys must match
        "method": "POST",               # default: any
        "path": "/api/v1/chat/completions",
        "model": "deepseek/...",        # request body "model"
        "stream": true,                 # request body "stream" (missing counts as false)
        "contains": "Quán cà phê"       # substring of the request body as JSON text
      },
      "responses": [                    # answered in order; the last one repeats
        {"status": 200, "json": {...}}                       # JSON body
        {"status": 200, "sse": [{...chunk...}, ...]}         # streamed: each chunk becomes a `data:` line,
                                                             # then `data: [DONE]`
        {"status": 429, "headers": {"retry-after": "1"}, "json": {...}}   # errors work the same way
      ]
    }

The first fixture whose `match` fits wins. A request nobody matches raises `UnmatchedRequest`, which fails the test
loudly instead of returning a made-up answer. Fixtures must never contain API keys.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

FIXTURE_MARKER = "vietrp_fixture"
DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "llm"


class UnmatchedRequest(AssertionError):
    """No recorded fixture fits this request."""


@dataclass(slots=True)
class _Fixture:
    name: str
    match: dict[str, Any]
    responses: list[dict[str, Any]]
    served: int = 0

    def matches(self, request: httpx.Request, body: dict[str, Any], body_text: str) -> bool:
        m = self.match
        if "method" in m and request.method != str(m["method"]).upper():
            return False
        if "path" in m and request.url.path != m["path"]:
            return False
        if "model" in m and body.get("model") != m["model"]:
            return False
        if "stream" in m and bool(body.get("stream", False)) != bool(m["stream"]):
            return False
        return not ("contains" in m and str(m["contains"]) not in body_text)

    def next_response(self) -> dict[str, Any]:
        response = self.responses[min(self.served, len(self.responses) - 1)]
        self.served += 1
        return response


def _render(spec: dict[str, Any]) -> httpx.Response:
    status = int(spec.get("status", 200))
    headers = dict(spec.get("headers", {}))
    if "sse" in spec:
        lines = [f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in spec["sse"]]
        lines.append("data: [DONE]\n\n")
        headers.setdefault("content-type", "text/event-stream")
        return httpx.Response(status, headers=headers, content="".join(lines).encode("utf-8"))
    return httpx.Response(status, headers=headers, json=spec.get("json", {}))


class RecordedLLM:
    def __init__(self) -> None:
        self._fixtures: list[_Fixture] = []
        # Every request seen, for assertions (headers included, so tests can check what was sent).
        self.requests: list[httpx.Request] = []

    @classmethod
    def from_dir(cls, directory: Path | None = None, *, names: list[str] | None = None) -> RecordedLLM:
        """Load fixture files (all marked ones, or just `names`) from `directory`, in filename order."""
        llm = cls()
        folder = directory or DEFAULT_FIXTURE_DIR
        paths = [folder / n for n in names] if names else sorted(folder.glob("*.json"))
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get(FIXTURE_MARKER):
                llm.add(data["responses"], data.get("match"), name=path.name)
            elif names:
                raise ValueError(f"{path.name} is not a VietRP fixture (missing {FIXTURE_MARKER!r})")
        return llm

    def add(
        self, responses: list[dict[str, Any]], match: dict[str, Any] | None = None, *, name: str = "inline"
    ) -> None:
        if not responses:
            raise ValueError("a fixture needs at least one response")
        self._fixtures.append(_Fixture(name, dict(match or {}), responses))

    @property
    def fixture_names(self) -> list[str]:
        return [f.name for f in self._fixtures]

    def requests_to(self, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == path]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body_text = request.content.decode("utf-8", errors="replace") if request.content else ""
        try:
            parsed = json.loads(body_text) if body_text else {}
        except ValueError:
            parsed = {}
        body = parsed if isinstance(parsed, dict) else {}
        for fixture in self._fixtures:
            if fixture.matches(request, body, body_text):
                return _render(fixture.next_response())
        raise UnmatchedRequest(f"no recorded fixture for {request.method} {request.url.path} model={body.get('model')}")

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)


__all__ = ["DEFAULT_FIXTURE_DIR", "FIXTURE_MARKER", "RecordedLLM", "UnmatchedRequest"]
