import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ImportButton } from "@/features/io";
import { useDuplicateCharacter, useDuplicateWorld } from "@/features/library/hooks";
import { errorMessage, t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import type { GalleryItem, TargetType } from "@/types/library";
import { GalleryCard } from "./GalleryCard";
import { GalleryFilters, type GallerySort } from "./GalleryFilters";
import { useFavorites, useGallery } from "./hooks";
import { useOptimisticFavorite } from "./useOptimisticFavorite";

const SEARCH_DEBOUNCE_MS = 300; // typing pause before the query is sent
const MAX_TAG_CHIPS = 12; // chips derived from loaded items; keeps the row to ~2 lines
export const GRID_CLASS =
  "grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7";

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

function topTags(items: GalleryItem[]): string[] {
  const counts = new Map<string, number>();
  for (const item of items)
    for (const tag of item.tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, MAX_TAG_CHIPS)
    .map(([tag]) => tag);
}

export function GalleryView() {
  const [type, setType] = useState<TargetType>("character");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<GallerySort>("recent");
  const [tag, setTag] = useState("");
  const [addingKey, setAddingKey] = useState<string | null>(null);
  const q = useDebounced(search.trim(), SEARCH_DEBOUNCE_MS);

  const gallery = useGallery({ type, sort, q, tag });
  const favorites = useFavorites();
  const toggle = useOptimisticFavorite();
  const duplicateCharacter = useDuplicateCharacter();
  const duplicateWorld = useDuplicateWorld();

  const items = useMemo(() => gallery.data?.pages.flatMap((p) => p.items) ?? [], [gallery.data]);
  const tags = useMemo(() => topTags(items), [items]);
  const favoriteItems = favorites.data ?? [];

  const sentinel = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = gallery;
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasNextPage || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting) && !isFetchingNextPage) void fetchNextPage();
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  function onToggle(item: GalleryItem): void {
    toggle.mutate({ type: item.type, id: item.id, favorite: !item.is_favorite });
  }

  function onAdd(item: GalleryItem): void {
    const key = `${item.type}:${item.id}`;
    setAddingKey(key);
    const callbacks = {
      onSuccess: () => toast.success(t("gallery.added")),
      onError: (error: unknown) =>
        toast.error(errorMessage(error instanceof ApiError ? error.code : null)),
      onSettled: () => setAddingKey(null),
    };
    if (item.type === "character") duplicateCharacter.mutate(item.id, callbacks);
    else duplicateWorld.mutate(item.id, callbacks);
  }

  function renderCards(list: GalleryItem[]) {
    return list.map((item) => (
      <GalleryCard
        key={`${item.type}:${item.id}`}
        item={item}
        onToggleFavorite={onToggle}
        onAdd={onAdd}
        adding={addingKey === `${item.type}:${item.id}`}
      />
    ));
  }

  return (
    <div className="mx-auto flex w-full max-w-[110rem] flex-col gap-6 p-4 md:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{t("gallery.title")}</h1>
        <ImportButton />
      </header>

      {favoriteItems.length > 0 ? (
        <section aria-labelledby="gallery-favorites" className="flex flex-col gap-3">
          <h2 id="gallery-favorites" className="text-lg font-semibold">
            {t("gallery.favoritesSection")}
          </h2>
          <div className="flex gap-3 overflow-x-auto pb-2">
            {favoriteItems.map((item) => (
              <div key={`${item.type}:${item.id}`} className="w-36 shrink-0 sm:w-40">
                {renderCards([item])}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <GalleryFilters
        type={type}
        onTypeChange={(next) => {
          setType(next);
          setTag("");
        }}
        search={search}
        onSearchChange={setSearch}
        sort={sort}
        onSortChange={setSort}
        tags={tags}
        activeTag={tag}
        onTagChange={setTag}
      />

      {gallery.isPending ? (
        <p role="status" className="text-sm text-muted">
          {t("pages.loading")}
        </p>
      ) : null}
      {gallery.isError ? (
        <div role="alert" className="flex items-center gap-3 text-sm text-danger">
          {t("gallery.loadFailed")}
          <Button variant="outline" size="sm" onClick={() => void gallery.refetch()}>
            {t("common.retry")}
          </Button>
        </div>
      ) : null}
      {gallery.isSuccess && items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border bg-surface p-8 text-center text-sm text-muted">
          {t("gallery.empty")}
        </p>
      ) : null}

      {items.length > 0 ? <div className={GRID_CLASS}>{renderCards(items)}</div> : null}

      {hasNextPage ? (
        <div ref={sentinel} className="flex justify-center">
          <Button
            variant="outline"
            disabled={isFetchingNextPage}
            onClick={() => void fetchNextPage()}
          >
            {isFetchingNextPage ? t("gallery.loadingMore") : t("gallery.loadMore")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
