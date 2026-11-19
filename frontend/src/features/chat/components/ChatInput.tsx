import { FastForward, SendHorizontal, Square, TextCursorInput, Undo2 } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { useBreakpoint } from "@/lib/useBreakpoint";
import { CommandPopup } from "./CommandPopup";
import { TokenBar } from "./TokenBar";
import {
  commandQuery,
  filterCommandHistory,
  filterCommands,
  loadCommandHistory,
  saveCommandHistory,
  type SlashCommand,
} from "./commands";

/** How many sent messages the Up arrow can recall. */
const HISTORY_LIMIT = 30;

function InputIconBtn({
  label,
  variant = "ghost",
  pressed,
  disabled,
  className,
  onClick,
  children,
}: {
  label: string;
  variant?: "ghost" | "outline" | "danger" | "default";
  pressed?: boolean;
  disabled?: boolean;
  className?: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Button
      type="button"
      variant={variant}
      size="icon-sm"
      aria-pressed={pressed}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={className}
    >
      {children}
    </Button>
  );
}

interface ChatInputProps {
  mode?: "single" | "world";
  isStreaming: boolean;
  usedTokens: number | null;
  budget: number | null;
  /** Resolve false when the request failed before streaming, so the text is put back. */
  onSend: (text: string, prefill: string) => Promise<boolean | void> | void;
  onStop: () => void;
  onOpenInspector: () => void;
  onTextChange: (text: string) => void;
  onContinue?: (prefill?: string) => Promise<boolean | void> | void;
  onUndo?: () => void;
  canContinue?: boolean;
  canUndo?: boolean;
  isActionPending?: boolean;
}

