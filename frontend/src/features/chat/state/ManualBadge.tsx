import { Pencil, Pin } from "lucide-react";
import { t } from "@/i18n";

const badgeClass =
  "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[11px] font-medium";

export function ManualBadge({ visible = true }: { visible?: boolean }) {
  if (!visible) return null;
  return (
    <span className={`${badgeClass} border-accent-2 text-fg`}>
      <Pencil className="size-3" aria-hidden="true" />
      {t("stateEditor.manualBadge")}
    </span>
  );
}

export function PinnedBadge({ visible = true }: { visible?: boolean }) {
  if (!visible) return null;
  return (
    <span
      title={t("stateEditor.bonds.pinnedNote")}
      className={`${badgeClass} border-border bg-surface-2 text-muted`}
    >
      <Pin className="size-3" aria-hidden="true" />
      {t("stateEditor.bonds.pinnedBadge")}
    </span>
  );
}
