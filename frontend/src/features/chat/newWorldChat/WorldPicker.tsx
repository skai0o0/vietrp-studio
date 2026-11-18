import { Check, Globe } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useWorlds } from "@/features/library/hooks";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";

interface WorldPickerProps {
  value: string | null;
  onChange: (id: string) => void;
}

export function WorldPicker({ value, onChange }: WorldPickerProps) {
  const [search, setSearch] = useState("");
  const query = useWorlds({ q: search.trim() });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section aria-labelledby="worldchat-world" className="flex flex-col gap-2">
      <h2 id="worldchat-world" className="text-sm font-semibold">
        {t("worldChat.step.world")}
      </h2>
      <Input
        type="search"
        aria-label={t("worldChat.searchWorld")}
        placeholder={t("worldChat.searchWorld")}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {query.isPending ? (
        <p role="status" className="text-sm text-muted">
          {t("newChat.loading")}
        </p>
      ) : null}
      {query.isSuccess && items.length === 0 ? (
        <p className="text-sm text-muted">{t("worldChat.worldsEmpty")}</p>
      ) : null}
      <ul className="grid max-h-72 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
        {items.map((w) => {
          const selected = value === w.id;
          return (
            <li key={w.id}>
              <button
                type="button"
                aria-pressed={selected}
                onClick={() => onChange(w.id)}
                className={cn(
                  "flex min-h-14 w-full items-center gap-3 rounded-md border p-3 text-left text-sm",
                  selected ? "border-accent bg-surface-2" : "border-border hover:bg-surface-2",
                )}
              >
                <div className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-surface text-muted">
                  {w.cover_url ? (
                    <img src={w.cover_url} alt="" className="size-full object-cover" />
                  ) : (
                    <Globe className="size-4" aria-hidden="true" />
                  )}
                </div>
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate font-medium">{w.name}</span>
                  {w.tagline ? (
                    <span className="line-clamp-1 text-xs text-muted">{w.tagline}</span>
                  ) : null}
                </div>
                {selected ? (
                  <Check className="size-4 shrink-0 text-accent" aria-hidden="true" />
                ) : null}
              </button>
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
            {t("worldChat.loadMoreWorlds")}
          </Button>
        </div>
      ) : null}
      <Link to="/" className="w-fit text-sm text-accent underline">
        {t("worldChat.worldsFromGallery")}
      </Link>
    </section>
  );
}
