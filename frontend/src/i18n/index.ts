import { vi, type ErrorCode, type MessageKey } from "./vi";

export type { ErrorCode, MessageKey };

export type MessageParams = Record<string, string | number>;

function lookup(key: string): string | undefined {
  let node: unknown = vi;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

/** Typed translation lookup. `{name}` placeholders are replaced from `params`. */
export function t(key: MessageKey, params?: MessageParams): string {
  const template = lookup(key) ?? key;
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    return value === undefined ? match : String(value);
  });
}

/** Maps a backend error code to Vietnamese, with a generic fallback for unknown codes. */
export function errorMessage(code: string | null | undefined): string {
  if (code && Object.prototype.hasOwnProperty.call(vi.errors, code)) {
    return vi.errors[code as ErrorCode];
  }
  return vi.errors.unknown;
}