export function ChatInput({
  mode,
  isStreaming,
  usedTokens,
  budget,
  onSend,
  onStop,
  onOpenInspector,
  onTextChange,
  onContinue,
  onUndo,
  canContinue = false,
  canUndo = false,
  isActionPending = false,
}: ChatInputProps) {
  const [text, setText] = useState("");
  const [prefill, setPrefill] = useState("");
  const [prefillOpen, setPrefillOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [popupDismissed, setPopupDismissed] = useState(false);
  const [cmdHistory, setCmdHistory] = useState<string[]>(() => loadCommandHistory());
  const [history, setHistory] = useState<string[]>(() => loadCommandHistory());
  const narrow = useBreakpoint() === "mobile";
  const historyPos = useRef<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    if (el.scrollHeight > 0) {
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }
  }, [text]);

  const query = commandQuery(text);
  const commands = query === null ? [] : filterCommands(query, mode);
  const historyMatches = query === null ? [] : filterCommandHistory(cmdHistory, query);
  const totalItems = historyMatches.length + commands.length;
  const popupOpen = !popupDismissed && query !== null && totalItems > 0;
  const safeActive = totalItems > 0 ? Math.min(active, totalItems - 1) : 0;

  function update(value: string) {
    setText(value);
    setActive(0);
    setPopupDismissed(false);
    historyPos.current = null;
    onTextChange(value);
  }

  function submit() {
    const body = text.trim();
    if (!body || isStreaming || isActionPending) return;
    const sentPrefill = prefillOpen ? prefill.trim() : "";
    const result = onSend(body, sentPrefill);
    if (body.startsWith("/")) {
      setCmdHistory(saveCommandHistory(body));
    }
    setHistory((h) => [body, ...h.filter((x) => x !== body)].slice(0, HISTORY_LIMIT));
    update("");
    if (sentPrefill) setPrefill("");
    void Promise.resolve(result).then((ok) => {
      if (ok !== false) return;
      // Request failed before streaming: give the typed text back (unless the user already typed anew).
      setText((current) => {
        if (current !== "") return current;
        onTextChange(body);
        return body;
      });
      if (sentPrefill) setPrefill((current) => current || sentPrefill);
    });
  }

  function handleContinue() {
    if (isStreaming || isActionPending || !onContinue) return;
    const sentPrefill = prefillOpen ? prefill.trim() : "";
    const result = onContinue(sentPrefill || undefined);
    if (sentPrefill) setPrefill("");
    void Promise.resolve(result).then((ok) => {
      if (ok === false && sentPrefill) {
        setPrefill((current) => current || sentPrefill);
      }
    });
  }

  function pick(command: SlashCommand) {
    if (command.supported) {
      update(`/${command.name} `);
      textareaRef.current?.focus();
    }
  }

  function pickHistory(entry: string) {
    setText(entry);
    setActive(0);
    setPopupDismissed(true);
    historyPos.current = null;
    onTextChange(entry);
    textareaRef.current?.focus();
  }

  function recall(direction: 1 | -1) {
    const next = (historyPos.current ?? -1) + direction;
    if (next < 0) {
      if (historyPos.current !== null) {
        historyPos.current = null;
        setPopupDismissed(false);
        setText("");
        onTextChange("");
      }
      return;
    }
    if (next >= history.length) return;
    historyPos.current = next;
    const value = history[next] ?? "";
    setPopupDismissed(true);
    setText(value);
    onTextChange(value);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (popupOpen) {
      if (event.key === "Escape") {
        event.preventDefault();
        setPopupDismissed(true);
        return;
      }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActive((i) => (i + step + totalItems) % totalItems);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        if (safeActive < historyMatches.length) {
          const entry = historyMatches[safeActive];
          if (entry !== undefined) pickHistory(entry);
        } else {
          const command = commands[safeActive - historyMatches.length];
          if (command?.supported) pick(command);
        }
        return;
      }
    } else if (text === "" || historyPos.current !== null) {
      if (event.key === "ArrowUp") {
        event.preventDefault();
        recall(1);
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        recall(-1);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  const showContinue = !isStreaming && canContinue && Boolean(onContinue) && text.trim() === "";
  const showUndo = !isStreaming && canUndo && Boolean(onUndo);

  return (
    <div className="relative border-t border-border-subtle bg-bg px-3 pb-safe pt-2 md:px-4">
      {popupOpen ? (
        <CommandPopup
          commands={commands}
          historyMatches={historyMatches}
          activeIndex={safeActive}
          onPick={pick}
          onPickHistory={pickHistory}
        />
      ) : null}
      <div className="mb-2 overflow-hidden rounded-lg border border-border bg-surface transition-colors duration-fast ease-ui focus-within:border-focus focus-within:outline focus-within:outline-1 focus-within:outline-focus">
        <TokenBar used={usedTokens} budget={budget} onOpen={onOpenInspector} />
        {prefillOpen && (
          <input
            value={prefill}
            onChange={(e) => setPrefill(e.target.value)}
            aria-label={t("chat.input.prefillLabel")}
            placeholder={t("chat.input.prefillPlaceholder")}
            className="block w-full border-b border-border-subtle bg-field px-3 py-2 font-content text-sm text-fg placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
          />
        )}
        <div className="px-2.5 pt-2">
          <textarea
            ref={textareaRef}
            value={text}
            rows={1}
            onChange={(e) => update(e.target.value)}
            onKeyDown={onKeyDown}
            aria-label={t("chat.input.label")}
            aria-controls={popupOpen ? "chat-command-list" : undefined}
            placeholder={narrow ? t("chat.input.placeholderShort") : t("chat.input.placeholder")}
            className="max-h-40 min-h-10 w-full resize-none bg-transparent font-content text-base text-fg placeholder:text-muted focus-visible:outline-none"
          />
        </div>
        <div className="flex items-center justify-between gap-2 px-2 pb-1.5 pt-0.5">
          <div className="flex items-center gap-1">
            <InputIconBtn
              label={t("chat.input.prefillToggle")}
              pressed={prefillOpen}
              className={cn(prefillOpen && "text-accent-2")}
              onClick={() => setPrefillOpen((v) => !v)}
            >
              <TextCursorInput aria-hidden="true" />
            </InputIconBtn>
            {showUndo && onUndo && (
              <InputIconBtn label={t("chat.input.undo")} disabled={isActionPending} onClick={onUndo}>
                <Undo2 aria-hidden="true" />
              </InputIconBtn>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {showContinue && (
              <InputIconBtn
                label={t("chat.input.continue")}
                variant="outline"
                disabled={isActionPending}
                onClick={handleContinue}
              >
                <FastForward aria-hidden="true" />
              </InputIconBtn>
            )}
            {isStreaming ? (
              <InputIconBtn label={t("chat.input.stop")} variant="danger" onClick={onStop}>
                <Square aria-hidden="true" />
              </InputIconBtn>
            ) : (
              <InputIconBtn
                label={t("chat.input.send")}
                variant="default"
                disabled={text.trim() === "" || isActionPending}
                onClick={submit}
              >
                <SendHorizontal aria-hidden="true" />
              </InputIconBtn>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
