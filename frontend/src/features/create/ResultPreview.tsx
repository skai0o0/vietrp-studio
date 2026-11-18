import { AlertTriangle, Code2, Lightbulb } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import type { FormatWarning, TargetType } from "./types";

function warningLabel(warning: FormatWarning): string {
  switch (warning.code) {
    case "field_long":
      return t("library.warnings.fieldLong");
    case "imperative_text":
      return t("library.warnings.imperativeText");
    case "age_missing":
      return t("library.warnings.ageMissing");
    default:
      return t("library.warnings.generic");
  }
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim() !== "");
}

function asAgeInput(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? String(Math.trunc(value)) : "";
}

export interface ResultPreviewProps {
  targetType: TargetType;
  data: Record<string, unknown>;
  warnings: readonly FormatWarning[];
  jsonText: string;
  jsonInvalid: boolean;
  disabled?: boolean;
  onPatchData: (patch: Record<string, unknown>) => void;
  onChangeJsonText: (text: string) => void;
}

/** Displays formatted character/world preview, quick Name/Age edits, warnings, and JSON editor. */
export function ResultPreview({
  targetType,
  data,
  warnings,
  jsonText,
  jsonInvalid,
  disabled = false,
  onPatchData,
  onChangeJsonText,
}: ResultPreviewProps) {
  const [jsonOpen, setJsonOpen] = useState(false);
  const nameId = useId();
  const ageId = useId();
  const jsonId = useId();

  const name = asString(data.name);
  const ageValue = data.age;
  const missingAge =
    targetType === "character" && (typeof ageValue !== "number" || !Number.isFinite(ageValue));
  const tags = asStringList(data.tags);

  const speechObj =
    typeof data.speech === "object" && data.speech !== null
      ? (data.speech as Record<string, unknown>)
      : null;
  const greetings = Array.isArray(data.greetings) ? data.greetings : [];
  const locations = Array.isArray(data.locations) ? data.locations : [];
  const openings = Array.isArray(data.openings) ? data.openings : [];

  return (
    <div className="flex flex-col gap-4">
      {/* Quick-edit Name & Age */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor={nameId}>{t("create.pipeline.preview.quickName")}</Label>
          <Input
            id={nameId}
            disabled={disabled}
            value={name}
            onChange={(e) => onPatchData({ name: e.target.value })}
          />
        </div>
        {targetType === "character" ? (
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor={ageId}>{t("create.pipeline.preview.quickAge")}</Label>
            <Input
              id={ageId}
              type="number"
              inputMode="numeric"
              min={0}
              max={10000}
              disabled={disabled}
              value={asAgeInput(ageValue)}
              onChange={(e) => {
                const raw = e.target.value.trim();
                const parsed = Number(raw);
                onPatchData({
                  age: raw === "" || !Number.isFinite(parsed) ? null : Math.trunc(parsed),
                });
              }}
            />
          </div>
        ) : null}
      </div>

      {missingAge ? (
        <p
          role="status"
          data-testid="creator-needs-age"
          className="flex items-start gap-2 rounded-md border-2 border-accent-2 bg-surface-2 p-3 text-xs text-fg"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-accent-2" aria-hidden="true" />
          <span>{t("create.pipeline.preview.quickAgeMissing")}</span>
        </p>
      ) : null}

      {/* Summary preview */}
      <div
        data-testid="creator-result-preview"
        className="flex flex-col gap-2.5 rounded-md border border-border bg-bg p-3.5 text-sm"
      >
        {targetType === "character" ? (
          <>
            {asString(data.tagline) ? (
              <p className="font-medium text-fg">{asString(data.tagline)}</p>
            ) : null}
            {asString(data.personality) ? (
              <div className="flex flex-col gap-0.5">
                <span className="text-xs font-medium text-muted">
                  {t("create.pipeline.preview.personality")}
                </span>
                <p className="font-content text-xs leading-relaxed text-fg">
                  {asString(data.personality)}
                </p>
              </div>
            ) : null}
            {asString(data.appearance) ? (
              <div className="flex flex-col gap-0.5">
                <span className="text-xs font-medium text-muted">
                  {t("create.pipeline.preview.appearance")}
                </span>
                <p className="font-content text-xs leading-relaxed text-fg">
                  {asString(data.appearance)}
                </p>
              </div>
            ) : null}
            {asString(data.goals) ? (
              <div className="flex flex-col gap-0.5">
                <span className="text-xs font-medium text-muted">
                  {t("create.pipeline.preview.goals")}
                </span>
                <p className="font-content text-xs leading-relaxed text-fg">
                  {asString(data.goals)}
                </p>
              </div>
            ) : null}
            {speechObj && asString(speechObj.style) ? (
              <div className="flex flex-col gap-0.5">
                <span className="text-xs font-medium text-muted">
                  {t("create.pipeline.preview.speech")}
                </span>
                <p className="font-content text-xs leading-relaxed text-fg">
                  {asString(speechObj.style)}
                </p>
              </div>
            ) : null}
            <p className="text-xs text-muted">
              {t("create.pipeline.preview.greetingsCount", { count: greetings.length })}
            </p>
          </>
        ) : (
          <>
            {asString(data.rules) ? (
              <div className="flex flex-col gap-0.5">
                <span className="text-xs font-medium text-muted">
                  {t("create.pipeline.preview.rules")}
                </span>
                <p className="font-content text-xs leading-relaxed text-fg">
                  {asString(data.rules)}
                </p>
              </div>
            ) : null}
            <div className="flex flex-wrap gap-3 text-xs text-muted">
              <span>
                {t("create.pipeline.preview.locationsCount", { count: locations.length })}
              </span>
              <span>{t("create.pipeline.preview.openingsCount", { count: openings.length })}</span>
            </div>
          </>
        )}

        {tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {tags.map((tag) => (
              <span
                key={tag}
                className="rounded-sm border border-border bg-surface-2 px-2 py-0.5 text-[11px] text-muted"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {/* Validation warnings */}
      {warnings.length > 0 ? (
        <div className="flex flex-col gap-1.5 rounded-md border border-border bg-surface-2 p-3">
          <p className="text-xs font-semibold text-fg">
            {t("create.pipeline.preview.warningsTitle", { count: warnings.length })}
          </p>
          <ul className="flex flex-col gap-1">
            {warnings.map((w, idx) => (
              <li
                key={`${w.code}-${w.path}-${idx}`}
                className="flex items-start gap-2 text-xs text-muted"
              >
                <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-accent-2" aria-hidden="true" />
                <span>
                  {w.path ? <code className="mr-1 font-mono text-[11px]">{w.path}:</code> : null}
                  {warningLabel(w)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Editable JSON drawer */}
      <div className="flex flex-col gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-expanded={jsonOpen}
          onClick={() => setJsonOpen((open) => !open)}
          className="w-fit"
        >
          <Code2 className="size-4" aria-hidden="true" />
          {jsonOpen
            ? t("create.pipeline.preview.editJsonHide")
            : t("create.pipeline.preview.editJsonShow")}
        </Button>

        {jsonOpen ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={jsonId}>{t("create.pipeline.preview.jsonLabel")}</Label>
            <textarea
              id={jsonId}
              rows={10}
              disabled={disabled}
              value={jsonText}
              onChange={(e) => onChangeJsonText(e.target.value)}
              className="flex min-h-40 w-full resize-y rounded-md border border-border bg-bg p-3 font-mono text-xs text-fg"
            />
            {jsonInvalid ? (
              <p role="alert" className="text-xs text-danger">
                {t("create.pipeline.preview.jsonInvalid")}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
