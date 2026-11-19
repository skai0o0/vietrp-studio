import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Archive, Check, ChevronRight, Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage, t, type MessageKey } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import { cn } from "@/lib/cn";
import { chatApi } from "../api";
import * as chatHooks from "../hooks";
import { useChatStreamStore } from "../store";
import { ManualBadge } from "./ManualBadge";

export const MAX_MEMORABLE_EVENTS = 24;

export type MemorableEventItem = { id: string; title: string; content: string };

export interface MemorySectionProps {
  chatId: string;
  summary: string;
  summaryUpto: number;
  events: readonly unknown[];
  isStreaming?: boolean;
  pending?: boolean;
  isManualSummary?: boolean;
  isManualEvents?: boolean;
  embedded?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
  onSaveSummary: (summary: string) => void;
  onSaveEvents: (events: MemorableEventItem[]) => void;
}

function useFallbackSummarizeChat(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => chatApi.summarize(id),
    onSuccess: (chat) => {
      client.setQueryData(["chats", "detail", id], chat);
      void client.invalidateQueries({ queryKey: ["chats", "messages", id] });
      void client.invalidateQueries({ queryKey: ["chats", "detail", id] });
    },
  });
}

function resolveOptionalHook<T>(getter: () => T, fallback: T): T {
  try {
    const candidate = getter();
    return typeof candidate === "function" ? candidate : fallback;
  } catch {
    return fallback;
  }
}

const useResolvedSummarizeChat = resolveOptionalHook(
  () => chatHooks.useSummarizeChat,
  useFallbackSummarizeChat,
);

function slugifyEventId(title: string, existingIds: ReadonlySet<string>): string {
  const ascii = title
    .normalize("NFC")
    .trim()
    .toLowerCase()
    .replace(/đ/g, "d")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 37)
    .replace(/_+$/g, "");
  const base = `sk_${ascii || "event"}`;
  if (!existingIds.has(base)) return base;
  for (let suffix = 2; suffix < 1000; suffix += 1) {
    const tag = `_${suffix}`;
    const candidate = `${base.slice(0, 40 - tag.length)}${tag}`;
    if (!existingIds.has(candidate)) return candidate;
  }
  return `${base.slice(0, 35)}_${existingIds.size}`;
}

export function normalizeMemorableEvents(rawEvents: readonly unknown[]): MemorableEventItem[] {
  const usedIds = new Set<string>();
  const out: MemorableEventItem[] = [];
  for (const raw of rawEvents) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) continue;
    const obj = raw as Record<string, unknown>;
    const rawTitle = typeof obj.title === "string" ? obj.title.trim() : "";
    const rawContent =
      typeof obj.content === "string"
        ? obj.content.trim()
        : typeof obj.text === "string"
          ? obj.text.trim()
          : "";
    if (!rawTitle && !rawContent) continue;
    const title = rawTitle || rawContent.slice(0, 40);
    const content = rawContent || title;
    const rawId = typeof obj.id === "string" ? obj.id.trim() : "";
    const id = rawId && !usedIds.has(rawId) ? rawId : slugifyEventId(title, usedIds);
    usedIds.add(id);
    out.push({ id, title, content });
  }
  return out.slice(0, MAX_MEMORABLE_EVENTS);
}

function resolveSummarizeError(err: unknown): string {
  const rawCode =
    err instanceof ApiError
      ? err.code
      : typeof err === "object" && err !== null && "code" in err
        ? (err as { code?: unknown }).code
        : null;
  const code = typeof rawCode === "string" ? rawCode : null;
  if (code) {
    const chatKey = `chat.errors.${code}` as MessageKey;
    const chatText = t(chatKey);
    if (chatText !== chatKey) return chatText;
  }
  return errorMessage(code);
}

