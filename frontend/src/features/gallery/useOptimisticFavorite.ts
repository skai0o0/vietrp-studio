import { useMutation, useQueryClient, type InfiniteData } from "@tanstack/react-query";
import type { GalleryItem, Page, TargetType } from "@/types/library";
import { galleryApi } from "./api";

interface FavoriteVars {
  type: TargetType;
  id: string;
  favorite: boolean;
}

type GalleryCache = InfiniteData<Page<GalleryItem>, string | undefined>;

function patchItem(item: GalleryItem, v: FavoriteVars): GalleryItem {
  if (item.type !== v.type || item.id !== v.id || item.is_favorite === v.favorite) return item;
  return {
    ...item,
    is_favorite: v.favorite,
    favorite_count: Math.max(0, item.favorite_count + (v.favorite ? 1 : -1)),
  };
}

/**
 * Favorite toggle that updates the gallery pages and the favorites list immediately,
 * rolls back on error, and revalidates when settled.
 */
export function useOptimisticFavorite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: FavoriteVars) =>
      v.favorite ? galleryApi.addFavorite(v.type, v.id) : galleryApi.removeFavorite(v.type, v.id),
    onMutate: async (v) => {
      await client.cancelQueries({ queryKey: ["gallery"] });
      await client.cancelQueries({ queryKey: ["favorites"] });
      const galleries = client.getQueriesData<GalleryCache>({ queryKey: ["gallery"] });
      const favorites = client.getQueryData<GalleryItem[]>(["favorites"]);

      let source: GalleryItem | undefined;
      for (const [key, data] of galleries) {
        if (!data) continue;
        client.setQueryData<GalleryCache>(key, {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            items: page.items.map((item) => {
              if (item.type === v.type && item.id === v.id) source = item;
              return patchItem(item, v);
            }),
          })),
        });
      }
      if (favorites) {
        if (v.favorite) {
          const known = favorites.some((i) => i.type === v.type && i.id === v.id);
          if (!known && source) {
            client.setQueryData<GalleryItem[]>(["favorites"], [patchItem(source, v), ...favorites]);
          }
        } else {
          client.setQueryData<GalleryItem[]>(
            ["favorites"],
            favorites.filter((i) => !(i.type === v.type && i.id === v.id)),
          );
        }
      }
      return { galleries, favorites };
    },
    onError: (_error, _v, context) => {
      if (!context) return;
      for (const [key, data] of context.galleries) client.setQueryData(key, data);
      client.setQueryData(["favorites"], context.favorites);
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["favorites"] });
      void client.invalidateQueries({ queryKey: ["gallery"] });
    },
  });
}
