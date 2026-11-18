import type { Addressing, Relationships, Speech } from "@/types/generated/vietrp-card";
import type { VietrpCard } from "@/types/library";

/** A card with every optional field filled in, so the form never handles `undefined`. */
export interface CardDraft {
  name: string;
  age: number | null;
  aliases: string[];
  tagline: string;
  tags: string[];
  appearance: string;
  personality: string;
  backstory: string;
  goals: string;
  limits: string[];
  secrets: { id: string; content: string; reveal_when: string }[];
  speech: Required<Speech>;
  addressing: Required<Addressing>;
  relationships: Required<Relationships>;
  greetings: string[];
  lorebook_ids: string[];
  extras: Record<string, string>;
}

export function emptyCardDraft(): CardDraft {
  return {
    name: "",
    age: null,
    aliases: [],
    tagline: "",
    tags: [],
    appearance: "",
    personality: "",
    backstory: "",
    goals: "",
    limits: [],
    secrets: [],
    speech: { style: "", catchphrases: [], examples: [] },
    addressing: { default: "", user: "", by_character: {} },
    relationships: { user: "", by_character: {} },
    greetings: [],
    lorebook_ids: [],
    extras: {},
  };
}

export function cardToDraft(card: VietrpCard): CardDraft {
  const empty = emptyCardDraft();
  return {
    name: card.name,
    age: card.age ?? null,
    aliases: [...(card.aliases ?? [])],
    tagline: card.tagline ?? "",
    tags: [...(card.tags ?? [])],
    appearance: card.appearance ?? "",
    personality: card.personality ?? "",
    backstory: card.backstory ?? "",
    goals: card.goals ?? "",
    limits: [...(card.limits ?? [])],
    secrets: (card.secrets ?? []).map((s) => ({
      id: s.id,
      content: s.content,
      reveal_when: s.reveal_when ?? "",
    })),
    speech: {
      style: card.speech?.style ?? "",
      catchphrases: [...(card.speech?.catchphrases ?? [])],
      examples: [...(card.speech?.examples ?? [])],
    },
    addressing: {
      default: card.addressing?.default ?? "",
      user: card.addressing?.user ?? "",
      by_character: { ...(card.addressing?.by_character ?? empty.addressing.by_character) },
    },
    relationships: {
      user: card.relationships?.user ?? "",
      by_character: { ...(card.relationships?.by_character ?? empty.relationships.by_character) },
    },
    greetings: [...(card.greetings ?? [])],
    lorebook_ids: [...(card.lorebook_ids ?? [])],
    extras: { ...(card.extras ?? {}) },
  };
}

/** Builds the payload for the API. `is_fictional` is always true (AGENTS.md section 2.1). */
export function draftToCard(draft: CardDraft): VietrpCard {
  return {
    format: "vietrp-card",
    spec_version: "1.0",
    is_fictional: true,
    ...draft,
    // The generated type caps tags with a long tuple union; the server enforces the limit.
    tags: draft.tags as VietrpCard["tags"],
  };
}
