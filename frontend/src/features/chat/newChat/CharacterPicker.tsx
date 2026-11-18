import { useState } from "react";
import { Link } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { useCharacters } from "@/features/library/hooks";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";

interface CharacterPickerProps {
  value: string | null;
  onChange: (id: string) => void;
}

export function CharacterPicker({ value, onChange }: CharacterPickerProps) {
  const [search, setSearch] = useState("");
  const query = useCharacters({ q: search.trim() });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section aria-labelledby="newchat-character" className="flex flex-col gap-2">
      <h2 id="newchat-character" className="text-sm font-semibold">
        {t("newChat.step.character")}
      </h2>
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
      <ul className="grid max-h-72 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
        {items.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              aria-pressed={value === c.id}
              onClick={() => onChange(c.id)}
              className={cn(
                "flex w-full flex-col rounded-md border p-3 text-left text-sm",
                value === c.id ? "border-accent bg-surface-2" : "border-border hover:bg-surface-2",
              )}
            >
              <span className="font-medium">{c.name}</span>
              <span className="line-clamp-1 text-xs text-muted">{c.tagline}</span>
              {c.needs_age ? (
                <span className="text-xs text-danger">{t("newChat.needsAge")}</span>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
      <Link to="/" className="text-sm text-accent underline">
        {t("newChat.fromGallery")}
      </Link>
    </section>
  );
}
