import { BookOpen, Globe2, User, UserRound } from "lucide-react";
import { useMemo, useState } from "react";
import { ImportButton } from "@/features/io";
import { t } from "@/i18n";
import { useCharacters, useLorebooks, usePersonas, useWorlds } from "../hooks";
import { NEW_ID } from "./badges";
import type { LibraryItem } from "./ItemCard";
import { LibraryListLayout } from "./LibraryListLayout";
import { useDebounced } from "./useDebounced";

function uniqueTags(pages: { tags: string[] }[] | undefined): string[] {
  const set = new Set<string>();
  for (const item of pages ?? []) for (const tag of item.tags) set.add(tag);
  return [...set].sort((a, b) => a.localeCompare(b));
}

export function CharactersList() {
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");
  const q = useDebounced(search.trim());
  // The unfiltered query (shared cache) supplies the tag chips while a filter is active.
  const everything = useCharacters({});
  const query = useCharacters({ q, tag });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const tags = uniqueTags(everything.data?.pages.flatMap((page) => page.items));

  const cards: LibraryItem[] = items.map((c) => ({
    id: c.id,
    to: `/characters/${c.id}`,
    name: c.name,
    subtitle: c.tagline,
    imageUrl: c.avatar_url,
    visibility: c.visibility,
    needsAge: c.needs_age,
  }));

  return (
    <LibraryListLayout
      title={t("pages.library.characters.title")}
      newTo={`/characters/${NEW_ID}`}
      searchLabel={t("library.list.searchCharacters")}
      search={search}
      onSearch={setSearch}
      tags={tags}
      activeTag={tag}
      onTag={setTag}
      items={cards}
      FallbackIcon={User}
      isPending={query.isPending}
      isError={query.isError}
      onRetry={() => void query.refetch()}
      hasMore={Boolean(query.hasNextPage)}
      loadingMore={query.isFetchingNextPage}
      onLoadMore={() => void query.fetchNextPage()}
      emptyText={t("pages.library.characters.empty")}
      extraActions={<ImportButton />}
    />
  );
}

export function WorldsList() {
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");
  const q = useDebounced(search.trim());
  const everything = useWorlds({});
  const query = useWorlds({ q, tag });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const tags = uniqueTags(everything.data?.pages.flatMap((page) => page.items));

  const cards: LibraryItem[] = items.map((w) => ({
    id: w.id,
    to: `/worlds/${w.id}`,
    name: w.name,
    subtitle: w.tagline,
    imageUrl: w.cover_url,
    visibility: w.visibility,
  }));

  return (
    <LibraryListLayout
      title={t("pages.library.worlds.title")}
      newTo={`/worlds/${NEW_ID}`}
      searchLabel={t("library.list.searchWorlds")}
      search={search}
      onSearch={setSearch}
      tags={tags}
      activeTag={tag}
      onTag={setTag}
      items={cards}
      FallbackIcon={Globe2}
      isPending={query.isPending}
      isError={query.isError}
      onRetry={() => void query.refetch()}
      hasMore={Boolean(query.hasNextPage)}
      loadingMore={query.isFetchingNextPage}
      onLoadMore={() => void query.fetchNextPage()}
      emptyText={t("pages.library.worlds.empty")}
      extraActions={<ImportButton />}
    />
  );
}

export function LorebooksList() {
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const query = useLorebooks({ q });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];

  const cards: LibraryItem[] = items.map((b) => ({
    id: b.id,
    to: `/library/lorebooks/${b.id}`,
    name: b.name,
    subtitle: t("library.lorebooks.entryCount", { count: b.entry_count }),
    imageUrl: null,
    visibility: b.visibility,
  }));

  return (
    <LibraryListLayout
      title={t("pages.library.lorebooks.title")}
      newTo={`/library/lorebooks/${NEW_ID}`}
      searchLabel={t("library.list.searchLorebooks")}
      search={search}
      onSearch={setSearch}
      items={cards}
      FallbackIcon={BookOpen}
      isPending={query.isPending}
      isError={query.isError}
      onRetry={() => void query.refetch()}
      hasMore={Boolean(query.hasNextPage)}
      loadingMore={query.isFetchingNextPage}
      onLoadMore={() => void query.fetchNextPage()}
      emptyText={t("pages.library.lorebooks.empty")}
      extraActions={<ImportButton />}
    />
  );
}

export function PersonasList() {
  const [search, setSearch] = useState("");
  const query = usePersonas();
  const needle = search.trim().toLowerCase();

  // The personas endpoint has no search parameter, so the (small) list is filtered here.
  const cards = useMemo<LibraryItem[]>(
    () =>
      (query.data ?? [])
        .filter((p) => !needle || p.data.name.toLowerCase().includes(needle))
        .map((p) => ({
          id: p.id,
          to: `/library/personas/${p.id}`,
          name: p.data.name,
          subtitle: [
            p.data.age != null ? t("library.persona.ageYears", { age: p.data.age }) : "",
            p.data.gender ?? "",
          ]
            .filter(Boolean)
            .join(" · "),
          imageUrl: p.avatar_url,
        })),
    [query.data, needle],
  );

  return (
    <LibraryListLayout
      title={t("pages.library.personas.title")}
      newTo={`/library/personas/${NEW_ID}`}
      searchLabel={t("library.list.searchPersonas")}
      search={search}
      onSearch={setSearch}
      items={cards}
      FallbackIcon={UserRound}
      isPending={query.isPending}
      isError={query.isError}
      onRetry={() => void query.refetch()}
      hasMore={false}
      loadingMore={false}
      onLoadMore={() => undefined}
      emptyText={t("pages.library.personas.empty")}
    />
  );
}
