import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { CastMemberSummary } from "@/types/chat";
import { ManualBadge, PinnedBadge } from "./ManualBadge";
import {
  buildBondPayload,
  CLOSENESS_LEVELS,
  normalizeBondRecord,
  type BondFieldsValue,
  type NormalizedBondRecord,
} from "./stateHelpers";

interface BondsSectionProps {
  bonds: Record<string, unknown>;
  cast: readonly CastMemberSummary[];
  pending: boolean;
  embedded?: boolean;
  onSavePair: (pairId: string, payload: NormalizedBondRecord) => void;
}

type ClosenessKey = "c0" | "c1" | "c2" | "c3" | "c4";

const BOND_FIELD_LABELS = {
  addressing: "stateEditor.bonds.fields.addressing",
  nickname: "stateEditor.bonds.fields.nickname",
  relationship: "stateEditor.bonds.fields.relationship",
  stance: "stateEditor.bonds.fields.stance",
  closeness: "stateEditor.bonds.fields.closeness",
  history: "stateEditor.bonds.fields.history",
} as const;

function bondFieldLabel(field: string): string {
  if (field in BOND_FIELD_LABELS) {
    return t(BOND_FIELD_LABELS[field as keyof typeof BOND_FIELD_LABELS]);
  }
  return field;
}

const TEXT_FIELDS: Array<{
  key: Exclude<keyof BondFieldsValue, "closeness">;
  labelKey:
    | "stateEditor.bonds.fields.addressing"
    | "stateEditor.bonds.fields.nickname"
    | "stateEditor.bonds.fields.relationship"
    | "stateEditor.bonds.fields.stance"
    | "stateEditor.bonds.fields.history";
}> = [
  { key: "addressing", labelKey: "stateEditor.bonds.fields.addressing" },
  { key: "nickname", labelKey: "stateEditor.bonds.fields.nickname" },
  { key: "relationship", labelKey: "stateEditor.bonds.fields.relationship" },
  { key: "stance", labelKey: "stateEditor.bonds.fields.stance" },
  { key: "history", labelKey: "stateEditor.bonds.fields.history" },
];

