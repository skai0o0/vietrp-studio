import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { TOKEN_BAR_CLASS, tokenBarState } from "./tokenMath";

interface TokenBarProps {
  used: number | null;
  budget: number | null;
  onOpen: () => void;
}

/** The top bar of the composer: fill = prompt tokens / budget, inline counts & Prompt Inspector trigger. */
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
      className="group flex w-full cursor-pointer flex-col border-b border-border-subtle bg-surface-2/60 transition-colors duration-fast ease-ui hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-focus"
    >
      <span data-level={state.level} className="token-bar-track block h-1 w-full bg-border-subtle">
        <span
          data-level={state.level}
          className={cn(
            "token-bar-fill block h-full transition-[width] duration-normal ease-ui motion-reduce:transition-none",
            TOKEN_BAR_CLASS[state.level],
          )}
          style={{ width: `${state.ratio * 100}%` }}
        />
      </span>
      <span className="flex w-full items-center justify-between gap-2 px-2.5 py-1 text-2xs tabular-nums text-muted">
        <span>
          {known ? t("chat.input.tokenCountShort", { used, budget }) : t("chat.input.tokensUnknown")}
        </span>
        <span className="font-medium text-accent-text group-hover:underline">
          {t("chat.input.inspectPrompt")}
        </span>
      </span>
    </button>
  );
}
