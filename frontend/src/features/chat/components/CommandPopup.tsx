import { History } from "lucide-react";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { SlashCommand } from "./commands";

interface CommandPopupProps {
  commands: readonly SlashCommand[];
  historyMatches?: readonly string[];
  activeIndex: number;
  onPick: (command: SlashCommand) => void;
  onPickHistory?: (entry: string) => void;
}

const MENU_ITEM_CLS =
  "flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm transition-colors duration-fast ease-ui hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus";
const MENU_HEADER_CLS =
  "border-b border-border-subtle bg-surface-2 px-3 py-1 text-2xs font-medium uppercase tracking-wide text-muted";

export function CommandPopup({
  commands,
  historyMatches = [],
  activeIndex,
  onPick,
  onPickHistory,
}: CommandPopupProps) {
  if (commands.length === 0 && historyMatches.length === 0) return null;
  const hasHistory = historyMatches.length > 0 && Boolean(onPickHistory);

  return (
    <ul
      role="listbox"
      id="chat-command-list"
      aria-label={t("chat.input.commandsLabel")}
      className="absolute inset-x-3 bottom-full z-popover mb-1 max-h-60 overflow-y-auto rounded-lg border border-border bg-surface-3 shadow-popover md:inset-x-4"
    >
      {hasHistory ? (
        <>
          <li role="presentation" className={MENU_HEADER_CLS}>
            {t("chat.input.historySection")}
          </li>
          {historyMatches.map((entry, i) => {
            const active = i === activeIndex;
            return (
              <li key={`h:${entry}`} role="option" aria-selected={active}>
                <button
                  type="button"
                  data-eink-active={active || undefined}
                  onClick={() => onPickHistory?.(entry)}
                  className={cn(MENU_ITEM_CLS, active && "bg-surface-2")}
                >
                  <History className="size-3.5 shrink-0 text-muted" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate font-mono text-fg">{entry}</span>
                </button>
              </li>
            );
          })}
          {commands.length > 0 ? (
            <li role="presentation" className={cn(MENU_HEADER_CLS, "border-t")}>
              {t("chat.input.commandsSection")}
            </li>
          ) : null}
        </>
      ) : null}

      {commands.map((command, i) => {
        const idx = (hasHistory ? historyMatches.length : 0) + i;
        const active = idx === activeIndex;
        return (
          <li
            key={command.name}
            role="option"
            aria-selected={active}
            aria-disabled={!command.supported}
          >
            <button
              type="button"
              disabled={!command.supported}
              data-eink-active={active || undefined}
              onClick={() => onPick(command)}
              className={cn(
                MENU_ITEM_CLS,
                "gap-3",
                active && "bg-surface-2",
                !command.supported && "opacity-50",
              )}
            >
              <span className="font-mono text-accent-2">/{command.name}</span>
              <span className="min-w-0 flex-1 truncate text-muted">{t(command.hintKey)}</span>
              {!command.supported && (
                <span className="text-xs text-muted">{t("chat.input.unsupported")}</span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
