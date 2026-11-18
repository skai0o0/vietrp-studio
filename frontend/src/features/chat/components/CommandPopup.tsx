import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { SlashCommand } from "./commands";

interface CommandPopupProps {
  commands: SlashCommand[];
  activeIndex: number;
  onPick: (command: SlashCommand) => void;
}

export function CommandPopup({ commands, activeIndex, onPick }: CommandPopupProps) {
  if (commands.length === 0) return null;
  return (
    <ul
      role="listbox"
      id="chat-command-list"
      aria-label={t("chat.input.commandsLabel")}
      className="absolute inset-x-3 bottom-full z-10 mb-1 overflow-hidden rounded-lg border border-border bg-surface md:inset-x-4"
    >
      {commands.map((command, i) => (
        <li
          key={command.name}
          role="option"
          aria-selected={i === activeIndex}
          aria-disabled={!command.supported}
        >
          <button
            type="button"
            disabled={!command.supported}
            onClick={() => onPick(command)}
            className={cn(
              "flex w-full items-center gap-3 px-3 py-2 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus",
              i === activeIndex && "bg-surface-2",
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
      ))}
    </ul>
  );
}
