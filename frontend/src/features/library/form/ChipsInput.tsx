import { X } from "lucide-react";
import { useId, useState, type KeyboardEvent } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import { useFieldMeta } from "./FormContext";

interface ChipsInputProps {
  label: string;
  values: readonly string[];
  onChange: (values: string[]) => void;
  path?: string;
  hint?: string;
  placeholder?: string;
  /** Lowercases entries as they are typed (tags). */
  lowercase?: boolean;
}

/** Free-text chips: Enter or comma adds, Backspace on an empty input removes the last chip. */
export function ChipsInput(props: ChipsInputProps) {
  const { label, values, onChange, path, hint, placeholder, lowercase = false } = props;
  const id = useId();
  const meta = useFieldMeta(path);
  const [draft, setDraft] = useState("");

  function commit(raw: string): void {
    const cleaned = (lowercase ? raw.toLowerCase() : raw).trim();
    setDraft("");
    if (!cleaned || values.includes(cleaned)) return;
    onChange([...values, cleaned]);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit(draft);
    } else if (event.key === "Backspace" && draft === "" && values.length > 0) {
      onChange(values.slice(0, -1));
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {values.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label={label}>
          {values.map((value) => (
            <li
              key={value}
              className="inline-flex items-center gap-1 rounded-sm border border-border bg-surface-2 py-0.5 pl-2 pr-1 text-xs"
            >
              <span className="break-all">{value}</span>
              {meta.readOnly ? null : (
                <button
                  type="button"
                  aria-label={t("library.chips.remove", { value })}
                  className="rounded-sm p-0.5 text-muted hover:text-fg"
                  onClick={() => onChange(values.filter((item) => item !== value))}
                >
                  <X className="size-3" aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      {meta.readOnly ? null : (
        <Input
          id={id}
          value={draft}
          placeholder={placeholder ?? t("library.chips.placeholder")}
          aria-invalid={meta.error ? true : undefined}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => commit(draft)}
        />
      )}
      {hint ? <p className="text-xs text-muted">{hint}</p> : null}
      {meta.error ? (
        <p role="alert" className="text-xs text-danger">
          {meta.error}
        </p>
      ) : null}
    </div>
  );
}
