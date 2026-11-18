import { vi } from "@/i18n/vi";

/** Friendly label for a known secret name; unknown names show as-is. */
export function secretLabel(name: string): string {
  const names: Record<string, string> = vi.settings.apiKey.names;
  return Object.prototype.hasOwnProperty.call(names, name) ? (names[name] ?? name) : name;
}
