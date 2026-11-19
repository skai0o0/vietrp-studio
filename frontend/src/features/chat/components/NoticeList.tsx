import { X } from "lucide-react";
import { useState } from "react";
import { errorMessage, t, type MessageKey } from "@/i18n";
import type { NoticeEvent } from "@/types/chat";

interface NoticeListProps {
  notices: readonly NoticeEvent[];
  errorCode: string | null;
  errorNonce?: number;
}

const DETAIL_NOTICE_CODES = new Set([
  "time_updated",
  "location_moved",
  "move_target_unknown",
  "npc_added",
  "npc_removed",
  "npc_not_found",
  "npc_cleared",
]);

function lookupText(group: "notices" | "errors", code: string): string | null {
  const key = `chat.${group}.${code}` as MessageKey;
  const text = t(key);
  // `t` echoes the key for unknown codes.
  return text === key ? null : text;
}

function noticeText(notice: NoticeEvent): string {
  const base = lookupText("notices", notice.code) ?? errorMessage(notice.code);
  const detail = notice.detail?.trim() ?? "";
  if (notice.code === "npc_listed") {
    return `${base}: ${detail || t("chat.notices.npc_listedEmpty")}`;
  }
  if (notice.code === "command_invalid" && detail) {
    return `${base}: /${detail}`;
  }
  if (DETAIL_NOTICE_CODES.has(notice.code) && detail) {
    return `${base}: ${detail}`;
  }
  return base;
}

function chatErrorText(code: string): string {
  return lookupText("errors", code) ?? errorMessage(code);
}

/** Pinned inline status/error strip above the chat input. Each item can be dismissed. */
export function NoticeList({ notices, errorCode, errorNonce = 0 }: NoticeListProps) {
  const [dismissedNotices, setDismissedNotices] = useState<ReadonlySet<NoticeEvent>>(
    () => new Set(),
  );
  const errorKey = `${errorCode ?? ""}:${errorNonce}`;
  const [prevErrorKey, setPrevErrorKey] = useState<string>(errorKey);
  const [dismissedError, setDismissedError] = useState(false);

  if (errorKey !== prevErrorKey) {
    setPrevErrorKey(errorKey);
    setDismissedError(false);
  }

  const noticeItems = notices
    .filter((n) => !dismissedNotices.has(n))
    .map((n, i) => ({
      id: `n${i}:${n.code}:${n.detail ?? ""}`,
      text: noticeText(n),
      error: false as const,
      dismiss: () => setDismissedNotices((s) => new Set(s).add(n)),
    }));
  const errorItems =
    errorCode && !dismissedError
      ? [
          {
            id: `e:${errorKey}`,
            text: chatErrorText(errorCode),
            error: true as const,
            dismiss: () => setDismissedError(true),
          },
        ]
      : [];
  const items = [...noticeItems, ...errorItems];
  if (items.length === 0) return null;
  return (
    <div className="mx-auto w-full max-w-3xl px-3 pb-2 md:px-6">
      <ul className="flex flex-col items-stretch gap-1" aria-label={t("chat.stream.noticesLabel")}>
        {items.map((item) => (
          <li
            key={item.id}
            role={item.error ? "alert" : "status"}
            className="flex max-w-full items-center justify-between gap-2 rounded-md border border-border bg-surface-2 px-3 py-1.5 text-xs text-muted data-[error=true]:border-danger data-[error=true]:text-danger-text"
            data-error={item.error}
          >
            <span className="min-w-0 break-words">{item.text}</span>
            <button
              type="button"
              aria-label={t("chat.stream.dismiss")}
              onClick={item.dismiss}
              className="shrink-0 rounded-sm p-0.5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            >
              <X className="size-3.5" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