/** Reusable memory panel: manual Archivist compression, editable summary, and up to 24 memorable events. */
export function MemorySection({
  chatId,
  summary,
  summaryUpto,
  events,
  isStreaming = false,
  pending = false,
  isManualSummary = false,
  isManualEvents = false,
  embedded = false,
  onDirtyChange,
  onSaveSummary,
  onSaveEvents,
}: MemorySectionProps) {
  const summarize = useResolvedSummarizeChat(chatId);
  const [summarizeSuccess, setSummarizeSuccess] = useState(false);

  const normalizedEvents = normalizeMemorableEvents(events);
  const eventsKey = JSON.stringify(normalizedEvents);
  const [summaryOverride, setSummaryOverride] = useState<{ key: string; value: string } | null>(
    null,
  );
  const [eventsOverride, setEventsOverride] = useState<{
    key: string;
    value: MemorableEventItem[];
  } | null>(null);
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newContent, setNewContent] = useState("");

  const draftSummary =
    summaryOverride && summaryOverride.key === summary ? summaryOverride.value : summary;
  const draftEvents =
    eventsOverride && eventsOverride.key === eventsKey ? eventsOverride.value : normalizedEvents;

  const summaryDirty = draftSummary !== summary;
  const eventsDirty = JSON.stringify(draftEvents) !== eventsKey;
  const anyDirty = summaryDirty || eventsDirty;
  useEffect(() => {
    onDirtyChange?.(anyDirty);
  }, [anyDirty, onDirtyChange]);

  const isBusy = Boolean(pending || isStreaming || summarize.isPending);
  const summarizeDisabled = Boolean(isStreaming || summarize.isPending);
  const canAddEvent =
    (newTitle.trim() !== "" || newContent.trim() !== "") &&
    draftEvents.length < MAX_MEMORABLE_EVENTS &&
    !isBusy;

  function updateEvents(updater: (prev: MemorableEventItem[]) => MemorableEventItem[]): void {
    setEventsOverride((prev) => {
      const current = prev && prev.key === eventsKey ? prev.value : normalizedEvents;
      return { key: eventsKey, value: updater(current) };
    });
  }

  function updateEventField(idx: number, field: "title" | "content", value: string): void {
    updateEvents((prev) => prev.map((item, i) => (i === idx ? { ...item, [field]: value } : item)));
  }

  function handleSummarize(): void {
    setSummarizeSuccess(false);
    summarize.mutate(undefined, {
      onSuccess: () => {
        useChatStreamStore.getState().clearMemory(chatId);
        setSummaryOverride(null);
        setEventsOverride(null);
        setSummarizeSuccess(true);
      },
    });
  }

  function handleAddEvent(): void {
    const rawTitle = newTitle.trim();
    const rawContent = newContent.trim();
    if ((!rawTitle && !rawContent) || draftEvents.length >= MAX_MEMORABLE_EVENTS) return;
    const title = rawTitle || rawContent.slice(0, 40);
    const content = rawContent || title;
    const id = slugifyEventId(title, new Set(draftEvents.map((ev) => ev.id)));
    updateEvents((prev) => [...prev, { id, title, content }]);
    setNewTitle("");
    setNewContent("");
    setAddOpen(false);
    setExpandedEventId(id);
  }

  const Container = embedded ? "div" : "section";

  return (
    <Container
      {...(!embedded ? { "aria-labelledby": "state-memory-heading" } : {})}
      className={cn(
        "flex flex-col gap-4",
        !embedded && "rounded-lg border border-border bg-surface p-3",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        {!embedded ? (
          <h3 id="state-memory-heading" className="text-sm font-semibold">
            {t("stateEditor.memory.title")}
          </h3>
        ) : (
          <span className="text-xs font-medium text-muted">
            {t("stateEditor.memory.summaryLabel")}
          </span>
        )}
        {summaryUpto > 0 ? (
          <span className="inline-flex items-center gap-1 rounded-sm border border-border bg-surface-2 px-2 py-0.5 text-2xs font-medium text-fg">
            <Archive className="size-3 shrink-0" aria-hidden="true" />
            {t("stateEditor.memory.compressedUpto", { seq: summaryUpto })}
          </span>
        ) : null}
      </div>

      <div className="flex flex-col gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="w-full"
          disabled={summarizeDisabled}
          onClick={handleSummarize}
        >
          {summarize.isPending ? (
            <>
              <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" />
              {t("stateEditor.memory.summarizing")}
            </>
          ) : (
            t("stateEditor.memory.summarizeNow")
          )}
        </Button>

        {summarizeSuccess && !summarize.isError ? (
          <p role="status" className="flex items-center gap-1.5 text-xs text-accent-text">
            <Check className="size-3.5 shrink-0" aria-hidden="true" />
            <span>{t("stateEditor.memory.summarizeSuccess")}</span>
          </p>
        ) : null}

        {summarize.isError ? (
          <p
            role="alert"
            className="flex items-start gap-1.5 rounded-md border border-danger bg-surface-2 p-2 text-xs text-danger-text"
          >
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span className="min-w-0 break-words">{resolveSummarizeError(summarize.error)}</span>
          </p>
        ) : null}
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-1">
          <Label htmlFor={`memory-summary-${chatId}`}>{t("stateEditor.memory.summaryLabel")}</Label>
          <ManualBadge visible={isManualSummary} />
        </div>
        <Textarea
          id={`memory-summary-${chatId}`}
          rows={4}
          value={draftSummary}
          disabled={isBusy}
          placeholder={t("stateEditor.memory.summaryPlaceholder")}
          onChange={(e) => setSummaryOverride({ key: summary, value: e.target.value })}
          className="text-xs md:text-xs"
        />
        <Button
          type="button"
          size="sm"
          className="w-full"
          disabled={!summaryDirty || isBusy}
          onClick={() => onSaveSummary(draftSummary)}
        >
          {pending ? t("stateEditor.saving") : t("stateEditor.memory.saveSummary")}
        </Button>
      </div>

      <div className="flex flex-col gap-2 border-t border-border-subtle pt-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h4 className="text-xs font-semibold uppercase text-muted">
              {t("stateEditor.memory.eventsTitle")}
            </h4>
            <span className="rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 text-2xs font-medium text-muted">
              {t("stateEditor.memory.eventsCount", {
                count: draftEvents.length,
                max: MAX_MEMORABLE_EVENTS,
              })}
            </span>
          </div>
          <ManualBadge visible={isManualEvents} />
        </div>

        {draftEvents.length === 0 ? (
          <p className="text-xs text-muted">{t("stateEditor.memory.eventsEmpty")}</p>
        ) : (
          <ul className="flex flex-col divide-y divide-border-subtle">
            {draftEvents.map((ev, idx) => {
              const expanded = expandedEventId === ev.id;
              return (
                <li
                  key={ev.id}
                  data-testid={`memory-event-${ev.id}`}
                  className="flex flex-col py-1"
                >
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      aria-expanded={expanded}
                      onClick={() => setExpandedEventId(expanded ? null : ev.id)}
                      className="flex min-h-9 min-w-0 flex-1 items-center gap-1.5 rounded px-1 text-left text-xs font-medium text-fg hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                    >
                      <ChevronRight
                        className={cn(
                          "size-3.5 shrink-0 text-muted transition-transform duration-fast ease-ui motion-reduce:transition-none",
                          expanded && "rotate-90 text-fg",
                        )}
                        aria-hidden="true"
                      />
                      <span className="truncate">{ev.title}</span>
                    </button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      className="shrink-0"
                      disabled={isBusy}
                      aria-label={t("stateEditor.memory.removeEvent", {
                        title: ev.title || String(idx + 1),
                      })}
                      onClick={() => updateEvents((prev) => prev.filter((_, i) => i !== idx))}
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  </div>
                  {expanded ? (
                    <div className="flex flex-col gap-2 pb-2 pl-5 pt-1">
                      <Input
                        aria-label={t("stateEditor.memory.eventTitleItem", { n: idx + 1 })}
                        value={ev.title}
                        disabled={isBusy}
                        onChange={(e) => updateEventField(idx, "title", e.target.value)}
                        className="h-9 text-xs font-medium md:h-9"
                      />
                      <Textarea
                        aria-label={t("stateEditor.memory.eventContentItem", { n: idx + 1 })}
                        rows={2}
                        value={ev.content}
                        disabled={isBusy}
                        onChange={(e) => updateEventField(idx, "content", e.target.value)}
                        className="text-xs md:text-xs"
                      />
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}

        {draftEvents.length >= MAX_MEMORABLE_EVENTS ? (
          <p className="text-xs text-muted">
            {t("stateEditor.memory.maxEventsReached", { max: MAX_MEMORABLE_EVENTS })}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full"
              disabled={isBusy}
              aria-expanded={addOpen}
              onClick={() => setAddOpen((v) => !v)}
            >
              {addOpen ? t("stateEditor.memory.cancelAdd") : t("stateEditor.memory.addToggle")}
            </Button>
            {addOpen ? (
              <div className="flex flex-col gap-2 border-l-2 border-accent/40 pl-2.5">
                <Input
                  aria-label={t("stateEditor.memory.eventTitlePlaceholder")}
                  placeholder={t("stateEditor.memory.eventTitlePlaceholder")}
                  value={newTitle}
                  disabled={isBusy}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="h-9 text-xs md:h-9"
                />
                <Textarea
                  aria-label={t("stateEditor.memory.eventContentPlaceholder")}
                  placeholder={t("stateEditor.memory.eventContentPlaceholder")}
                  rows={2}
                  value={newContent}
                  disabled={isBusy}
                  onChange={(e) => setNewContent(e.target.value)}
                  className="text-xs md:text-xs"
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="w-full"
                  disabled={!canAddEvent}
                  onClick={handleAddEvent}
                >
                  <Plus className="size-4" aria-hidden="true" />
                  {t("stateEditor.memory.addEvent")}
                </Button>
              </div>
            ) : null}
          </div>
        )}

        <Button
          type="button"
          size="sm"
          className="w-full"
          disabled={!eventsDirty || isBusy}
          onClick={() => onSaveEvents(normalizeMemorableEvents(draftEvents))}
        >
          {pending ? t("stateEditor.saving") : t("stateEditor.memory.saveEvents")}
        </Button>
      </div>
    </Container>
  );
}
