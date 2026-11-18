import { AlertCircle, CheckCircle2, FileJson, Loader2, Save, Sparkles, X } from "lucide-react";
import { useId } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { libraryErrorMessage, parseApiError } from "@/features/library/lib/errors";
import { errorMessage, t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { Visibility } from "@/types/library";
import { CardJudgePanel } from "./CardJudgePanel";
import { ResultPreview } from "./ResultPreview";
import type {
  CardJudgeResult,
  CreatorPipelineStage,
  FormatWarning,
  NoticeEvent,
  TargetType,
} from "./types";

function stageText(stage: CreatorPipelineStage): string | null {
  switch (stage) {
    case "drafting_raw":
      return t("create.pipeline.stages.drafting_raw");
    case "formatting":
      return t("create.pipeline.stages.formatting");
    case "validating":
      return t("create.pipeline.stages.validating");
    case "judging":
      return t("create.pipeline.stages.judging");
    case "done":
      return t("create.pipeline.stages.done");
    case "error":
      return t("create.pipeline.stages.error");
    default:
      return null;
  }
}

export interface PipelineOutputPanelProps {
  targetType: TargetType;
  stage: CreatorPipelineStage;
  isGenerating: boolean;
  isStreamingChat: boolean;
  rawText: string;
  onChangeRaw: (raw: string) => void;
  onGenerateFull: () => void;
  onGenerateFromRaw: () => void;
  generatedData: Record<string, unknown> | null;
  warnings: readonly FormatWarning[];
  jsonText: string;
  jsonInvalid: boolean;
  onPatchData: (patch: Record<string, unknown>) => void;
  onChangeJsonText: (text: string) => void;
  judgeScore: CardJudgeResult | null;
  notices: readonly NoticeEvent[];
  onDismissNotice: (index: number) => void;
  pipelineErrorCode: string | null;
  visibility: Visibility;
  onVisibility: (visibility: Visibility) => void;
  isSaving: boolean;
  saveError: unknown;
  onSave: () => void;
}

/** Step 1 (editable raw prose), Step 2 (formatted preview + CardJudgePanel), and Save controls. */
export function PipelineOutputPanel({
  targetType,
  stage,
  isGenerating,
  isStreamingChat,
  rawText,
  onChangeRaw,
  onGenerateFull,
  onGenerateFromRaw,
  generatedData,
  warnings,
  jsonText,
  jsonInvalid,
  onPatchData,
  onChangeJsonText,
  judgeScore,
  notices,
  onDismissNotice,
  pipelineErrorCode,
  visibility,
  onVisibility,
  isSaving,
  saveError,
  onSave,
}: PipelineOutputPanelProps) {
  const rawId = useId();
  const visibilityId = useId();

  const busy = isGenerating || isStreamingChat;
  const pillText = stageText(stage);
  const showSettingsLink =
    pipelineErrorCode === "openrouter_key_missing" || pipelineErrorCode === "llm_auth_failed";

  const parsedSaveError = saveError ? parseApiError(saveError) : null;

  return (
    <div className="flex flex-col gap-5">
      {/* Live progress pill */}
      {pillText ? (
        <div
          role="status"
          data-testid="pipeline-stage"
          data-stage={stage}
          className={cn(
            "flex items-center gap-2 rounded-md border px-3 py-2 text-xs font-medium",
            stage === "error"
              ? "border-2 border-danger bg-surface text-danger"
              : stage === "done"
                ? "border-accent-2 bg-surface text-fg"
                : "border-accent bg-accent/10 text-fg",
          )}
        >
          {isGenerating ? (
            <Loader2 className="size-4 shrink-0 motion-safe:animate-spin" aria-hidden="true" />
          ) : stage === "done" ? (
            <CheckCircle2 className="size-4 shrink-0 text-accent-2" aria-hidden="true" />
          ) : (
            <AlertCircle className="size-4 shrink-0 text-danger" aria-hidden="true" />
          )}
          <span>{pillText}</span>
        </div>
      ) : null}

      {/* Step 1: Raw draft */}
      <section className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 md:p-5">
        <header className="flex flex-col gap-1">
          <h2 className="text-base font-semibold">{t("create.pipeline.step1Title")}</h2>
          <p className="text-xs text-muted">{t("create.pipeline.step1Hint")}</p>
        </header>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={rawId}>{t("create.pipeline.rawLabel")}</Label>
          <textarea
            id={rawId}
            rows={7}
            disabled={busy}
            value={rawText}
            placeholder={t("create.pipeline.rawPlaceholder")}
            onChange={(e) => onChangeRaw(e.target.value)}
            className="flex min-h-36 w-full resize-y rounded-md border border-border bg-bg p-3 font-content text-sm leading-relaxed text-fg placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            disabled={busy}
            onClick={onGenerateFull}
            className="min-h-10 flex-1 shadow-glow"
          >
            {isGenerating ? (
              <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles className="size-4" aria-hidden="true" />
            )}
            {isGenerating ? t("create.pipeline.generating") : t("create.pipeline.generateFull")}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={busy || !rawText.trim()}
            onClick={onGenerateFromRaw}
            className="min-h-10 flex-1"
          >
            <FileJson className="size-4" aria-hidden="true" />
            {t("create.pipeline.generateFromRaw")}
          </Button>
        </div>
      </section>

      {/* Pipeline errors & notices */}
      {pipelineErrorCode ? (
        <div
          role="alert"
          data-testid="pipeline-error"
          className="flex flex-col gap-2 rounded-lg border-2 border-danger bg-surface p-3.5 text-xs"
        >
          <div className="flex items-start gap-2">
            <AlertCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
            <span>{errorMessage(pipelineErrorCode)}</span>
          </div>
          {showSettingsLink ? (
            <Link
              to="/settings"
              className="w-fit font-medium text-accent-2 underline-offset-4 hover:underline"
            >
              {t("library.judge.openSettings")}
            </Link>
          ) : null}
        </div>
      ) : null}

      {notices.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {notices.map((notice, idx) => (
            <li
              key={`${notice.code}-${idx}`}
              role="status"
              className="flex items-start justify-between gap-2 rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-muted"
            >
              <span>
                {notice.agent === "card_judge"
                  ? t("create.pipeline.notices.cardJudgeSkipped", {
                      detail: notice.detail ?? errorMessage(notice.code),
                    })
                  : t("create.pipeline.notices.generic", {
                      detail: notice.detail ?? errorMessage(notice.code),
                    })}
              </span>
              <button
                type="button"
                aria-label={t("create.pipeline.notices.dismiss")}
                onClick={() => onDismissNotice(idx)}
                className="rounded-sm p-0.5 hover:text-fg"
              >
                <X className="size-3.5" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {/* Step 2: Result + Card Judge + Save */}
      <section className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 md:p-5">
        <h2 className="text-base font-semibold">{t("create.pipeline.step2Title")}</h2>

        {generatedData ? (
          <>
            <ResultPreview
              targetType={targetType}
              data={generatedData}
              warnings={warnings}
              jsonText={jsonText}
              jsonInvalid={jsonInvalid}
              disabled={busy || isSaving}
              onPatchData={onPatchData}
              onChangeJsonText={onChangeJsonText}
            />

            <CardJudgePanel result={judgeScore} embedded />

            {parsedSaveError ? (
              <div
                role="alert"
                data-testid="creator-save-error"
                className="flex items-start gap-2 rounded-md border-2 border-danger bg-surface-2 p-3 text-xs"
              >
                <AlertCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
                <div className="flex min-w-0 flex-col gap-1">
                  <p className="font-medium text-fg">{libraryErrorMessage(parsedSaveError.code)}</p>
                  {parsedSaveError.general.map((line) => (
                    <p key={line} className="text-muted">
                      {line}
                    </p>
                  ))}
                  {Object.entries(parsedSaveError.fields).map(([field, msg]) => (
                    <p key={field} className="text-muted">
                      <code className="mr-1 font-mono text-[11px]">{field}:</code>
                      {msg}
                    </p>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="flex flex-col gap-3 border-t border-border pt-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <Label htmlFor={visibilityId}>{t("create.pipeline.save.visibilityLabel")}</Label>
                  <p className="text-xs text-muted">{t("create.pipeline.save.visibilityHint")}</p>
                </div>
                <Switch
                  id={visibilityId}
                  disabled={busy || isSaving}
                  checked={visibility === "public"}
                  onCheckedChange={(checked) => onVisibility(checked ? "public" : "private")}
                />
              </div>

              <Button
                type="button"
                disabled={busy || isSaving || jsonInvalid}
                onClick={onSave}
                className="min-h-11 w-full"
              >
                {isSaving ? (
                  <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" />
                ) : (
                  <Save className="size-4" aria-hidden="true" />
                )}
                {isSaving ? t("create.pipeline.save.saving") : t("create.pipeline.save.button")}
              </Button>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted">{t("create.pipeline.step2Empty")}</p>
        )}
      </section>
    </div>
  );
}
