import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n";
import { useFormState } from "./FormContext";
import { IconButton } from "./IconButton";

let rowCounter = 0;
const newRowId = (): number => ++rowCounter;

interface Row {
  rid: number;
  key: string;
  value: string;
}

interface KeyValueEditorProps {
  label: string;
  value: Readonly<Record<string, string>>;
  onChange: (value: Record<string, string>) => void;
  /** Path of the map inside `data`; an entry is looked up at `${path}.${key}`. */
  path: string;
  keyLabel: string;
  valueLabel: string;
  addLabel: string;
  hint?: string;
}

function toObject(rows: readonly Row[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (key) out[key] = row.value;
  }
  return out;
}

/**
 * Editable key/value map (extras, per-character addressing). Rows are kept locally so a half-typed
 * or duplicate key does not drop data; only rows with a key are emitted. Remount to reset.
 */
export function KeyValueEditor(props: KeyValueEditorProps) {
  const { label, value, onChange, path, keyLabel, valueLabel, addLabel, hint } = props;
  const { readOnly, errors } = useFormState();
  const [rows, setRows] = useState<Row[]>(() =>
    Object.entries(value).map(([key, text]) => ({ rid: newRowId(), key, value: text })),
  );

  function commit(next: Row[]): void {
    setRows(next);
    onChange(toObject(next));
  }

  function update(rid: number, patch: Partial<Row>): void {
    commit(rows.map((row) => (row.rid === rid ? { ...row, ...patch } : row)));
  }

  const duplicates = new Set(
    rows.map((row) => row.key.trim()).filter((key, i, all) => key && all.indexOf(key) !== i),
  );

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-sm font-medium leading-none">{label}</p>
      {hint ? <p className="text-xs text-muted">{hint}</p> : null}
      {rows.length > 0 ? (
        <ul className="flex flex-col gap-3" aria-label={label}>
          {rows.map((row, index) => {
            const error = errors[`${path}.${row.key.trim()}`];
            const duplicate = duplicates.has(row.key.trim());
            return (
              <li key={row.rid} className="flex flex-col gap-1">
                <div className="flex items-start gap-1.5">
                  <div className="grid min-w-0 flex-1 gap-1.5 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
                    <Input
                      aria-label={t("library.kv.keyAria", { label: keyLabel, position: index + 1 })}
                      aria-invalid={error || duplicate ? true : undefined}
                      value={row.key}
                      readOnly={readOnly}
                      placeholder={keyLabel}
                      onChange={(event) => update(row.rid, { key: event.target.value })}
                    />
                    <Input
                      aria-label={t("library.kv.valueAria", {
                        label: valueLabel,
                        position: index + 1,
                      })}
                      value={row.value}
                      readOnly={readOnly}
                      placeholder={valueLabel}
                      onChange={(event) => update(row.rid, { value: event.target.value })}
                    />
                  </div>
                  {readOnly ? null : (
                    <IconButton
                      icon={Trash2}
                      label={t("library.kv.remove", { position: index + 1 })}
                      onClick={() => commit(rows.filter((r) => r.rid !== row.rid))}
                    />
                  )}
                </div>
                {error ? (
                  <p role="alert" className="text-xs text-danger">
                    {error}
                  </p>
                ) : null}
                {duplicate ? (
                  <p role="alert" className="text-xs text-danger">
                    {t("library.kv.duplicateKey")}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : readOnly ? (
        <p className="text-sm text-muted">{t("library.list.none")}</p>
      ) : null}
      {readOnly ? null : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => setRows([...rows, { rid: newRowId(), key: "", value: "" }])}
        >
          <Plus aria-hidden="true" />
          {addLabel}
        </Button>
      )}
    </div>
  );
}
