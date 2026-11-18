import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type { GalleryParams } from "@/types/library";
import { galleryApi } from "./api";

const DEFAULT_PAGE_SIZE = 30; // WP-I contract: limit default 30

export function useGallery(params: GalleryParams = {}) {
  return useInfiniteQuery({
    queryKey: ["gallery", params],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      galleryApi.list({ limit: DEFAULT_PAGE_SIZE, ...params, cursor: pageParam }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useFavorites() {
  return useQuery({
    queryKey: ["favorites"],
    queryFn: async () => (await galleryApi.favorites()).items,
  });
}