function BondPairRow({
  record,
  expanded,
  onToggle,
  pending,
  onSave,
}: {
  record: NormalizedBondRecord;
  expanded: boolean;
  onToggle: () => void;
  pending: boolean;
  onSave: (payload: NormalizedBondRecord) => void;
}) {
  const recordKey = JSON.stringify(record.fields);
  const [override, setOverride] = useState<{ key: string; value: BondFieldsValue } | null>(null);
  const fields = override && override.key === recordKey ? override.value : record.fields;

  function updateFields(updater: (prev: BondFieldsValue) => BondFieldsValue): void {
    setOverride((prev) => {
      const current = prev && prev.key === recordKey ? prev.value : record.fields;
      return { key: recordKey, value: updater(current) };
    });
  }

  const pinnedSet = new Set(record.pinned);
  const manualSet = new Set(record.manual);
  const dirty = JSON.stringify(fields) !== recordKey;
  const closenessLabel = t(`stateEditor.bonds.closenessLevels.${`c${fields.closeness}` as ClosenessKey}`);

  return (
    <div data-testid={`bond-pair-${record.pair_id}`} className="border-b border-border-subtle last:border-b-0">
      <button
        type="button"
        aria-expanded={expanded}
        aria-label={
          expanded
            ? t("stateEditor.bonds.collapsePair", { label: record.label })
            : t("stateEditor.bonds.expandPair", { label: record.label })
        }
        onClick={onToggle}
        className="flex min-h-10 w-full items-center gap-2 py-2 text-left transition-colors duration-fast ease-ui hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      >
        <ChevronRight
          className={cn(
            "size-3.5 shrink-0 text-muted transition-transform duration-fast ease-ui motion-reduce:transition-none",
            expanded && "rotate-90 text-fg",
          )}
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-fg">{record.label}</span>
        <span className="shrink-0 truncate text-2xs text-muted">{closenessLabel}</span>
      </button>

      {expanded ? (
        <div className="flex flex-col gap-2.5 pb-3 pl-5 pt-1">
          {TEXT_FIELDS.map(({ key, labelKey }) => {
            const isPinned = pinnedSet.has(key);
            const isManual = manualSet.has(key);
            const inputId = `bond-${record.pair_id}-${key}`;
            return (
              <div key={key} className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center justify-between gap-1">
                  <Label htmlFor={inputId} className="text-xs text-muted">
                    {t(labelKey)}
                  </Label>
                  <div className="flex flex-wrap gap-1">
                    <PinnedBadge visible={isPinned} />
                    <ManualBadge visible={isManual} />
                  </div>
                </div>
                <Input
                  id={inputId}
                  value={fields[key]}
                  readOnly={isPinned}
                  disabled={isPinned}
                  title={isPinned ? t("stateEditor.bonds.pinnedNote") : undefined}
                  onChange={(e) => updateFields((p) => ({ ...p, [key]: e.target.value }))}
                  className="h-9 text-xs md:h-9"
                />
              </div>
            );
          })}

          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center justify-between gap-1">
              <Label htmlFor={`bond-${record.pair_id}-closeness`} className="text-xs text-muted">
                {t("stateEditor.bonds.fields.closeness")}
              </Label>
              <ManualBadge visible={manualSet.has("closeness")} />
            </div>
            <Select
              id={`bond-${record.pair_id}-closeness`}
              value={String(fields.closeness)}
              onChange={(e) => updateFields((p) => ({ ...p, closeness: Number(e.target.value) }))}
              className="h-9 text-xs md:h-9"
            >
              {CLOSENESS_LEVELS.map((n) => (
                <option key={n} value={String(n)}>
                  {t(`stateEditor.bonds.closenessLevels.${`c${n}` as ClosenessKey}`)}
                </option>
              ))}
            </Select>
          </div>

          {record.changes.length > 0 ? (
            <details className="text-xs text-muted">
              <summary className="cursor-pointer font-medium">
                {t("stateEditor.bonds.changesTitle", { count: record.changes.length })}
              </summary>
              <ul className="mt-1 flex flex-col gap-1 pl-2">
                {record.changes.map((c, idx) => (
                  <li key={`${c.seq}-${c.field}-${idx}`}>
                    {t("stateEditor.bonds.changeLine", {
                      seq: c.seq,
                      field: bondFieldLabel(c.field),
                      old: c.old || "—",
                      new: c.new || "—",
                    })}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!dirty || pending}
            onClick={() => onSave(buildBondPayload(record, fields))}
          >
            {pending ? t("stateEditor.saving") : t("stateEditor.bonds.savePair")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function BondsSection({
  bonds,
  cast,
  pending,
  embedded = false,
  onSavePair,
}: BondsSectionProps) {
  const entries = Object.entries(bonds).map(([pairId, raw]) =>
    normalizeBondRecord(pairId, raw, cast),
  );
  const [expandedPairId, setExpandedPairId] = useState<string | null | undefined>(undefined);
  const activePairId =
    expandedPairId !== undefined
      ? expandedPairId
      : entries.length === 1
        ? (entries[0]?.pair_id ?? null)
        : null;

  const Container = embedded ? "div" : "section";

  return (
    <Container
      {...(!embedded ? { "aria-labelledby": "state-bonds-heading" } : {})}
      className={cn(
        "flex flex-col gap-2",
        !embedded && "rounded-lg border border-border bg-surface p-3",
      )}
    >
      {!embedded ? (
        <h3 id="state-bonds-heading" className="text-sm font-semibold">
          {t("stateEditor.bonds.title")}
        </h3>
      ) : null}
      {entries.length === 0 ? (
        <p className="text-xs text-muted">{t("stateEditor.bonds.empty")}</p>
      ) : (
        <div className="flex flex-col">
          {entries.map((record) => (
            <BondPairRow
              key={record.pair_id}
              record={record}
              expanded={activePairId === record.pair_id}
              onToggle={() =>
                setExpandedPairId((prev) =>
                  (prev === undefined ? activePairId : prev) === record.pair_id
                    ? null
                    : record.pair_id,
                )
              }
              pending={pending}
              onSave={(payload) => onSavePair(record.pair_id, payload)}
            />
          ))}
        </div>
      )}
    </Container>
  );
}
