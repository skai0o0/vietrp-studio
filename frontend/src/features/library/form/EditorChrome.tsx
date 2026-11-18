import { AlertCircle, ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import { libraryErrorMessage, parseApiError } from "../lib/errors";

interface EditorHeaderProps {
  title: string;
  backTo: string;
  backLabel: string;
  badges?: ReactNode;
  actions?: ReactNode;
}

/** Sticky title bar with the back link and the editor's actions. */
export function EditorHeader({ title, backTo, backLabel, badges, actions }: EditorHeaderProps) {
  return (
    <header className="sticky top-0 z-10 -mx-4 flex flex-col gap-2 border-b border-border bg-bg px-4 py-3 md:-mx-8 md:px-8">
      <Link
        to={backTo}
        className="inline-flex w-fit items-center gap-1.5 rounded-sm text-sm text-muted hover:text-fg"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        {backLabel}
      </Link>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h1 className="min-w-0 truncate text-xl font-semibold md:text-2xl">{title}</h1>
          {badges}
        </div>
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      </div>
    </header>
  );
}

interface SaveErrorBannerProps {
  error: unknown;
}

/** Top-level summary of a failed save. Field-level messages are shown beside their fields. */
export function SaveErrorBanner({ error }: SaveErrorBannerProps) {
  if (!error) return null;
  const parsed = parseApiError(error);
  const fieldCount = Object.keys(parsed.fields).length;
  return (
    <div
      role="alert"
      data-testid="save-error"
      className="flex items-start gap-2 rounded-lg border-2 border-danger bg-surface p-3 text-sm"
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
      <div className="flex min-w-0 flex-col gap-1">
        <p className="font-medium">{libraryErrorMessage(parsed.code)}</p>
        {fieldCount > 0 ? (
          <p className="text-muted">{t("library.errors.fieldCount", { count: fieldCount })}</p>
        ) : null}
        {parsed.general.map((line) => (
          <p key={line} className="text-muted">
            {line}
          </p>
        ))}
        {parsed.detail && fieldCount === 0 ? (
          <p className="break-words text-xs text-muted">{parsed.detail}</p>
        ) : null}
      </div>
    </div>
  );
}

interface LoadStatusProps {
  isPending: boolean;
  error: unknown;
  onRetry: () => void;
  backTo: string;
  backLabel: string;
}

/** Loading / not-found / error states for a detail route. */
export function LoadStatus({ isPending, error, onRetry, backTo, backLabel }: LoadStatusProps) {
  if (isPending) {
    return (
      <p role="status" className="p-8 text-sm text-muted">
        {t("pages.loading")}
      </p>
    );
  }
  const notFound = error instanceof ApiError && error.status === 404;
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 p-8 text-center">
      <p role="alert" className="text-sm text-muted">
        {notFound
          ? t("errors.not_found")
          : libraryErrorMessage(error instanceof ApiError ? error.code : "unknown")}
      </p>
      <div className="flex gap-2">
        {notFound ? null : (
          <Button variant="outline" onClick={onRetry}>
            {t("common.retry")}
          </Button>
        )}
        <Button asChild variant="outline">
          <Link to={backTo}>{backLabel}</Link>
        </Button>
      </div>
    </div>
  );
}
