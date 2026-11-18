import { Check, X } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { t } from "@/i18n";
import type { MessageVariantOut } from "@/types/chat";

interface MetaDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  variant: MessageVariantOut | undefined;
}

/** Director criteria with hints, plus the rejected draft when the variant kept one. */
export function MetaDialog({ open, onOpenChange, variant }: MetaDialogProps) {
  const director = variant?.director ?? null;
  const draft = variant?.draft ?? null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto">
        <DialogTitle className="text-lg font-semibold">{t("chat.meta.title")}</DialogTitle>
        <DialogDescription className="sr-only">{t("chat.meta.title")}</DialogDescription>
        {!director && !draft && <p className="text-sm text-muted">{t("chat.meta.none")}</p>}
        {director && (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">
              {t("chat.meta.director")}:{" "}
              {director.passed ? t("chat.meta.passed") : t("chat.meta.failed")}
              {" · "}
              {t("chat.meta.score", { score: Math.round(director.score * 100) })}
              {director.attempt > 0 &&
                ` · ${t("chat.meta.attempt", { attempt: director.attempt })}`}
            </h3>
            <ul className="flex flex-col gap-1.5">
              {director.criteria.map((c) => (
                <li key={c.id} className="rounded-md border border-border bg-surface-2 p-2 text-sm">
                  <div className="flex items-center gap-2">
                    {c.passed ? (
                      <Check className="size-4 text-accent-2" aria-hidden="true" />
                    ) : (
                      <X className="size-4 text-danger" aria-hidden="true" />
                    )}
                    <span className="font-mono">{c.id}</span>
                    <span className="ml-auto text-muted">{Math.round(c.probability * 100)}%</span>
                  </div>
                  {c.hint_vi && <p className="mt-1 text-muted">{c.hint_vi}</p>}
                </li>
              ))}
            </ul>
          </section>
        )}
        {draft && (
          <section className="flex flex-col gap-1">
            <h3 className="text-sm font-medium">{t("chat.meta.draft")}</h3>
            <p className="whitespace-pre-wrap break-words font-content text-sm text-muted">
              {draft}
            </p>
          </section>
        )}
      </DialogContent>
    </Dialog>
  );
}
