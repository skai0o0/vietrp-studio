import { ChevronRight, ShieldCheck } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { PromptPreview } from "@/types/chat";

/** Layer name the backend uses for the minor-safety rule (backend/app/pipeline/safety.py). */
export const SAFETY_LAYER = "minor_rule";

interface PromptInspectorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: PromptPreview | undefined;
  isLoading: boolean;
  isError: boolean;
}

export function PromptInspector({
  open,
  onOpenChange,
  preview,
  isLoading,
  isError,
}: PromptInspectorProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        hideDefaultClose
        className="flex w-full max-w-xl flex-col overflow-hidden p-0 sm:w-[90%]"
      >
        <SheetHeader title={<SheetTitle className="text-base font-semibold">{t("chat.inspector.title")}</SheetTitle>} />
        <div className="flex-1 overflow-y-auto p-4">
          <SheetDescription className="mb-3 text-sm text-muted">
            {t("chat.inspector.description")}
          </SheetDescription>
          {isLoading && <p className="text-sm text-muted">{t("chat.inspector.loading")}</p>}
          {isError && !preview && (
            <p className="text-sm text-danger-text">{t("chat.inspector.failed")}</p>
          )}
          {preview && (
            <>
              <p className="mb-3 text-sm font-medium tabular-nums">
                {t("chat.inspector.total", { used: preview.total_tokens, budget: preview.budget })}
              </p>
              <ol className="flex flex-col gap-2.5">
                {preview.layers.map((layer, i) => {
                  const safety = layer.name === SAFETY_LAYER;
                  const percent =
                    preview.total_tokens > 0
                      ? Math.round((layer.tokens / preview.total_tokens) * 100)
                      : 0;
                  return (
                    <li
                      key={`${layer.name}-${i}`}
                      data-safety={safety || undefined}
                      className={cn(
                        "rounded-lg border bg-surface-2",
                        safety ? "border-accent-2" : "border-border",
                      )}
                    >
                      <details open={safety || i < 2} className="group">
                        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                          <span className="flex min-w-0 items-center gap-1.5 font-mono text-fg">
                            <ChevronRight
                              className="size-3.5 shrink-0 text-muted transition-transform duration-fast ease-ui group-open:rotate-90 motion-reduce:transition-none"
                              aria-hidden="true"
                            />
                            {safety && (
                              <ShieldCheck className="size-4 shrink-0 text-accent-2" aria-hidden="true" />
                            )}
                            <span className="truncate">
                              {safety ? t("chat.inspector.safety") : layer.name}
                            </span>
                          </span>
                          <span className="shrink-0 tabular-nums text-muted">
                            {t("chat.inspector.layerTokens", { tokens: layer.tokens })} ·{" "}
                            {t("chat.inspector.layerPercent", { percent })}
                          </span>
                        </summary>
                        <div className="px-3 pb-3">
                          <div className="mb-2 h-1 w-full overflow-hidden rounded-full bg-surface">
                            <span
                              className={cn("block h-full", safety ? "bg-accent-2" : "bg-accent")}
                              style={{ width: `${Math.max(2, percent)}%` }}
                            />
                          </div>
                          {safety && (
                            <p className="mb-1.5 text-xs text-accent-2">
                              {t("chat.inspector.safetyHint")}
                            </p>
                          )}
                          {layer.text ? (
                            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-content text-sm text-muted">
                              {layer.text}
                            </pre>
                          ) : (
                            <p className="text-xs italic text-muted">{t("chat.inspector.empty")}</p>
                          )}
                        </div>
                      </details>
                    </li>
                  );
                })}
              </ol>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
