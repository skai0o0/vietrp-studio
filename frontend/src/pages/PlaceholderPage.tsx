import type { ReactNode } from "react";
import { t, type MessageKey } from "@/i18n";

interface PlaceholderPageProps {
  titleKey: MessageKey;
  emptyKey: MessageKey;
  children?: ReactNode;
}

/** Title + empty state used by every route until its real feature lands. */
export function PlaceholderPage({ titleKey, emptyKey, children }: PlaceholderPageProps) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-4 md:p-8">
      <h1 className="text-2xl font-semibold">{t(titleKey)}</h1>
      <section className="flex min-h-48 flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-border bg-surface p-8 text-center">
        <p className="max-w-md text-sm text-muted">{t(emptyKey)}</p>
        {children}
      </section>
    </div>
  );
}
