import { Plus, Search } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { ItemCard, type LibraryItem } from "./ItemCard";

const LIBRARY_TABS = [
  { to: "/library/characters", labelKey: "pages.library.characters.title" },
  { to: "/library/worlds", labelKey: "pages.library.worlds.title" },
  { to: "/library/lorebooks", labelKey: "pages.library.lorebooks.title" },
  { to: "/library/personas", labelKey: "pages.library.personas.title" },
] as const;

interface LibraryListLayoutProps {
  title: string;
  newTo: string;
  searchLabel: string;
  search: string;
  onSearch: (value: string) => void;
  /** Tag chips; omit for kinds without tags. */
  tags?: string[];
  activeTag?: string;
  onTag?: (tag: string) => void;
  items: LibraryItem[];
  FallbackIcon: LucideIcon;
  isPending: boolean;
  isError: boolean;
  onRetry: () => void;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  emptyText: string;
  /** Rendered next to "Tạo mới" (the import button). */
  extraActions?: ReactNode;
}

export function LibraryListLayout(props: LibraryListLayoutProps) {
  const { title, newTo, searchLabel, search, onSearch, tags = [], activeTag = "", onTag } = props;
  const filtering = search.trim() !== "" || activeTag !== "";

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 p-4 md:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{title}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {props.extraActions}
          <Button asChild>
            <Link to={newTo}>
              <Plus aria-hidden="true" />
              {t("library.actions.create")}
            </Link>
          </Button>
        </div>
      </header>

      <nav
        aria-label={t("library.list.navLabel")}
        className="inline-flex w-fit max-w-full flex-wrap items-center gap-1 rounded-md border border-border bg-surface p-1"
      >
        {LIBRARY_TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                "inline-flex min-h-9 items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
                isActive ? "bg-accent/15 text-fg" : "text-muted hover:text-fg",
              )
            }
          >
            {t(tab.labelKey)}
          </NavLink>
        ))}
      </nav>

      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
          aria-hidden="true"
        />
        <Input
          type="search"
          value={search}
          aria-label={searchLabel}
          placeholder={searchLabel}
          className="pl-9"
          onChange={(event) => onSearch(event.target.value)}
        />
      </div>

      {tags.length > 0 && onTag ? (
        <ul className="flex flex-wrap gap-1.5" aria-label={t("library.list.tagFilter")}>
          {tags.map((tag) => {
            const active = tag === activeTag;
            return (
              <li key={tag}>
                <button
                  type="button"
                  aria-pressed={active}
                  className={cn(
                    "rounded-sm border px-2 py-1 text-xs",
                    active
                      ? "border-accent bg-accent text-accent-fg"
                      : "border-border bg-surface text-muted hover:text-fg",
                  )}
                  onClick={() => onTag(active ? "" : tag)}
                >
                  {tag}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      {props.isPending ? (
        <p role="status" className="text-sm text-muted">
          {t("pages.loading")}
        </p>
      ) : props.isError ? (
        <div role="alert" className="flex flex-col items-start gap-2 text-sm">
          <p className="text-danger">{t("library.list.loadFailed")}</p>
          <Button variant="outline" size="sm" onClick={props.onRetry}>
            {t("common.retry")}
          </Button>
        </div>
      ) : props.items.length === 0 ? (
        <section className="flex min-h-48 flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-border bg-surface p-8 text-center">
          <p className="max-w-md text-sm text-muted">
            {filtering ? t("library.list.noResults") : props.emptyText}
          </p>
          {filtering ? null : (
            <Button asChild>
              <Link to={newTo}>
                <Plus aria-hidden="true" />
                {t("library.actions.create")}
              </Link>
            </Button>
          )}
        </section>
      ) : (
        <>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {props.items.map((item) => (
              <ItemCard key={item.id} item={item} FallbackIcon={props.FallbackIcon} />
            ))}
          </ul>
          {props.hasMore ? (
            <Button
              variant="outline"
              className="self-center"
              disabled={props.loadingMore}
              onClick={props.onLoadMore}
            >
              {t("library.list.loadMore")}
            </Button>
          ) : null}
        </>
      )}
    </div>
  );
}
