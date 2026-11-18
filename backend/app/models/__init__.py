"""SQLAlchemy models. Importing this package registers every table on `Base.metadata`."""

from app.models.base import Base
from app.models.chat import Chat, MemorySnapshot, Message, MessageVariant, UsageLog
from app.models.library import (
    Asset,
    Character,
    CreatorSession,
    Favorite,
    Lorebook,
    LorebookLink,
    LoreEntry,
    Persona,
    PromptPreset,
    World,
)
from app.models.vault import Secret, Vault

__all__ = [
    "Asset",
    "Base",
    "Character",
    "Chat",
    "CreatorSession",
    "Favorite",
    "LoreEntry",
    "Lorebook",
    "LorebookLink",
    "MemorySnapshot",
    "Message",
    "MessageVariant",
    "Persona",
    "PromptPreset",
    "Secret",
    "UsageLog",
    "Vault",
    "World",
]
