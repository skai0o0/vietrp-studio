import { AlertTriangle, Globe, Lock } from "lucide-react";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { Visibility } from "@/types/library";

/** Route segment used for "create" on the detail routes. */
export const NEW_ID = "new";

const badgeClass =
  "inline-flex items-center gap-1 rounded-sm border border-border px-1.5 py-0.5 text-xs font-medium";

export function VisibilityBadge({ visibility }: { visibility: Visibility }) {
  const Icon = visibility === "public" ? Globe : Lock;
  return (
    <span className={cn(badgeClass, "text-muted")}>
      <Icon className="size-3" aria-hidden="true" />
      {visibility === "public" ? t("library.badge.public") : t("library.badge.private")}
    </span>
  );
}

export function NeedsAgeBadge() {
  return (
    <span className={cn(badgeClass, "border-2 border-accent-2 text-fg")}>
      <AlertTriangle className="size-3" aria-hidden="true" />
      {t("library.badge.needsAge")}
    </span>
  );
}
