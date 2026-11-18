import {
  AlertCircle,
  AlertTriangle,
  Award,
  Check,
  CheckCircle2,
  Lightbulb,
  Loader2,
  X,
} from "lucide-react";
import { useId } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { errorMessage, t, type MessageKey } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import { cn } from "@/lib/cn";
import type { CardJudgeCriterion, CardJudgeResult } from "./types";

const CRITERIA_ORDER = [
  "completeness",
  "atomic_concise",
  "no_command_tone",
  "distinct_voice",
  "actionable_goals",
  "safety_valid",
] as const;

const CRITERION_RANK = new Map<string, number>(
  CRITERIA_ORDER.map((criterionId, index) => [criterionId, index]),
);

function criterionLabel(criterion: CardJudgeCriterion): string {
  if (criterion.label.trim()) return criterion.label;
  const key = `library.judge.criteria.${criterion.id}` as MessageKey;
  const translated = t(key);
  return translated === key ? criterion.id : translated;
}

function orderedCriteria(criteria: readonly CardJudgeCriterion[]): CardJudgeCriterion[] {
  return [...criteria].sort((a, b) => {
    const rankA = CRITERION_RANK.get(a.id) ?? CRITERIA_ORDER.length;
    const rankB = CRITERION_RANK.get(b.id) ?? CRITERIA_ORDER.length;
    return rankA - rankB;
  });
}

function extractErrorCode(error: unknown): string | null {
  if (!error) return null;
  if (typeof error === "string") return error;
  if (error instanceof ApiError) return error.code;
  if (typeof error === "object" && "code" in error && typeof error.code === "string") {
    return error.code;
  }
  return "judge_failed";
}

export interface CardJudgePanelProps {
  result: CardJudgeResult | null | undefined;
  onJudge?: (() => void) | undefined;
  pending?: boolean;
  error?: unknown;
  hintNote?: string;
  embedded?: boolean;
  className?: string;
}

/** Displays Card Judge overall score, pass/fail status, 6 atomic criteria, and fix hints. */
export function CardJudgePanel({
  result,
  onJudge,
  pending = false,
  error,
  hintNote,
  embedded = false,
  className,
}: CardJudgePanelProps) {
  const headingId = useId();
  const errorCode = extractErrorCode(error);
  const showSettingsLink =
    errorCode === "openrouter_key_missing" || errorCode === "llm_auth_failed";

  const scorePercent = result ? Math.round(result.score * 100) : null;
  const thresholdPercent = result ? Math.round(result.threshold * 100) : null;
  const criteria = result ? orderedCriteria(result.criteria) : [];

  return (
    <section
      aria-labelledby={headingId}
      data-testid="card-judge-panel"
      className={cn(
        "flex flex-col gap-4 rounded-lg border border-border",
        embedded ? "bg-surface-2/40 p-4" : "bg-surface p-4 md:p-6",
        className,
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <Award className="size-4 shrink-0 text-accent" aria-hidden="true" />
            <h2 id={headingId} className="text-base font-semibold">
              {t("library.judge.title")}
            </h2>
            {result && scorePercent !== null ? (
              <>
                <span
                  data-testid="judge-score-badge"
                  className="inline-flex items-center rounded-sm border border-border bg-surface-2 px-2 py-0.5 font-mono text-xs font-semibold tabular-nums"
                >
                  {t("library.judge.scoreLabel", { score: scorePercent })}
                </span>
                <span
                  data-testid="judge-status-badge"
                  className={cn(
                    "inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-xs font-medium",
                    result.passed
                      ? "border-accent-2 bg-accent-2/10 text-fg"
                      : "border-2 border-danger bg-danger/10 text-danger",
                  )}
                >
                  {result.passed ? (
                    <CheckCircle2 className="size-3.5 shrink-0 text-accent-2" aria-hidden="true" />
                  ) : (
                    <AlertTriangle className="size-3.5 shrink-0 text-danger" aria-hidden="true" />
                  )}
                  {result.passed ? t("library.judge.passed") : t("library.judge.needsWork")}
                </span>
              </>
            ) : null}
          </div>
          <p className="text-xs text-muted">{t("library.judge.subtitle")}</p>
        </div>

        {onJudge ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={pending}
            onClick={onJudge}
            className="min-h-10 shrink-0"
          >
            {pending ? (
              <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" />
            ) : (
              <Award className="size-4" aria-hidden="true" />
            )}
            {pending ? t("library.judge.running") : t("library.judge.run")}
          </Button>
        ) : null}
      </header>

      {hintNote && onJudge ? <p className="text-xs text-muted">{hintNote}</p> : null}

      {errorCode ? (
        <div
          role="alert"
          data-testid="judge-error"
          className="flex flex-col gap-2 rounded-md border-2 border-danger bg-surface-2 p-3 text-xs"
        >
          <div className="flex items-start gap-2">
            <AlertCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
            <span className="text-fg">{errorMessage(errorCode)}</span>
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

      {result && scorePercent !== null && thresholdPercent !== null ? (
        <div className="flex flex-col gap-3">
          <p className="text-xs text-muted tabular-nums">
            {t("library.judge.thresholdNote", {
              threshold: thresholdPercent,
              score: scorePercent,
            })}
          </p>
          <ul className="flex flex-col gap-2">
            {criteria.map((criterion) => {
              const probPercent = Math.round(criterion.probability * 100);
              const label = criterionLabel(criterion);
              return (
                <li
                  key={criterion.id}
                  data-testid={`judge-criterion-${criterion.id}`}
                  className={cn(
                    "flex flex-col gap-2 rounded-md border bg-surface-2 p-3 text-sm",
                    criterion.passed ? "border-border" : "border-2 border-danger",
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {criterion.passed ? (
                      <Check className="size-4 shrink-0 text-accent-2" aria-hidden="true" />
                    ) : (
                      <X className="size-4 shrink-0 text-danger" aria-hidden="true" />
                    )}
                    <span className="min-w-0 flex-1 font-medium">{label}</span>
                    <span className="text-xs text-muted">
                      {criterion.passed
                        ? t("library.judge.criterionPassed")
                        : t("library.judge.criterionFailed")}
                    </span>
                    <span className="font-mono text-xs font-semibold tabular-nums">
                      {probPercent}%
                    </span>
                  </div>
                  <div
                    aria-hidden="true"
                    className="h-1.5 w-full overflow-hidden rounded-full border border-border bg-bg"
                  >
                    <div
                      className={cn("h-full", criterion.passed ? "bg-accent-2" : "bg-danger")}
                      style={{ width: `${Math.min(100, Math.max(0, probPercent))}%` }}
                    />
                  </div>
                  {criterion.hint_vi?.trim() ? (
                    <p className="flex items-start gap-2 border-l-2 border-accent-2 pl-2.5 text-xs text-fg">
                      <Lightbulb
                        className="mt-0.5 size-3.5 shrink-0 text-accent-2"
                        aria-hidden="true"
                      />
                      <span>{criterion.hint_vi}</span>
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-muted">
          {onJudge ? t("library.judge.emptyAction") : t("library.judge.empty")}
        </p>
      )}
    </section>
  );
}
