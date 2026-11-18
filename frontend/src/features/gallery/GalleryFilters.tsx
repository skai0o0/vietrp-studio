import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { TargetType } from "@/types/library";

export type GallerySort = "recent" | "favorites";

interface GalleryFiltersProps {
  type: TargetType;
  onTypeChange: (type: TargetType) => void;
  search: string;
  onSearchChange: (value: string) => void;
  sort: GallerySort;
  onSortChange: (sort: GallerySort) => void;
  tags: string[];
  activeTag: string;
  onTagChange: (tag: string) => void;
}

const SORTS: readonly GallerySort[] = ["recent", "favorites"];

export function GalleryFilters(props: GalleryFiltersProps) {
  const { type, search, sort, tags, activeTag } = props;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={type} onValueChange={(value) => props.onTypeChange(value as TargetType)}>
          <TabsList aria-label={t("gallery.tabs.label")}>
            <TabsTrigger value="character">{t("gallery.tabs.character")}</TabsTrigger>
            <TabsTrigger value="world">{t("gallery.tabs.world")}</TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="relative min-w-48 flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <Input
            type="search"
            value={search}
            onChange={(event) => props.onSearchChange(event.target.value)}
            placeholder={t("gallery.searchPlaceholder")}
            aria-label={t("gallery.searchLabel")}
            className="pl-9"
          />
        </div>

        <div role="group" aria-label={t("gallery.sort.label")} className="flex gap-1">
          {SORTS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={sort === value}
              onClick={() => props.onSortChange(value)}
              className={cn(
                "h-10 rounded-md border border-border px-3 text-sm text-muted",
                sort === value && "border-accent bg-accent/15 text-fg",
              )}
            >
              {t(`gallery.sort.${value}`)}
            </button>
          ))}
        </div>
      </div>

      {tags.length > 0 || activeTag ? (
        <div role="group" aria-label={t("gallery.tags.label")} className="flex flex-wrap gap-2">
          {activeTag && !tags.includes(activeTag) ? (
            <TagChip tag={activeTag} active onClick={() => props.onTagChange("")} />
          ) : null}
          {tags.map((tag) => (
            <TagChip
              key={tag}
              tag={tag}
              active={tag === activeTag}
              onClick={() => props.onTagChange(tag === activeTag ? "" : tag)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

interface TagChipProps {
  tag: string;
  active: boolean;
  onClick: () => void;
}

function TagChip({ tag, active, onClick }: TagChipProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={active ? t("gallery.tags.clear", { tag }) : tag}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs text-muted",
        active && "border-accent bg-accent/15 text-fg",
      )}
    >
      {tag}
      {active ? <X className="size-3" aria-hidden /> : null}
    </button>
  );
}
