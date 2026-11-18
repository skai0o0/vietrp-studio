import { AlertCircle, Loader2, Send, Sparkles, Wand2 } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { errorMessage, t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { CreatorMessage, TargetType } from "./types";

export interface ChatCreatorSectionProps {
  targetType: TargetType;
  messages: readonly CreatorMessage[];
  streamingReply: string;
  isStreaming: boolean;
  isGenerating: boolean;
  errorCode: string | null;
  onSendMessage: (text: string) => Promise<boolean>;
  onFinalize: () => void;
}

/** Conversational interview panel with live SSE streaming and "Chốt & Tạo" action. */
export function ChatCreatorSection({
  targetType,
  messages,
  streamingReply,
  isStreaming,
  isGenerating,
  errorCode,
  onSendMessage,
  onFinalize,
}: ChatCreatorSectionProps) {
  const [draft, setDraft] = useState("");
  const inputId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const busy = isStreaming || isGenerating;
  const showSettingsLink =
    errorCode === "openrouter_key_missing" || errorCode === "llm_auth_failed";

  const starters =
    targetType === "character"
      ? [t("create.chat.starterCharacter1"), t("create.chat.starterCharacter2")]
      : [t("create.chat.starterWorld1"), t("create.chat.starterWorld2")];

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "auto", block: "nearest" });
  }, [messages.length, streamingReply, isStreaming]);

  async function submit(): Promise<void> {
    const trimmed = draft.trim();
    if (!trimmed || busy) return;
    setDraft("");
    const ok = await onSendMessage(trimmed);
    if (!ok) {
      setDraft(trimmed);
    }
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <section
      data-testid="creator-chat-section"
      className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 md:p-5"
    >
      <header className="flex flex-col gap-1">
        <h2 className="text-base font-semibold">{t("create.chat.title")}</h2>
        <p className="text-xs text-muted">{t("create.chat.subtitle")}</p>
      </header>

      <div
        role="log"
        aria-live="polite"
        data-testid="creator-chat-messages"
        className="flex min-h-72 max-h-[28rem] flex-col gap-3 overflow-y-auto rounded-md border border-border bg-bg p-3 md:p-4"
      >
        {messages.length === 0 && !isStreaming ? (
          <div className="my-auto flex flex-col gap-3 py-4">
            <div className="flex flex-col gap-1">
              <p className="text-sm font-medium">{t("create.chat.emptyTitle")}</p>
              <p className="text-xs text-muted">{t("create.chat.emptyHint")}</p>
            </div>
            <div className="flex flex-col gap-2">
              {starters.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setDraft(prompt);
                    textareaRef.current?.focus();
                  }}
                  className="rounded-md border border-border bg-surface px-3 py-2 text-left font-content text-xs leading-relaxed text-fg hover:border-accent hover:bg-surface-2 disabled:opacity-50"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {messages.map((msg, idx) => {
          const isUser = msg.role === "user";
          return (
            <div
              key={`${msg.role}-${idx}`}
              className={cn("flex flex-col gap-1", isUser ? "items-end" : "items-start")}
            >
              <span className="flex items-center gap-1 px-1 text-[11px] font-medium text-muted">
                {!isUser ? <Sparkles className="size-3 text-accent" aria-hidden="true" /> : null}
                {isUser ? t("create.chat.you") : t("create.chat.assistant")}
              </span>
              <div
                className={cn(
                  "max-w-[90%] rounded-lg border px-3.5 py-2.5 font-content text-sm leading-relaxed whitespace-pre-wrap break-words",
                  isUser ? "border-accent-2/50 bg-surface-2" : "border-border bg-surface",
                )}
              >
                {msg.content}
              </div>
            </div>
          );
        })}

        {isStreaming ? (
          <div className="flex flex-col items-start gap-1" data-testid="creator-chat-streaming">
            <span className="flex items-center gap-1 px-1 text-[11px] font-medium text-muted">
              <Loader2 className="size-3 text-accent motion-safe:animate-spin" aria-hidden="true" />
              {t("create.chat.assistant")}
            </span>
            <div className="max-w-[90%] rounded-lg border border-accent/60 bg-surface px-3.5 py-2.5 font-content text-sm leading-relaxed whitespace-pre-wrap break-words">
              {streamingReply || <span className="text-muted">{t("create.chat.streaming")}</span>}
            </div>
          </div>
        ) : null}

        <div ref={endRef} />
      </div>

      {errorCode ? (
        <div
          role="alert"
          data-testid="creator-chat-error"
          className="flex flex-col gap-2 rounded-md border-2 border-danger bg-surface-2 p-3 text-xs"
        >
          <div className="flex items-start gap-2">
            <AlertCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
            <span>{errorMessage(errorCode)}</span>
          </div>
          {showSettingsLink ? (
            <Link
              to="/settings"
              className="w-fit font-medium text-accent-2 underline-offset-4 hover:underline"
            >
              {t("library.judge.openSettings")}
            </Link>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-col gap-3">
        <label htmlFor={inputId} className="sr-only">
          {t("create.chat.inputLabel")}
        </label>
        <textarea
          ref={textareaRef}
          id={inputId}
          rows={3}
          disabled={busy}
          value={draft}
          placeholder={t("create.chat.inputPlaceholder")}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          className="flex min-h-20 w-full resize-y rounded-md border border-border bg-bg px-3 py-2 font-content text-sm text-fg placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-50"
        />

        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={busy || !draft.trim()}
            onClick={() => void submit()}
            className="min-h-10"
          >
            <Send className="size-4" aria-hidden="true" />
            {t("create.chat.send")}
          </Button>
          <Button
            type="button"
            disabled={busy}
            onClick={onFinalize}
            className="min-h-11 shadow-glow"
          >
            {isGenerating ? (
              <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" />
            ) : (
              <Wand2 className="size-4" aria-hidden="true" />
            )}
            {isGenerating ? t("create.chat.finalizing") : t("create.chat.finalize")}
          </Button>
        </div>
      </div>
    </section>
  );
}
