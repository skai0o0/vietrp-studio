import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { moveItem, removeAt, replaceAt } from "../lib/arrays";
import { useFieldMeta } from "./FormContext";
import { textareaClass } from "./fields";
import { IconButton } from "./IconButton";

interface StringListEditorProps {
  label: string;
  items: readonly string[];
  onChange: (items: string[]) => void;
  /** Path of the list inside `data`; item `i` is looked up at `${path}.${i}`. */
  path: string;
  addLabel: string;
  /** Builds the accessible name of an item from its 1-based position. */
  itemLabel: (position: number) => string;
  hint?: string;
  multiline?: boolean;
  rows?: number;
}

interface RowProps {
  id: string;
  path: string;
  value: string;
  position: number;
  total: number;
  itemLabel: string;
  multiline: boolean;
  rows: number;
  onChange: (value: string) => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}

function Row(props: RowProps) {
  const { id, path, value, position, total, itemLabel, multiline, rows } = props;
  const meta = useFieldMeta(path);
  const describedBy = meta.error ? `${id}-error` : undefined;
  return (
    <li className="flex flex-col gap-1.5">
      <div className="flex items-start gap-1.5">
        <div className="min-w-0 flex-1">
          {multiline ? (
            <textarea
              id={id}
              aria-label={itemLabel}
              aria-invalid={meta.error ? true : undefined}
              aria-describedby={describedBy}
              value={value}
              rows={rows}
              readOnly={meta.readOnly}
              className={cn(textareaClass, "resize-y")}
              onChange={(event) => props.onChange(event.target.value)}
            />
          ) : (
            <Input
              id={id}
              aria-label={itemLabel}
              aria-invalid={meta.error ? true : undefined}
              aria-describedby={describedBy}
              value={value}
              readOnly={meta.readOnly}
              onChange={(event) => props.onChange(event.target.value)}
            />
          )}
        </div>
        {meta.readOnly ? null : (
          <div className="flex shrink-0 flex-col gap-0.5 sm:flex-row">
            <IconButton
              icon={ArrowUp}
              label={t("library.list.moveUp", { name: itemLabel })}
              disabled={position === 1}
              onClick={() => props.onMove(-1)}
            />
            <IconButton
              icon={ArrowDown}
              label={t("library.list.moveDown", { name: itemLabel })}
              disabled={position === total}
              onClick={() => props.onMove(1)}
            />
            <IconButton
              icon={Trash2}
              label={t("library.list.remove", { name: itemLabel })}
              onClick={props.onRemove}
            />
          </div>
        )}
      </div>
      {meta.error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {meta.error}
        </p>
      ) : null}
      {meta.warnings.map((text) => (
        <p
          key={text}
          data-testid="field-warning"
          className="border-l-2 border-accent-2 pl-2 text-xs text-muted"
        >
          {text}
        </p>
      ))}
    </li>
  );
}

/** Editable, reorderable list of strings (limits, catchphrases, greetings, …). */
export function StringListEditor(props: StringListEditorProps) {
  const {
    label,
    items,
    onChange,
    path,
    addLabel,
    itemLabel,
    hint,
    multiline = false,
    rows = 3,
  } = props;
  const baseId = useId();
  const { readOnly } = useFieldMeta();
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-sm font-medium leading-none">{label}</p>
      {hint ? <p className="text-xs text-muted">{hint}</p> : null}
      {items.length > 0 ? (
        <ul className="flex flex-col gap-2" aria-label={label}>
          {items.map((value, index) => (
            <Row
              key={index}
              id={`${baseId}-${index}`}
              path={`${path}.${index}`}
              value={value}
              position={index + 1}
              total={items.length}
              itemLabel={itemLabel(index + 1)}
              multiline={multiline}
              rows={rows}
              onChange={(next) => onChange(replaceAt(items, index, next))}
              onMove={(delta) => onChange(moveItem(items, index, index + delta))}
              onRemove={() => onChange(removeAt(items, index))}
            />
          ))}
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
          onClick={() => onChange([...items, ""])}
        >
          <Plus aria-hidden="true" />
          {addLabel}
        </Button>
      )}
    </div>
  );
}
