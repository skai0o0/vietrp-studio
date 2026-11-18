import { ShieldCheck } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { CastMemberSummary, PromptPreview } from "@/types/chat";
import { SAFETY_LAYER } from "../components/PromptInspector";

interface WorldPromptInspectorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: PromptPreview | undefined;
  isLoading: boolean;
  isError: boolean;
  speaker: string;
  onSpeakerChange: (speaker: string) => void;
  cast: readonly CastMemberSummary[];
}

export function WorldPromptInspector({
  open,
  onOpenChange,
  preview,
  isLoading,
  isError,
  speaker,
  onSpeakerChange,
  cast,
}: WorldPromptInspectorProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-xl overflow-y-auto p-4 sm:w-[90%]">
        <SheetTitle className="pr-10 text-lg font-semibold">{t("chat.inspector.title")}</SheetTitle>
        <SheetDescription className="text-sm text-muted">
          {t("chat.inspector.description")}
        </SheetDescription>
        <div className="flex flex-col gap-1">
          <Label htmlFor="inspector-speaker">{t("worldChat.previewSpeaker")}</Label>
          <select
            id="inspector-speaker"
            value={speaker}
            onChange={(e) => onSpeakerChange(e.target.value)}
            className="h-10 w-full rounded-md border border-border bg-surface px-3 text-sm text-fg"
          >
            <option value="group">{t("worldChat.groupSpeaker")}</option>
            <option value="narrator">{t("chat.message.narrator")}</option>
            {cast.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
        {isLoading ? <p className="text-sm text-muted">{t("chat.inspector.loading")}</p> : null}
        {isError && !preview ? (
          <p className="text-sm text-danger">{t("chat.inspector.failed")}</p>
        ) : null}
        {preview ? (
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
                        {safety ? (
                          <ShieldCheck className="size-4 text-accent-2" aria-hidden="true" />
                        ) : null}
                        {safety ? t("chat.inspector.safety") : layer.name}
                      </span>
                      <span className="text-muted">
                        {t("chat.inspector.layerTokens", { tokens: layer.tokens })}
                      </span>
                    </div>
                    {safety ? (
                      <p className="mt-1 text-xs text-accent-2">{t("chat.inspector.safetyHint")}</p>
                    ) : null}
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-content text-sm text-muted">
                      {layer.text}
                    </pre>
                  </li>
                );
              })}
            </ol>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
