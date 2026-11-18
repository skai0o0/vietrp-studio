import { useId } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { useLorebooks } from "../hooks";
import { useFormState } from "./FormContext";

interface LorebookPickerProps {
  selected: readonly string[];
  onChange: (ids: string[]) => void;
}

/** Multi-select of the vault's lorebooks (checkbox list). */
export function LorebookPicker({ selected, onChange }: LorebookPickerProps) {
  const baseId = useId();
  const { readOnly } = useFormState();
  const query = useLorebooks();
  const books = query.data?.pages.flatMap((page) => page.items) ?? [];
  const knownIds = new Set(books.map((book) => book.id));
  const unknown = selected.filter((id) => !knownIds.has(id));

  function toggle(id: string, checked: boolean): void {
    onChange(checked ? [...selected, id] : selected.filter((item) => item !== id));
  }

  if (query.isPending)
    return <p className="text-sm text-muted">{t("library.lorebooks.loading")}</p>;
  if (query.isError) {
    return (
      <p role="alert" className="text-sm text-danger">
        {t("library.lorebooks.loadFailed")}
      </p>
    );
  }
  if (books.length === 0 && unknown.length === 0) {
    return <p className="text-sm text-muted">{t("library.lorebooks.none")}</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-1" aria-label={t("library.lorebooks.listLabel")}>
        {books.map((book) => (
          <li key={book.id}>
            <label
              htmlFor={`${baseId}-${book.id}`}
              className="flex min-h-10 cursor-pointer items-center gap-3 rounded-md px-2 hover:bg-surface-2"
            >
              <input
                id={`${baseId}-${book.id}`}
                type="checkbox"
                className="size-4 accent-[rgb(var(--accent))]"
                checked={selected.includes(book.id)}
                disabled={readOnly}
                onChange={(event) => toggle(book.id, event.target.checked)}
              />
              <span className="min-w-0 flex-1 truncate text-sm">{book.name}</span>
              <span className="shrink-0 text-xs text-muted">
                {t("library.lorebooks.entryCount", { count: book.entry_count })}
              </span>
            </label>
          </li>
        ))}
        {unknown.map((id) => (
          <li key={id} className="px-2 text-sm text-muted">
            {t("library.lorebooks.unknown", { id: id.slice(0, 8) })}
          </li>
        ))}
      </ul>
      {query.hasNextPage ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          {t("library.list.loadMore")}
        </Button>
      ) : null}
    </div>
  );
}
