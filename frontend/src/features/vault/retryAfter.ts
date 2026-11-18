import { t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";

/** Localized "retry after N seconds" note for a 429 that carried Retry-After, else "". */
export function retryAfterNote(error: unknown): string {
  if (error instanceof ApiError && error.retryAfter !== undefined) {
    return ` ${t("vault.unlock.retryAfter", { seconds: Math.ceil(error.retryAfter) })}`;
  }
  return "";
}
