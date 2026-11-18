import { useId, type ReactNode } from "react";
import { cn } from "@/lib/cn";

interface SectionProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** A titled form block. */
export function Section({ title, description, actions, className, children }: SectionProps) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className={cn(
        "flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 md:p-6",
        className,
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 id={headingId} className="text-base font-semibold">
            {title}
          </h2>
          {description ? <p className="text-sm text-muted">{description}</p> : null}
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}
