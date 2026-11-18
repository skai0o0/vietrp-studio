"""Chat command parser (architecture section 8): `/cmd`, `/force`, `/time`, `/move`, and NPC commands.

Unknown slash text (for example "/shrug" inside roleplay) is an ordinary message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CommandKind = Literal[
    "plain",
    "cmd",
    "force",
    "time",
    "move",
    "addnpc",
    "removenpc",
    "listnpc",
    "clearnpc",
    "unsupported",
]

# Retained as an empty set for callers inspecting commands not yet implemented.
UNSUPPORTED_COMMANDS: frozenset[str] = frozenset()

MAX_NPC_AGE = 10000

_COMMAND = re.compile(r"^/([A-Za-z]+)(?:\s+(.*))?$", re.DOTALL)
_FORCE_TARGET = re.compile(r"^@(\S+)(?:\s+(.*))?$", re.DOTALL)
_BRACKETED = re.compile(r"^\[(.*?)\]\s*(.*)$", re.DOTALL)
# Require whitespace on at least one side of `-` so hyphenated names like `Jean-Luc` stay intact.
_NPC_SPLIT = re.compile(r"\s+-\s*|\s*-\s+")
_NPC_AGE = re.compile(r"^(.*?)\s*\(\s*(\d{1,5})\s*(?:tuổi)?\s*\)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedInput:
    kind: CommandKind
    # What is stored as the player's message (may be empty for pure instructions or state commands).
    message: str
    # `/cmd` only: a one-turn instruction for the Orchestrator/Writer.
    instruction: str = ""
    # `/force` only: the name or id after "@".
    force_target: str = ""
    # Command name without the slash when `kind` is a command (or `unsupported`).
    command_name: str = ""
    # `/time` only: the new time label.
    time_text: str = ""
    # `/move` only: location id or name.
    move_target: str = ""
    # `/addnpc` and `/removenpc`: NPC display name.
    npc_name: str = ""
    # `/addnpc`: optional short description after `-`.
    npc_description: str = ""
    # `/addnpc`: optional age in parentheses; None keeps unknown-age NPCs protected by safety.py.
    npc_age: int | None = None


def parse_input(text: str) -> ParsedInput:
    """Parse one chat input.

    `/cmd [instruction] message` uses the bracket form; without brackets the first line is the instruction
    and the remaining lines are the message.
    """
    stripped = text.strip()
    match = _COMMAND.match(stripped)
    if match is None:
        return ParsedInput(kind="plain", message=text)
    name = match.group(1).lower()
    rest = (match.group(2) or "").strip()
    if name == "cmd":
        return _parse_cmd(rest)
    if name == "force":
        return _parse_force(rest, text)
    if name == "time":
        return ParsedInput(kind="time", message="", command_name="time", time_text=rest)
    if name == "move":
        return ParsedInput(kind="move", message="", command_name="move", move_target=rest)
    if name == "addnpc":
        return _parse_addnpc(rest)
    if name == "removenpc":
        return ParsedInput(kind="removenpc", message="", command_name="removenpc", npc_name=rest)
    if name == "listnpc":
        return ParsedInput(kind="listnpc", message="", command_name="listnpc")
    if name == "clearnpc":
        return ParsedInput(kind="clearnpc", message="", command_name="clearnpc")
    if name in UNSUPPORTED_COMMANDS:
        return ParsedInput(kind="unsupported", message="", instruction=rest, command_name=name)
    return ParsedInput(kind="plain", message=text)


def _parse_cmd(rest: str) -> ParsedInput:
    bracket = _BRACKETED.match(rest)
    if bracket is not None:
        return ParsedInput(kind="cmd", message=bracket.group(2).strip(), instruction=bracket.group(1).strip())
    first, _, remainder = rest.partition("\n")
    return ParsedInput(kind="cmd", message=remainder.strip(), instruction=first.strip())


def _parse_force(rest: str, original: str) -> ParsedInput:
    match = _FORCE_TARGET.match(rest)
    if match is None:
        # "/force" without a target: treat as plain text rather than failing the turn.
        return ParsedInput(kind="plain", message=original)
    return ParsedInput(kind="force", message=(match.group(2) or "").strip(), force_target=match.group(1))


def _parse_addnpc(rest: str) -> ParsedInput:
    if not rest:
        return ParsedInput(kind="addnpc", message="", command_name="addnpc")
    parts = _NPC_SPLIT.split(rest, maxsplit=1)
    raw_name = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else ""
    age: int | None = None
    npc_name = raw_name
    age_match = _NPC_AGE.match(raw_name)
    if age_match is not None:
        parsed_age = int(age_match.group(2))
        if parsed_age <= MAX_NPC_AGE:
            npc_name = age_match.group(1).strip()
            age = parsed_age
    return ParsedInput(
        kind="addnpc",
        message="",
        command_name="addnpc",
        npc_name=npc_name,
        npc_description=desc,
        npc_age=age,
    )
