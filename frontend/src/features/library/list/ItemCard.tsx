import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import type { Visibility } from "@/types/library";
import { NeedsAgeBadge, VisibilityBadge } from "./badges";

export interface LibraryItem {
  id: string;
  to: string;
  name: string;
  subtitle: string;
  imageUrl: string | null;
  tags?: string[];
  visibility?: Visibility;
  needsAge?: boolean;
}

interface ItemCardProps {
  item: LibraryItem;
  FallbackIcon: LucideIcon;
}

export function ItemCard({ item, FallbackIcon }: ItemCardProps) {
  return (
    <li>
      <Link
        to={item.to}
        className="group flex h-full flex-col overflow-hidden rounded-lg border border-border bg-surface transition-colors hover:border-accent"
      >
        <div className="relative aspect-[4/3] w-full bg-surface-2">
          {item.imageUrl ? (
            <img src={item.imageUrl} alt="" loading="lazy" className="size-full object-cover" />
          ) : (
            <div className="flex size-full items-center justify-center text-muted">
              <FallbackIcon className="size-10" aria-hidden="true" />
            </div>
          )}
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5 p-3">
          <h2 className="truncate text-sm font-semibold">{item.name}</h2>
          {item.subtitle ? (
            <p className="line-clamp-2 text-xs text-muted">{item.subtitle}</p>
          ) : null}
          <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
            {item.needsAge ? <NeedsAgeBadge /> : null}
            {item.visibility ? <VisibilityBadge visibility={item.visibility} /> : null}
          </div>
        </div>
      </Link>
    </li>
  );
}
