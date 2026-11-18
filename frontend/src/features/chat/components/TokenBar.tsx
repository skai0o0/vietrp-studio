import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { TOKEN_BAR_CLASS, tokenBarState } from "./tokenMath";

interface TokenBarProps {
  used: number | null;
  budget: number | null;
  onOpen: () => void;
}

/** The top border of the chat textarea: fill = prompt tokens / budget. Click opens the Prompt Inspector. */
export function TokenBar({ used, budget, onOpen }: TokenBarProps) {
  const known = used !== null && budget !== null;
  const state = tokenBarState(used ?? 0, budget ?? 0);
  const label = known
    ? t("chat.input.tokenBar", { used, budget, percent: state.percent })
    : t("chat.input.tokensUnknown");
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={label}
      title={label}
      data-level={state.level}
      className="block h-3 w-full cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
    >
      <span data-level={state.level} className="token-bar-track block h-1 w-full bg-border">
        <span
          data-level={state.level}
          className={cn("token-bar-fill block h-full", TOKEN_BAR_CLASS[state.level])}
          style={{ width: `${state.ratio * 100}%` }}
        />
      </span>
    </button>
  );
}
