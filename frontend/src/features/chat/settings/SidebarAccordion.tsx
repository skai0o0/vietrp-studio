import { ChevronRight } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";

export interface SidebarAccordionProps {
  title: string;
  summary?: string | null;
  dirty?: boolean;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

/** Flat, mobile-friendly accordion row designed for stacked sidebar panels. */
export function SidebarAccordion({
  title,
  summary,
  dirty = false,
  defaultOpen = false,
  open: controlledOpen,
  onOpenChange,
  className,
  bodyClassName,
  children,
}: SidebarAccordionProps) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const open = controlledOpen ?? internalOpen;
  const titleId = useId();
  const panelId = useId();

  function toggle() {
    const next = !open;
    if (controlledOpen === undefined) {
      setInternalOpen(next);
    }
    onOpenChange?.(next);
  }

  return (
    <section className={cn("border-b border-border-subtle last:border-b-0", className)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={toggle}
        className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left transition-colors duration-fast ease-ui hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-[-2px]"
      >
        <ChevronRight
          className={cn(
            "size-4 shrink-0 text-muted transition-transform duration-fast ease-ui motion-reduce:transition-none",
            open && "rotate-90 text-fg",
          )}
          aria-hidden="true"
        />
        <span className="flex min-w-0 flex-1 items-center gap-1.5">
          <span id={titleId} className="truncate text-sm font-medium text-fg">
            {title}
          </span>
          {dirty && (
            <span
              className="inline-flex shrink-0 items-center gap-1 rounded border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-2xs font-medium text-accent-text"
              title={t("stateEditor.accordion.dirtyLabel")}
            >
              <span aria-hidden="true">*</span>
              <span>{t("stateEditor.dirtyBadge")}</span>
            </span>
          )}
        </span>
        {summary && (
          <span className="max-w-[42%] shrink-0 truncate text-xs text-muted">{summary}</span>
        )}
      </button>
      {open && (
        <div
          id={panelId}
          role="region"
          aria-labelledby={titleId}
          className={cn("px-3 pb-3 pt-1", bodyClassName)}
        >
          {children}
        </div>
      )}
    </section>
  );
}
