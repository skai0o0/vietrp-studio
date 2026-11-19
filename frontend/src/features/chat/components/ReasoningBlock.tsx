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
  /** Director rewrite attempt counter; changing resets the thinking timer cleanly. */
  attempt?: number;
}

const TICK_MS = 1000;

function useThinkingSeconds(thinking: boolean, active: boolean, attempt: number): number {
  const startRef = useRef<number | null>(null);
  const prevAttemptRef = useRef<number>(attempt);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (prevAttemptRef.current !== attempt) {
      prevAttemptRef.current = attempt;
      startRef.current = null;
    }
    if (!active) return;
    if (startRef.current === null) startRef.current = Date.now();
    const start = startRef.current;
    const update = () => setSeconds(Math.max(1, Math.round((Date.now() - start) / TICK_MS)));
    update();
    if (!thinking) return;
    const id = window.setInterval(update, TICK_MS);
    return () => window.clearInterval(id);
  }, [thinking, active, attempt]);

  return seconds;
}

/** Collapsible "thinking" block above a reply. Open while the model thinks, closes when the reply starts. */
export function ReasoningBlock({
  text,
  thinking = false,
  saved = false,
  attempt = 0,
}: ReasoningBlockProps) {
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const seconds = useThinkingSeconds(thinking, !saved && text !== "", attempt);
  const open = userOpen ?? thinking;

  useEffect(() => {
    if (thinking && open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [text, thinking, open]);

  if (text.trim() === "") return null;

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
            "size-3.5 transition-transform duration-fast ease-ui motion-reduce:transition-none",
            open && "rotate-180",
          )}
          aria-hidden="true"
        />
      </button>
      {open ? (
        <div
          ref={scrollRef}
          className="mt-1.5 max-h-60 overflow-y-auto whitespace-pre-wrap border-l-2 border-border pl-2.5 text-left text-xs leading-relaxed text-muted"
        >
          {text}
        </div>
      ) : null}
    </div>
  );
}
