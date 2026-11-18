import { apiClient } from "@/lib/apiClient";
import { buildQuery } from "@/features/library/api";
import type { GalleryItem, GalleryParams, Page, TargetType } from "@/types/library";

export interface GalleryCursorParams extends GalleryParams {
  cursor?: string | undefined;
}

export const galleryApi = {
  list: (p: GalleryCursorParams = {}) =>
    apiClient.get<Page<GalleryItem>>(`/api/gallery${buildQuery(p)}`),
  favorites: () => apiClient.get<{ items: GalleryItem[] }>("/api/favorites"),
  addFavorite: (type: TargetType, itemId: string) =>
    apiClient.put<void>(`/api/favorites/${type}/${encodeURIComponent(itemId)}`),
  removeFavorite: (type: TargetType, itemId: string) =>
    apiClient.delete<void>(`/api/favorites/${type}/${encodeURIComponent(itemId)}`),
};
