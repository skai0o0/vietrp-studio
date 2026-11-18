import { Brain, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";

interface ReasoningBlockProps {
  text: string;
  /** True while the model is still thinking (reasoning streams, reply text has not started). */
  thinking?: boolean;
  /** Saved reasoning of a finished message: no timer, collapsed by default. */
  saved?: boolean;
}

const TICK_MS = 1000;

function useThinkingSeconds(thinking: boolean, active: boolean): number {
  const startRef = useRef<number | null>(null);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!active) return;
    if (startRef.current === null) startRef.current = Date.now();
    const start = startRef.current;
    const update = () => setSeconds(Math.max(1, Math.round((Date.now() - start) / TICK_MS)));
    update();
    if (!thinking) return;
    const id = window.setInterval(update, TICK_MS);
    return () => window.clearInterval(id);
  }, [thinking, active]);

  return seconds;
}

/** Collapsible "thinking" block above a reply. Open while the model thinks, closes when the reply starts. */
export function ReasoningBlock({ text, thinking = false, saved = false }: ReasoningBlockProps) {
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const seconds = useThinkingSeconds(thinking, !saved && text !== "");
  if (text.trim() === "") return null;

  const open = userOpen ?? thinking;
  let label = t("chat.reasoning.saved");
  if (!saved) {
    label = thinking
      ? t("chat.reasoning.thinking", { seconds })
      : t("chat.reasoning.thought", { seconds });
  }

  return (
    <div data-testid="reasoning-block" className="mb-2 not-italic">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setUserOpen(!open)}
        className="flex items-center gap-1.5 rounded-md text-xs text-muted hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        <Brain
          className={cn("size-3.5", thinking && "motion-safe:animate-pulse")}
          aria-hidden="true"
        />
        <span>{label}</span>
        <ChevronDown
          className={cn(
            "size-3.5 transition-transform motion-reduce:transition-none",
            open && "rotate-180",
          )}
          aria-hidden="true"
        />
      </button>
      {open ? (
        <div className="mt-1.5 max-h-60 overflow-y-auto whitespace-pre-wrap border-l-2 border-border pl-2.5 text-left text-xs leading-relaxed text-muted">
          {text}
        </div>
      ) : null}
    </div>
  );
}
