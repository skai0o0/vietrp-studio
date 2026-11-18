import {
  CharactersList,
  LorebooksList,
  PersonasList,
  WorldsList,
} from "@/features/library/list/Lists";

export function LibraryCharactersPage() {
  return <CharactersList />;
}

export function LibraryWorldsPage() {
  return <WorldsList />;
}

export function LibraryLorebooksPage() {
  return <LorebooksList />;
}

export function LibraryPersonasPage() {
  return <PersonasList />;
}
