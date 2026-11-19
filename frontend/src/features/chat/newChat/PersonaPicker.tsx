import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { usePersonas } from "@/features/library/hooks";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";

interface PersonaPickerProps {
  value: string | null;
  onChange: (id: string | null) => void;
}

export function PersonaPicker({ value, onChange }: PersonaPickerProps) {
  const personas = usePersonas();
  const items = personas.data ?? [];
  return (
    <section aria-labelledby="newchat-persona" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="newchat-persona" className="text-sm font-semibold">
          {t("newChat.step.persona")}
        </h2>
        <Link to="/library/personas/new" className="text-xs font-medium text-accent underline">
          {t("newChat.createPersona")}
        </Link>
      </div>
      <div role="radiogroup" aria-labelledby="newchat-persona" className="flex flex-wrap gap-2">
        <Choice selected={value === null} onSelect={() => onChange(null)}>
          {t("newChat.noPersona")}
        </Choice>
        {items.map((persona) => (
          <Choice
            key={persona.id}
            selected={value === persona.id}
            onSelect={() => onChange(persona.id)}
          >
            {persona.data.name}
          </Choice>
        ))}
      </div>
      {personas.isSuccess && items.length === 0 ? (
        <p className="text-xs text-muted">{t("newChat.personaNone")}</p>
      ) : null}
    </section>
  );
}

function Choice(props: { selected: boolean; onSelect: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={props.selected}
      onClick={props.onSelect}
      className={cn(
        "rounded-md border px-3 py-2 text-sm",
        props.selected
          ? "border-accent bg-surface-2 text-fg"
          : "border-border text-muted hover:bg-surface-2",
      )}
    >
      {props.children}
    </button>
  );
}
