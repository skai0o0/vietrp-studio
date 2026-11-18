import { useParams } from "react-router-dom";
import { CharacterEditor } from "@/features/library/character/CharacterEditor";
import { LorebookEditor } from "@/features/library/lorebook/LorebookEditor";
import { PersonaEditor } from "@/features/library/persona/PersonaEditor";
import { WorldEditor } from "@/features/library/world/WorldEditor";
import { NEW_ID } from "@/features/library/list/badges";

export function CharacterDetailPage() {
  const { id = NEW_ID } = useParams();
  return <CharacterEditor id={id} />;
}

export function WorldDetailPage() {
  const { id = NEW_ID } = useParams();
  return <WorldEditor id={id} />;
}

export function PersonaDetailPage() {
  const { id = NEW_ID } = useParams();
  return <PersonaEditor id={id} />;
}

export function LorebookDetailPage() {
  const { id = NEW_ID } = useParams();
  return <LorebookEditor id={id} />;
}
