import { ShieldCheck } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
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
      <SheetContent side="right" className="w-full max-w-xl overflow-y-auto p-4 sm:w-[90%]">
        <SheetTitle className="pr-10 text-lg font-semibold">{t("chat.inspector.title")}</SheetTitle>
        <SheetDescription className="text-sm text-muted">
          {t("chat.inspector.description")}
        </SheetDescription>
        {isLoading && <p className="text-sm text-muted">{t("chat.inspector.loading")}</p>}
        {isError && !preview && <p className="text-sm text-danger">{t("chat.inspector.failed")}</p>}
        {preview && (
          <>
            <p className="text-sm font-medium">
              {t("chat.inspector.total", { used: preview.total_tokens, budget: preview.budget })}
            </p>
            <ol className="flex flex-col gap-3">
              {preview.layers.map((layer, i) => {
                const safety = layer.name === SAFETY_LAYER;
                return (
                  <li
                    key={`${layer.name}-${i}`}
                    data-safety={safety || undefined}
                    className={cn(
                      "rounded-lg border bg-surface-2 p-3",
                      safety ? "border-accent-2" : "border-border",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="flex items-center gap-1 font-mono text-fg">
                        {safety && (
                          <ShieldCheck className="size-4 text-accent-2" aria-hidden="true" />
                        )}
                        {safety ? t("chat.inspector.safety") : layer.name}
                      </span>
                      <span className="text-muted">
                        {t("chat.inspector.layerTokens", { tokens: layer.tokens })}
                      </span>
                    </div>
                    {safety && (
                      <p className="mt-1 text-xs text-accent-2">{t("chat.inspector.safetyHint")}</p>
                    )}
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-content text-sm text-muted">
                      {layer.text}
                    </pre>
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
