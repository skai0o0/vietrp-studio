import { Heart, ImageOff, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { GalleryItem } from "@/types/library";

interface GalleryCardProps {
  item: GalleryItem;
  onToggleFavorite: (item: GalleryItem) => void;
  onAdd: (item: GalleryItem) => void;
  adding?: boolean;
}

export function detailPath(item: Pick<GalleryItem, "type" | "id">): string {
  const base = item.type === "character" ? "characters" : "worlds";
  return `/${base}/${encodeURIComponent(item.id)}`;
}

export function GalleryCard({ item, onToggleFavorite, onAdd, adding = false }: GalleryCardProps) {
  const favoriteLabel = t(item.is_favorite ? "gallery.unfavorite" : "gallery.favorite", {
    name: item.name,
  });
  return (
    <article className="group relative flex flex-col overflow-hidden rounded-lg border border-border bg-surface focus-within:border-accent hover:border-accent">
      <Link
        to={detailPath(item)}
        aria-label={t("gallery.open", { name: item.name })}
        className="flex flex-1 flex-col outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        <div className="relative aspect-[3/4] w-full bg-surface-2">
          {item.image_url ? (
            <img src={item.image_url} alt="" loading="lazy" className="size-full object-cover" />
          ) : (
            <div className="flex size-full items-center justify-center text-muted">
              <ImageOff className="size-8" aria-hidden />
            </div>
          )}
        </div>
        <div className="flex flex-col gap-1 p-3">
          <h3 className="line-clamp-1 text-sm font-semibold">{item.name}</h3>
          <p className="line-clamp-2 min-h-8 text-xs text-muted">{item.tagline}</p>
          <p className="line-clamp-1 text-xs text-muted">
            {item.is_owner ? t("gallery.mine") : t("gallery.byAuthor", { author: item.author })}
          </p>
        </div>
      </Link>

      <Button
        variant="ghost"
        size="sm"
        aria-pressed={item.is_favorite}
        aria-label={favoriteLabel}
        title={t("gallery.favoriteCount", { count: item.favorite_count })}
        onClick={() => onToggleFavorite(item)}
        className="absolute right-2 top-2 h-8 gap-1 bg-bg/80 px-2 text-xs text-fg"
      >
        <Heart aria-hidden className={cn(item.is_favorite && "fill-current text-accent-2")} />
        <span>{item.favorite_count}</span>
      </Button>

      {item.is_owner ? null : (
        <div className="px-3 pb-3">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={adding}
            onClick={() => onAdd(item)}
          >
            <Plus aria-hidden />
            {adding ? t("gallery.adding") : t("gallery.addToLibrary")}
          </Button>
        </div>
      )}
    </article>
  );
}
