import { Check } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCharacters } from "@/features/library/hooks";
import { NeedsAgeBadge } from "@/features/library/list/badges";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { CharacterSummary } from "@/types/library";

type CastCandidate = CharacterSummary & {
  age?: number | null;
  data?: { age?: number | null };
};

export function isCharacterMissingAge(candidate: CastCandidate): boolean {
  if (candidate.needs_age) return true;
  if ("age" in candidate && candidate.age === null) return true;
  if (candidate.data && candidate.data.age === null) return true;
  return false;
}

interface CastPickerProps {
  selectedIds: readonly string[];
  onToggle: (id: string) => void;
}

export function CastPicker({ selectedIds, onToggle }: CastPickerProps) {
  const [search, setSearch] = useState("");
  const query = useCharacters({ q: search.trim() });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const selectedSet = new Set(selectedIds);

  return (
    <section aria-labelledby="worldchat-cast" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="worldchat-cast" className="text-sm font-semibold">
          {t("worldChat.step.cast")}
        </h2>
        <span className="text-xs text-muted">
          {t("worldChat.castSelectedCount", { count: selectedIds.length })}
        </span>
      </div>
      <p className="text-xs text-muted">{t("worldChat.castHint")}</p>
      <Input
        type="search"
        aria-label={t("newChat.searchCharacter")}
        placeholder={t("newChat.searchCharacter")}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {query.isPending ? (
        <p role="status" className="text-sm text-muted">
          {t("newChat.loading")}
        </p>
      ) : null}
      {query.isSuccess && items.length === 0 ? (
        <p className="text-sm text-muted">{t("newChat.charactersEmpty")}</p>
      ) : null}
      <ul className="grid max-h-80 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
        {items.map((c) => {
          const blocked = isCharacterMissingAge(c);
          const selected = selectedSet.has(c.id);
          return (
            <li
              key={c.id}
              className={cn(
                "flex flex-col gap-2 rounded-md border p-3",
                blocked
                  ? "border-danger/60 bg-surface"
                  : selected
                    ? "border-accent bg-surface-2"
                    : "border-border bg-surface",
              )}
            >
              <button
                type="button"
                role="checkbox"
                aria-checked={selected}
                disabled={blocked}
                onClick={() => onToggle(c.id)}
                className="flex min-h-11 w-full items-center gap-3 text-left text-sm disabled:cursor-not-allowed disabled:opacity-65"
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-sm border",
                    selected ? "border-accent bg-accent text-accent-fg" : "border-border bg-bg",
                  )}
                >
                  {selected ? <Check className="size-3.5" /> : null}
                </span>
                <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-surface-2 text-xs text-muted">
                  {c.avatar_url ? (
                    <img src={c.avatar_url} alt="" className="size-full object-cover" />
                  ) : (
                    <span aria-hidden="true">{c.name.slice(0, 1)}</span>
                  )}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate font-medium">{c.name}</span>
                  {c.tagline ? (
                    <span className="line-clamp-1 text-xs text-muted">{c.tagline}</span>
                  ) : null}
                </span>
              </button>
              {blocked ? (
                <div
                  data-testid={`needs-age-block-${c.id}`}
                  role="status"
                  className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2 text-xs"
                >
                  <div className="flex items-center gap-1.5">
                    <NeedsAgeBadge />
                    <span className="text-danger">{t("worldChat.castNeedsAgeBlocked")}</span>
                  </div>
                  <Link className="font-medium text-accent underline" to={`/characters/${c.id}`}>
                    {t("newChat.fixInEditor")}
                  </Link>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
      {query.hasNextPage ? (
        <div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={query.isFetchingNextPage}
            onClick={() => void query.fetchNextPage()}
          >
            {t("worldChat.loadMoreCharacters")}
          </Button>
        </div>
      ) : null}
      <Link to="/" className="w-fit text-sm text-accent underline">
        {t("newChat.fromGallery")}
      </Link>
    </section>
  );
}
