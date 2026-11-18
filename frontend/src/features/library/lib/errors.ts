import { errorMessage, t } from "@/i18n";
import { vi } from "@/i18n/vi";
import { ApiError } from "@/lib/apiClient";

export interface ParsedApiError {
  code: string;
  /** Field-level messages (Vietnamese), keyed by the path inside `data`, e.g. `secrets.0.content`. */
  fields: Record<string, string>;
  /** Errors that could not be tied to a field (Vietnamese summary lines). */
  general: string[];
  /** Raw English detail from the server, for the technical-detail line. */
  detail: string | null;
}

const VALIDATION_PREFIXES = ["data is invalid: ", "Request validation failed: "];
const REQUEST_PATH_PREFIXES = ["body.data.", "body.", "data."];
const PATH_SEGMENT = /^([A-Za-z0-9_.-]+): (.*)$/;

/** Maps a pydantic message to Vietnamese. Unknown messages fall back to a generic one. */
export function translateFieldMessage(message: string): string {
  const text = message.replace(/^Value error, /, "");
  if (/field required/i.test(text)) return t("library.fieldErrors.required");
  if (/age is required/i.test(text)) return t("library.fieldErrors.ageRequired");
  const atLeast = text.match(/at least (\d+) character/i);
  if (atLeast) return t("library.fieldErrors.minLength", { count: atLeast[1] ?? "" });
  const atMost = text.match(/at most (\d+) character/i);
  if (atMost) return t("library.fieldErrors.maxLength", { count: atMost[1] ?? "" });
  if (/should match pattern/i.test(text)) return t("library.fieldErrors.slug");
  if (/must be lowercase/i.test(text)) return t("library.fieldErrors.lowercase");
  if (/greater than or equal to (-?\d+)/i.test(text)) {
    return t("library.fieldErrors.min", { value: text.match(/equal to (-?\d+)/i)?.[1] ?? "" });
  }
  if (/less than or equal to (-?\d+)/i.test(text)) {
    return t("library.fieldErrors.max", { value: text.match(/equal to (-?\d+)/i)?.[1] ?? "" });
  }
  if (/must be deeper than parent/i.test(text)) return t("library.fieldErrors.levelDeeper");
  if (/does not exist/i.test(text)) return t("library.fieldErrors.missingReference");
  if (/duplicate/i.test(text)) return t("library.fieldErrors.duplicate");
  return t("library.fieldErrors.invalid");
}

function stripPrefix(text: string, prefixes: readonly string[]): string {
  for (const prefix of prefixes) if (text.startsWith(prefix)) return text.slice(prefix.length);
  return text;
}

/** Parses the server's `validation_error` message: `loc: msg; loc: msg`. */
export function parseValidationMessage(
  message: string,
): Pick<ParsedApiError, "fields" | "general"> {
  const fields: Record<string, string> = {};
  const general: string[] = [];
  const body = stripPrefix(message, VALIDATION_PREFIXES);
  for (const raw of body.split("; ")) {
    const segment = raw.replace(/^: /, "").trim();
    if (!segment) continue;
    const match = segment.match(PATH_SEGMENT);
    if (match?.[1] && match[2] !== undefined) {
      const path = stripPrefix(match[1], REQUEST_PATH_PREFIXES);
      fields[path] = fields[path] ?? translateFieldMessage(match[2]);
    } else if (/^age is required/i.test(segment)) {
      fields["age"] = translateFieldMessage(segment);
    } else {
      general.push(translateFieldMessage(segment));
    }
  }
  return { fields, general };
}

export function parseApiError(error: unknown): ParsedApiError {
  if (!(error instanceof ApiError)) {
    return { code: "unknown", fields: {}, general: [], detail: null };
  }
  if (error.code === "validation_error") {
    const { fields, general } = parseValidationMessage(error.message);
    return { code: error.code, fields, general, detail: error.message };
  }
  return { code: error.code, fields: {}, general: [], detail: null };
}

/** Vietnamese text for an error code, preferring the library-specific map. */
export function libraryErrorMessage(code: string): string {
  if (Object.prototype.hasOwnProperty.call(vi.library.errors, code)) {
    return vi.library.errors[code as keyof typeof vi.library.errors];
  }
  return errorMessage(code);
}
