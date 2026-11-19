import type { MessageKey } from "@/i18n";

export interface SlashCommand {
  name: string;
  hintKey: MessageKey;
  supported: boolean;
  worldOnly?: boolean;
}

/** All chat slash commands supported in P5. */
export const SLASH_COMMANDS: readonly SlashCommand[] = [
  { name: "cmd", hintKey: "chat.commands.cmd", supported: true },
  { name: "force", hintKey: "chat.commands.force", supported: true, worldOnly: true },
  { name: "time", hintKey: "chat.commands.time", supported: true, worldOnly: true },
  { name: "move", hintKey: "chat.commands.move", supported: true, worldOnly: true },
  { name: "addnpc", hintKey: "chat.commands.addnpc", supported: true },
  { name: "removenpc", hintKey: "chat.commands.removenpc", supported: true },
  { name: "listnpc", hintKey: "chat.commands.listnpc", supported: true },
  { name: "clearnpc", hintKey: "chat.commands.clearnpc", supported: true },
];

export const CMD_HISTORY_KEY = "vietrp_cmd_history";
export const CMD_HISTORY_MAX = 20;

export function loadCommandHistory(): string[] {
  try {
    if (typeof window === "undefined" || !window.localStorage) return [];
    const raw = window.localStorage.getItem(CMD_HISTORY_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is string => typeof item === "string" && item.trim().startsWith("/"))
      .slice(0, CMD_HISTORY_MAX);
  } catch {
    return [];
  }
}

export function saveCommandHistory(commandText: string): string[] {
  const trimmed = commandText.trim();
  const current = loadCommandHistory();
  if (!trimmed.startsWith("/")) return current;
  const next = [trimmed, ...current.filter((entry) => entry !== trimmed)].slice(0, CMD_HISTORY_MAX);
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(CMD_HISTORY_KEY, JSON.stringify(next));
    }
  } catch {
    /* ignore storage failures (private mode / quota) */
  }
  return next;
}

/** The popup opens while the text is a single `/word` with no space yet. Returns the filter, or null. */
export function commandQuery(text: string): string | null {
  const match = /^\/([a-z]*)$/i.exec(text);
  return match ? (match[1] ?? "").toLowerCase() : null;
}

export function filterCommands(query: string, mode?: "single" | "world"): SlashCommand[] {
  return SLASH_COMMANDS.filter(
    (c) => c.name.startsWith(query) && !(mode === "single" && c.worldOnly),
  );
}

export function filterCommandHistory(history: readonly string[], query: string): string[] {
  const prefix = `/${query}`;
  return history.filter((entry) => entry.toLowerCase().startsWith(prefix));
}
