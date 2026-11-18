import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { errorMessage, t } from "@/i18n";
import type { ImportResult } from "@/types/library";
import { openTarget, warningLabel } from "./ImportResultPanel";

export type BatchStatus = "waiting" | "uploading" | "done" | "error";

export interface BatchItem {
  key: string;
  name: string;
  status: BatchStatus;
  result?: ImportResult;
  errorCode?: string | null;
}

interface ImportBatchListProps {
  items: readonly BatchItem[];
  running: boolean;
  onAnother: () => void;
  onNavigate: () => void;
}

function StatusIcon({ status }: { status: BatchStatus }) {
  if (status === "done")
    return <CheckCircle2 className="size-4 shrink-0 text-accent" aria-hidden />;
  if (status === "error") return <XCircle className="size-4 shrink-0 text-danger" aria-hidden />;
  if (status === "uploading") {
    return <Loader2 className="size-4 shrink-0 text-muted motion-safe:animate-spin" aria-hidden />;
  }
  return <span className="size-4 shrink-0" aria-hidden />;
}

function BatchRow({ item, onNavigate }: { item: BatchItem; onNavigate: () => void }) {
  const result = item.result;
  const target = result ? openTarget(result) : null;
  return (
    <li
      data-testid="import-batch-row"
      className="flex flex-col gap-1 border-b border-border py-2 last:border-b-0"
    >
      <div className="flex items-center gap-2 text-sm">
        <StatusIcon status={item.status} />
        <span className="min-w-0 flex-1 truncate" title={item.name}>
          {target?.name || item.name}
        </span>
        {result ? (
          <span className="shrink-0 rounded-sm border border-border px-2 py-0.5 text-xs text-muted">
            {t(`io.import.kind.${result.kind}`)}
          </span>
        ) : null}
        {target ? (
          <Link
            to={target.to}
            onClick={onNavigate}
            className="shrink-0 rounded-sm text-xs text-accent underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            {t("io.import.openItem")}
          </Link>
        ) : null}
      </div>
      {item.status === "waiting" ? (
        <p className="pl-6 text-xs text-muted">{t("io.import.batch.waiting")}</p>
      ) : null}
      {item.status === "error" ? (
        <p role="alert" className="pl-6 text-xs text-danger">
          {errorMessage(item.errorCode ?? null)}
        </p>
      ) : null}
      {result?.needs_age && result.kind === "character" ? (
        <p className="flex items-center gap-1 pl-6 text-xs text-danger">
          <AlertTriangle className="size-3" aria-hidden />
          {t("io.import.needsAgeTitle")}
        </p>
      ) : null}
      {result && result.warnings.length > 0 ? (
        <ul className="list-disc pl-10 text-xs text-muted">
          {result.warnings.map((warning, index) => (
            <li key={`${warning.code}-${warning.path}-${index}`}>{warningLabel(warning)}</li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/** Results of a multi-file import, one row per file, filled in as each upload finishes. */
export function ImportBatchList({ items, running, onAnother, onNavigate }: ImportBatchListProps) {
  const done = items.filter((item) => item.status === "done").length;
  const failed = items.filter((item) => item.status === "error").length;
  return (
    <div className="flex flex-col gap-3">
      <p role="status" className="text-sm font-medium">
        {running
          ? t("io.import.batch.progress", { done: done + failed, total: items.length })
          : t("io.import.batch.summary", { done, failed })}
      </p>
      <ul className="max-h-80 overflow-y-auto">
        {items.map((item) => (
          <BatchRow key={item.key} item={item} onNavigate={onNavigate} />
        ))}
      </ul>
      <div className="flex justify-end">
        <Button variant="outline" disabled={running} onClick={onAnother}>
          {t("io.import.another")}
        </Button>
      </div>
    </div>
  );
}
