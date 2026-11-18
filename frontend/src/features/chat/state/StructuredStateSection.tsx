import { Check } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { flattenTree, pathLabel, type Loc } from "@/features/library/world/treeOps";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { CastMemberSummary, StatePatch } from "@/types/chat";
import { ManualBadge } from "./ManualBadge";
import { diffStructuredPatch, TENSION_LEVELS, type StructuredDraft } from "./stateHelpers";

interface StructuredStateSectionProps {
  value: StructuredDraft;
  locations: readonly Loc[];
  cast: readonly CastMemberSummary[];
  silence: Record<string, number>;
  manualKeys: ReadonlySet<string>;
  pending: boolean;
  onSave: (patch: StatePatch) => void;
}

type TensionKey = "t0" | "t1" | "t2" | "t3" | "t4";

export function StructuredStateSection({
  value,
  locations,
  cast,
  silence,
  manualKeys,
  pending,
  onSave,
}: StructuredStateSectionProps) {
  const valueKey = JSON.stringify(value);
  const [override, setOverride] = useState<{ key: string; value: StructuredDraft } | null>(null);
  const draft = override && override.key === valueKey ? override.value : value;

  function updateDraft(updater: (prev: StructuredDraft) => StructuredDraft): void {
    setOverride((prev) => {
      const current = prev && prev.key === valueKey ? prev.value : value;
      return { key: valueKey, value: updater(current) };
    });
  }

  const diff = diffStructuredPatch(value, draft);
  const locationOptions = flattenTree(locations).map(({ loc }) => ({
    value: loc.id,
    label: pathLabel(locations, loc.id),
  }));
  if (draft.location_id && !locationOptions.some((o) => o.value === draft.location_id)) {
    locationOptions.push({ value: draft.location_id, label: draft.location_id });
  }

  function toggleListId(key: "present_ids" | "awaiting_reply", id: string): void {
    updateDraft((prev) => {
      const list = prev[key];
      const next = list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
      return { ...prev, [key]: next };
    });
  }

  return (
    <section
      aria-labelledby="state-structured-heading"
      className="flex flex-col gap-3 rounded-lg border border-border bg-bg p-3"
    >
      <h3 id="state-structured-heading" className="text-sm font-semibold">
        {t("stateEditor.structured.title")}
      </h3>

      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center justify-between gap-1">
          <Label htmlFor="state-location">{t("stateEditor.structured.location")}</Label>
          <ManualBadge visible={manualKeys.has("location_id")} />
        </div>
        <select
          id="state-location"
          value={draft.location_id}
          onChange={(e) => updateDraft((p) => ({ ...p, location_id: e.target.value }))}
          className="h-10 w-full rounded-md border border-border bg-surface px-3 text-sm text-fg"
        >
          {locationOptions.length === 0 ? (
            <option value="">{t("stateEditor.structured.noLocations")}</option>
          ) : null}
          {locationOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center justify-between gap-1">
          <Label htmlFor="state-time">{t("stateEditor.structured.time")}</Label>
          <ManualBadge visible={manualKeys.has("time")} />
        </div>
        <Input
          id="state-time"
          value={draft.time}
          placeholder={t("stateEditor.structured.timePlaceholder")}
          onChange={(e) => updateDraft((p) => ({ ...p, time: e.target.value }))}
        />
      </div>

      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center justify-between gap-1">
          <Label htmlFor="state-tension">{t("stateEditor.structured.tension")}</Label>
          <ManualBadge visible={manualKeys.has("tension")} />
        </div>
        <select
          id="state-tension"
          value={String(draft.tension)}
          onChange={(e) => updateDraft((p) => ({ ...p, tension: Number(e.target.value) }))}
          className="h-10 w-full rounded-md border border-border bg-surface px-3 text-sm text-fg"
        >
          {TENSION_LEVELS.map((n) => (
            <option key={n} value={String(n)}>
              {t(`library.world.tension.${`t${n}` as TensionKey}`)}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center justify-between gap-1">
          <span id="state-present-label" className="text-sm font-medium">
            {t("stateEditor.structured.present")}
          </span>
          <ManualBadge visible={manualKeys.has("present_ids")} />
        </div>
        {cast.length === 0 ? (
          <p className="text-xs text-muted">{t("stateEditor.structured.emptyCast")}</p>
        ) : (
          <div role="group" aria-labelledby="state-present-label" className="flex flex-wrap gap-2">
            {cast.map((m) => {
              const active = draft.present_ids.includes(m.id);
              const silentCount = silence[m.id] ?? 0;
              return (
                <button
                  key={m.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggleListId("present_ids", m.id)}
                  className={cn(
                    "inline-flex min-h-9 items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium",
                    active
                      ? "border-accent bg-surface-2 text-fg"
                      : "border-border bg-surface text-muted hover:text-fg",
                  )}
                >
                  {active ? <Check className="size-3.5" aria-hidden="true" /> : null}
                  <span>{m.name}</span>
                  {silentCount > 0 ? (
                    <span className="text-[11px] text-muted">
                      ({t("stateEditor.structured.silenceCount", { count: silentCount })})
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center justify-between gap-1">
          <span id="state-awaiting-label" className="text-sm font-medium">
            {t("stateEditor.structured.awaitingReply")}
          </span>
          <ManualBadge visible={manualKeys.has("awaiting_reply")} />
        </div>
        {cast.length === 0 ? (
          <p className="text-xs text-muted">{t("stateEditor.structured.emptyCast")}</p>
        ) : (
          <div role="group" aria-labelledby="state-awaiting-label" className="flex flex-wrap gap-2">
            {cast.map((m) => {
              const active = draft.awaiting_reply.includes(m.id);
              return (
                <button
                  key={m.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggleListId("awaiting_reply", m.id)}
                  className={cn(
                    "inline-flex min-h-9 items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium",
                    active
                      ? "border-accent-2 bg-surface-2 text-fg"
                      : "border-border bg-surface text-muted hover:text-fg",
                  )}
                >
                  {active ? <Check className="size-3.5" aria-hidden="true" /> : null}
                  <span>{m.name}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <Button
        type="button"
        size="sm"
        disabled={!diff || pending}
        onClick={() => {
          if (diff) onSave(diff);
        }}
      >
        {pending ? t("stateEditor.saving") : t("stateEditor.save")}
      </Button>
    </section>
  );
}
