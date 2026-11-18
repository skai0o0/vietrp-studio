import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { t } from "@/i18n";
import { ChipsInput } from "../form/ChipsInput";
import { useFormState } from "../form/FormContext";
import { NumberField, SelectField, TextAreaField, TextField, ToggleField } from "../form/fields";
import { IconButton } from "../form/IconButton";
import { moveItem, removeAt, replaceAt, uniqueSlug } from "../lib/arrays";
import type { EntryDraft } from "./lorebookDraft";

const SELECT_MODES: EntryDraft["select_mode"][] = ["keyword", "ai", "both"];
const POSITIONS: EntryDraft["position"][] = ["before_char", "after_char"];

interface EntryRowProps {
  entry: EntryDraft;
  index: number;
  total: number;
  onChange: (entry: EntryDraft) => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}

function EntryRow({ entry, index, total, onChange, onMove, onRemove }: EntryRowProps) {
  const { readOnly } = useFormState();
  const [open, setOpen] = useState(false);
  const base = `entries.${index}`;
  const name = entry.title.trim() || t("library.lorebook.entryItem", { n: index + 1 });
  const patch = (change: Partial<EntryDraft>): void => onChange({ ...entry, ...change });

  return (
    <li className="flex flex-col rounded-md border border-border bg-bg">
      <div className="flex flex-wrap items-center gap-2 p-2">
        <button
          type="button"
          aria-expanded={open}
          aria-label={t(open ? "library.lorebook.collapse" : "library.lorebook.expand", { name })}
          className="flex min-h-10 min-w-0 flex-1 items-center gap-2 rounded-md px-1 text-left hover:bg-surface-2"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? (
            <ChevronDown className="size-4 shrink-0" aria-hidden="true" />
          ) : (
            <ChevronRight className="size-4 shrink-0" aria-hidden="true" />
          )}
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{name}</span>
            <span className="block truncate text-xs text-muted">
              {entry.constant
                ? t("library.lorebook.constantShort")
                : entry.keys.join(", ") || t("library.lorebook.noKeys")}
            </span>
          </span>
        </button>
        <Switch
          checked={entry.enabled}
          disabled={readOnly}
          aria-label={t("library.lorebook.enabledAria", { name })}
          onCheckedChange={(enabled) => patch({ enabled })}
        />
        {readOnly ? null : (
          <div className="flex gap-0.5">
            <IconButton
              icon={ArrowUp}
              label={t("library.list.moveUp", { name })}
              disabled={index === 0}
              onClick={() => onMove(-1)}
            />
            <IconButton
              icon={ArrowDown}
              label={t("library.list.moveDown", { name })}
              disabled={index === total - 1}
              onClick={() => onMove(1)}
            />
            <IconButton
              icon={Trash2}
              label={t("library.list.remove", { name })}
              onClick={onRemove}
            />
          </div>
        )}
      </div>
      {open ? (
        <div className="flex flex-col gap-4 border-t border-border p-3 md:p-4">
          <TextField
            label={t("library.lorebook.entryTitle")}
            path={`${base}.title`}
            value={entry.title}
            onChange={(title) => patch({ title })}
          />
          <ChipsInput
            label={t("library.lorebook.keys")}
            path={`${base}.keys`}
            hint={t("library.lorebook.keysHint")}
            values={entry.keys}
            onChange={(keys) => patch({ keys })}
          />
          {entry.selective ? (
            <ChipsInput
              label={t("library.lorebook.secondaryKeys")}
              path={`${base}.secondary_keys`}
              hint={t("library.lorebook.secondaryKeysHint")}
              values={entry.secondary_keys}
              onChange={(secondary_keys) => patch({ secondary_keys })}
            />
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField
              label={t("library.lorebook.selectMode")}
              path={`${base}.select_mode`}
              value={entry.select_mode}
              options={SELECT_MODES.map((mode) => ({
                value: mode,
                label: t(`library.lorebook.modes.${mode}`),
              }))}
              onChange={(value) => patch({ select_mode: value as EntryDraft["select_mode"] })}
            />
            <SelectField
              label={t("library.lorebook.position")}
              path={`${base}.position`}
              value={entry.position}
              options={POSITIONS.map((p) => ({
                value: p,
                label: t(`library.lorebook.positions.${p}`),
              }))}
              onChange={(value) => patch({ position: value as EntryDraft["position"] })}
            />
            <NumberField
              label={t("library.lorebook.priority")}
              path={`${base}.priority`}
              hint={t("library.lorebook.priorityHint")}
              value={entry.priority}
              onChange={(priority) => patch({ priority: priority ?? 0 })}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <ToggleField
              label={t("library.lorebook.constant")}
              hint={t("library.lorebook.constantHint")}
              checked={entry.constant}
              onChange={(constant) => patch({ constant })}
            />
            <ToggleField
              label={t("library.lorebook.selective")}
              hint={t("library.lorebook.selectiveHint")}
              checked={entry.selective}
              onChange={(selective) => patch({ selective })}
            />
          </div>
          <TextAreaField
            label={t("library.lorebook.content")}
            path={`${base}.content`}
            rows={5}
            value={entry.content}
            onChange={(content) => patch({ content })}
          />
        </div>
      ) : null}
    </li>
  );
}

interface EntriesTableProps {
  entries: EntryDraft[];
  onChange: (entries: EntryDraft[]) => void;
}

/** Entry list with a compact summary row; each row expands into the inline editor. */
export function EntriesTable({ entries, onChange }: EntriesTableProps) {
  const { readOnly } = useFormState();

  function add(): void {
    const id = uniqueSlug(
      "entry",
      entries.map((e) => e.id),
    );
    onChange([
      ...entries,
      {
        id,
        title: "",
        keys: [],
        secondary_keys: [],
        selective: false,
        constant: false,
        priority: 0,
        position: "before_char",
        select_mode: "keyword",
        content: "",
        enabled: true,
      },
    ]);
  }

  return (
    <div className="flex flex-col gap-3">
      {entries.length === 0 ? (
        <p className="text-sm text-muted">{t("library.lorebook.noEntries")}</p>
      ) : null}
      <ul className="flex flex-col gap-2" aria-label={t("library.lorebook.entries")}>
        {entries.map((entry, index) => (
          <EntryRow
            key={entry.id}
            entry={entry}
            index={index}
            total={entries.length}
            onChange={(next) => onChange(replaceAt(entries, index, next))}
            onMove={(delta) => onChange(moveItem(entries, index, index + delta))}
            onRemove={() => onChange(removeAt(entries, index))}
          />
        ))}
      </ul>
      {readOnly ? null : (
        <Button type="button" variant="outline" size="sm" className="self-start" onClick={add}>
          <Plus aria-hidden="true" />
          {t("library.lorebook.addEntry")}
        </Button>
      )}
    </div>
  );
}
