import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  GitFork,
  Info,
  Pencil,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { MessageOut } from "@/types/chat";
import { MetaDialog } from "./MetaDialog";
import { ReasoningBlock } from "./ReasoningBlock";
import { RpText } from "./RpText";
import { NARRATOR_SPEAKER, USER_SPEAKER } from "./grouping";

type ActionResult = Promise<boolean | void> | boolean | void;

interface MessageBubbleProps {
  message: MessageOut;
  isFirstInGroup: boolean;
  isLastInGroup: boolean;
  disabled?: boolean;
  onSelectVariant?: (variantIdx: number) => ActionResult;
  onRegenerate?: (messageId: string) => void;
  onEdit?: (messageId: string, content: string) => ActionResult;
  onDelete?: (messageId: string) => ActionResult;
  onFork?: (messageId: string, seq: number) => void;
}

function resolveActionResult(
  result: ActionResult,
  onSuccess: () => void,
  onReject?: () => void,
): void {
  if (result && typeof (result as Promise<unknown>).then === "function") {
    void (result as Promise<boolean | void>).then((ok) => {
      if (ok === false) onReject?.();
      else onSuccess();
    });
  } else if (result === false) {
    onReject?.();
  } else {
    onSuccess();
  }
}

function ActionIconButton({
  label,
  title = label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  title?: string;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      disabled={disabled}
      aria-label={label}
      title={title}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

export function MessageBubble({
  message,
  isFirstInGroup,
  isLastInGroup,
  disabled = false,
  onSelectVariant,
  onRegenerate,
  onEdit,
  onDelete,
  onFork,
}: MessageBubbleProps) {
  const variantKey = `${message.active_variant}:${message.variants.length}`;
  const [picked, setPicked] = useState<{ pos: number; key: string } | null>(null);
  const [metaOpen, setMetaOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftContent, setDraftContent] = useState("");
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing) editTextareaRef.current?.focus();
  }, [editing]);

  useEffect(() => {
    if (!copied) return;
    const id = window.setTimeout(() => setCopied(false), 1500);
    return () => window.clearTimeout(id);
  }, [copied]);

  const total = message.variants.length;
  const fallback = Math.max(
    0,
    message.variants.findIndex((v) => v.idx === message.active_variant),
  );
  const activePicked = picked && picked.key === variantKey ? picked.pos : null;
  const position = Math.min(activePicked ?? fallback, Math.max(total - 1, 0));
  const variant = message.variants[position];
  const isUser = message.speaker === USER_SPEAKER;
  const isNarrator = message.speaker === NARRATOR_SPEAKER;
  const isGreeting = message.seq === 0;
  // `meta` belongs to the latest generation, so its reasoning only matches the newest variant.
  const newestIdx = Math.max(...message.variants.map((v) => v.idx), 0);
  const savedReasoning =
    variant?.idx === newestIdx && typeof message.meta?.reasoning === "string"
      ? message.meta.reasoning
      : "";
  const alwaysShowActions = isLastInGroup || total > 1 || editing || confirmDeleteOpen;

  function swipeTo(nextPos: number) {
    const target = message.variants[nextPos];
    if (!target || disabled) return;
    setPicked({ pos: nextPos, key: variantKey });
    resolveActionResult(
      onSelectVariant?.(target.idx),
      () => undefined,
      () => setPicked(null),
    );
  }

  function startEdit() {
    setDraftContent(variant?.content ?? "");
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setDraftContent(variant?.content ?? "");
  }

  function saveEdit() {
    if (disabled || draftContent.trim() === "") return;
    resolveActionResult(onEdit?.(message.id, draftContent), () => setEditing(false));
  }

  function confirmDelete() {
    if (disabled || isGreeting) return;
    resolveActionResult(onDelete?.(message.id), () => setConfirmDeleteOpen(false));
  }

  const hasMeta = Boolean(variant?.director || variant?.draft);

  function copyContent() {
    const text = variant?.content ?? "";
    if (!text) return;
    void navigator.clipboard?.writeText(text);
    setCopied(true);
  }

  const bubble = cn(
    "rounded-lg border px-3.5 py-2.5 text-fg [html[data-theme='e-ink']_&]:border-2",
    isUser ? "border-accent/60 bg-surface-2" : "border-border-subtle bg-surface",
    isNarrator && "border-border border-dashed bg-surface/40 text-center italic",
    isUser && !isFirstInGroup && "rounded-tr-sm",
    !isUser && !isNarrator && !isFirstInGroup && "rounded-tl-sm",
  );

  return (
    <div
      data-speaker={message.speaker}
      className={cn(
        "group/msg flex min-w-0 flex-col",
        isUser ? "items-end" : "items-start",
        isNarrator && "items-center",
      )}
    >
      <div
        className={cn(
          "max-w-[92%] md:max-w-[75%]",
          editing && "w-full",
          variant?.stopped && "opacity-85",
        )}
      >
        <div className={bubble}>
          {editing ? (
            <div className="flex flex-col gap-2 text-left not-italic">
              <Textarea
                ref={editTextareaRef}
                value={draftContent}
                rows={3}
                aria-label={t("chat.message.edit")}
                onChange={(e) => setDraftContent(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    e.preventDefault();
                    cancelEdit();
                  } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    saveEdit();
                  }
                }}
                className="resize-y font-content text-base md:text-base"
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-2xs text-muted">{t("chat.message.editHint")}</span>
                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={cancelEdit}>
                    {t("chat.message.cancelEdit")}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    disabled={disabled || draftContent.trim() === ""}
                    onClick={saveEdit}
                  >
                    {t("chat.message.saveEdit")}
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <>
              {!isUser ? <ReasoningBlock text={savedReasoning} saved /> : null}
              <RpText text={variant?.content ?? ""} />
              {variant?.stopped && (
                <span className="text-xs text-muted">({t("chat.message.stopped")})</span>
              )}
            </>
          )}
        </div>
        {!editing && (
          <div
            className={cn(
              "mt-1 flex flex-wrap items-center gap-1 text-muted transition-opacity duration-fast ease-ui",
              isUser && "justify-end",
              !alwaysShowActions &&
                "opacity-100 md:opacity-0 md:group-hover/msg:opacity-100 md:group-focus-within/msg:opacity-100",
            )}
          >
            {total > 1 && (
              <span className="flex items-center">
                <ActionIconButton
                  label={t("chat.message.swipePrev")}
                  disabled={disabled || position === 0}
                  onClick={() => swipeTo(position - 1)}
                >
                  <ChevronLeft aria-hidden="true" />
                </ActionIconButton>
                <span className="px-1 text-xs tabular-nums" aria-live="polite">
                  {t("chat.message.swipeCount", { index: position + 1, total })}
                </span>
                <ActionIconButton
                  label={t("chat.message.swipeNext")}
                  disabled={disabled || position >= total - 1}
                  onClick={() => swipeTo(position + 1)}
                >
                  <ChevronRight aria-hidden="true" />
                </ActionIconButton>
              </span>
            )}
            <ActionIconButton
              label={copied ? t("chat.message.copied") : t("chat.message.copy")}
              onClick={copyContent}
            >
              {copied ? <Check className="text-accent-text" aria-hidden="true" /> : <Copy aria-hidden="true" />}
            </ActionIconButton>
            {!isUser && message.seq >= 0 && (
              <ActionIconButton
                label={t("chat.message.regenerate")}
                disabled={disabled}
                onClick={() => onRegenerate?.(message.id)}
              >
                <RotateCcw aria-hidden="true" />
              </ActionIconButton>
            )}
            {!isUser && hasMeta && (
              <ActionIconButton label={t("chat.message.meta")} onClick={() => setMetaOpen(true)}>
                <Info aria-hidden="true" />
              </ActionIconButton>
            )}
            <ActionIconButton
              label={t("chat.message.edit")}
              disabled={disabled}
              onClick={startEdit}
            >
              <Pencil aria-hidden="true" />
            </ActionIconButton>
            <ActionIconButton
              label={t("chat.message.delete")}
              title={isGreeting ? t("chat.message.cannotDeleteGreeting") : t("chat.message.delete")}
              disabled={disabled || isGreeting}
              onClick={() => setConfirmDeleteOpen(true)}
            >
              <Trash2 aria-hidden="true" />
            </ActionIconButton>
            <ActionIconButton
              label={t("chat.message.fork")}
              disabled={disabled}
              onClick={() => onFork?.(message.id, message.seq)}
            >
              <GitFork aria-hidden="true" />
            </ActionIconButton>
          </div>
        )}
      </div>
      <MetaDialog open={metaOpen} onOpenChange={setMetaOpen} variant={variant} />
      {confirmDeleteOpen && (
        <Dialog open onOpenChange={(next) => (next ? undefined : setConfirmDeleteOpen(false))}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("chat.message.confirmDeleteTitle")}</DialogTitle>
              <DialogDescription>{t("chat.message.confirmDelete")}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setConfirmDeleteOpen(false)}>
                {t("chat.message.cancelEdit")}
              </Button>
              <Button type="button" variant="danger" disabled={disabled} onClick={confirmDelete}>
                {t("chat.message.confirmDeleteButton")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
