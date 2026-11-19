import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useInRouterContext } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { LorebookPicker } from "@/features/library/form/LorebookPicker";
import * as libraryHooks from "@/features/library/hooks";
import { t } from "@/i18n";
import type { ChatOut, ChatSettings, StatePatch } from "@/types/chat";
import type { PersonaOut } from "@/types/library";
import { chatApi } from "../api";
import * as chatHooks from "../hooks";
import { MemorySection } from "../state/MemorySection";
import { useChatStreamStore } from "../store";
import { AgentModelSelects } from "./AgentModelSelects";
import { SelectField } from "./SelectField";
import { SidebarAccordion } from "./SidebarAccordion";

const STREAM_MODES = ["draft_then_replace", "hold_until_approved"] as const;
const LOREBOOK_MODES = ["hybrid", "keyword", "ai"] as const;
const REASONING_EFFORTS = ["off", "auto", "low", "medium", "high"] as const;
const WRITE_MODES = ["per_character", "single_call"] as const;
const CHAIN_MAX_OPTIONS = [1, 2, 3, 4, 5, 6] as const;

const CONTEXT_PRESETS = [
  { value: "16384", labelKey: "chatSettings.memory.contextLengthOptions.k16" },
  { value: "32768", labelKey: "chatSettings.memory.contextLengthOptions.k32" },
  { value: "65536", labelKey: "chatSettings.memory.contextLengthOptions.k64" },
  { value: "131072", labelKey: "chatSettings.memory.contextLengthOptions.k128" },
] as const;

const SUMMARIZE_RATIOS = [
  { value: "0.6", labelKey: "chatSettings.memory.summarizeAtOptions.r60" },
  { value: "0.7", labelKey: "chatSettings.memory.summarizeAtOptions.r70" },
  { value: "0.8", labelKey: "chatSettings.memory.summarizeAtOptions.r80" },
  { value: "0.9", labelKey: "chatSettings.memory.summarizeAtOptions.r90" },
] as const;

function useFallbackPatchState(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: StatePatch) => chatApi.patchState(id, patch),
    onSuccess: (chat) => client.setQueryData(["chats", "detail", id], chat),
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

const useResolvedPatchState = resolveOptionalHook(
  () => chatHooks.usePatchState,
  useFallbackPatchState,
);

function useFallbackPersonas(): { data?: PersonaOut[] } {
  return { data: [] };
}

const useResolvedPersonas = resolveOptionalHook<() => { data?: PersonaOut[] }>(
  () => libraryHooks.usePersonas,
  useFallbackPersonas,
);

type MemorySettings = NonNullable<ChatSettings["memory"]>;

interface MemorySettingsSectionProps {
  memory: MemorySettings | undefined;
  embedded?: boolean;
  onChange: (memory: MemorySettings) => void;
}

function MemorySettingsSection({ memory, embedded = false, onChange }: MemorySettingsSectionProps) {
  const contextLength = memory?.context_length ?? null;
  const summarizeAt = memory?.summarize_at ?? 0.8;
  const isPreset =
    contextLength === null || CONTEXT_PRESETS.some((p) => Number(p.value) === contextLength);

  const [customState, setCustomState] = useState<{
    active: boolean;
    draft: string;
    invalid: boolean;
  } | null>(null);

  const customOpen = customState ? customState.active : !isPreset;
  const selectValue = customOpen ? "custom" : contextLength === null ? "" : String(contextLength);
  const customDraft = customState?.draft ?? (contextLength !== null ? String(contextLength) : "");

  const ratioStr = String(summarizeAt);
  const hasKnownRatio = SUMMARIZE_RATIOS.some((r) => r.value === ratioStr);
  const summarizeOptions = [
    ...SUMMARIZE_RATIOS.map((r) => ({ value: r.value, label: t(r.labelKey) })),
    ...(hasKnownRatio
      ? []
      : [{ value: ratioStr, label: `${Math.round(summarizeAt * 100)}% (${ratioStr})` }]),
  ];

  function handleContextSelect(value: string): void {
    if (value === "") {
      setCustomState({ active: false, draft: "", invalid: false });
      onChange({ ...memory, context_length: null });
      return;
    }
    if (value === "custom") {
      setCustomState({
        active: true,
        draft: contextLength !== null ? String(contextLength) : "",
        invalid: false,
      });
      return;
    }
    setCustomState({ active: false, draft: value, invalid: false });
    onChange({ ...memory, context_length: Number(value) });
  }

  function handleCustomSubmit(event: FormEvent): void {
    event.preventDefault();
    const parsed = Number(customDraft.trim());
    if (!Number.isInteger(parsed) || parsed <= 0) {
      setCustomState({ active: true, draft: customDraft, invalid: true });
      return;
    }
    setCustomState({ active: true, draft: String(parsed), invalid: false });
    onChange({ ...memory, context_length: parsed });
  }

  const Container = embedded ? "div" : "section";

  return (
    <Container
      {...(!embedded ? { "aria-labelledby": "cs-memory" } : {})}
      className="flex flex-col gap-3"
    >
      {!embedded ? (
        <h3 id="cs-memory" className="text-sm font-semibold">
          {t("chatSettings.memory.title")}
        </h3>
      ) : null}
      <SelectField
        id="cs-memory-context"
        label={t("chatSettings.memory.contextLength")}
        value={selectValue}
        options={[
          { value: "", label: t("chatSettings.memory.contextLengthOptions.default") },
          ...CONTEXT_PRESETS.map((p) => ({ value: p.value, label: t(p.labelKey) })),
          { value: "custom", label: t("chatSettings.memory.contextLengthOptions.custom") },
        ]}
        onChange={handleContextSelect}
      />
      {customOpen ? (
        <form onSubmit={handleCustomSubmit} className="flex flex-col gap-1.5">
          <Label htmlFor="cs-memory-context-custom" className="text-xs text-muted">
            {t("chatSettings.memory.customContextLength")}
          </Label>
          <div className="flex flex-wrap gap-2">
            <Input
              id="cs-memory-context-custom"
              type="number"
              min={1}
              step={1}
              placeholder={t("chatSettings.memory.customContextLengthPlaceholder")}
              value={customDraft}
              onChange={(event) =>
                setCustomState({ active: true, draft: event.target.value, invalid: false })
              }
              className="h-9 min-w-0 flex-1 text-sm"
            />
            <Button type="submit" variant="outline" size="sm" className="h-9 shrink-0">
              {t("chatSettings.memory.applyCustomContext")}
            </Button>
          </div>
          {customState?.invalid ? (
            <p role="alert" className="text-xs text-danger">
              {t("chatSettings.memory.customContextInvalid")}
            </p>
          ) : null}
        </form>
      ) : null}
      <SelectField
        id="cs-memory-summarize-at"
        label={t("chatSettings.memory.summarizeAt")}
        value={ratioStr}
        options={summarizeOptions}
        onChange={(value) => onChange({ ...memory, summarize_at: Number(value) })}
      />
    </Container>
  );
}

export interface ChatSettingsPanelProps {
  chatId: string;
  hidePersona?: boolean;
  hideMemory?: boolean;
}

/** Per-chat settings (Archivist memory, director, lorebook mode, group, NSFW, per-agent model) & optional persona/memory. */
export function ChatSettingsPanel({
  chatId,
  hidePersona = false,
  hideMemory = false,
}: ChatSettingsPanelProps) {
  const inRouter = useInRouterContext();
  const queryClient = useQueryClient();
  const chat = chatHooks.useChat(chatId);
  const personas = useResolvedPersonas();
  const update = chatHooks.useUpdateChat(chatId);
  const patchState = useResolvedPatchState(chatId);
  const turn = useChatStreamStore((s) => s.turns[chatId]);
  const [stateSaved, setStateSaved] = useState(false);

  const rawSettings: ChatSettings = useMemo(() => chat.data?.settings ?? {}, [chat.data?.settings]);
  const rawSettingsKey = JSON.stringify(rawSettings);
  const latestSettingsRef = useRef<ChatSettings>(rawSettings);
  useEffect(() => {
    latestSettingsRef.current = rawSettings;
  }, [rawSettingsKey, rawSettings]);

  if (!chat.data) {
    return (
      <p role="status" className="p-4 text-sm text-muted">
        {t("chatSettings.loading")}
      </p>
    );
  }

  const settings: ChatSettings = chat.data.settings;
  const isWorld = chat.data.mode === "world";
  const resolvedId = chat.data.id ?? chatId;
  const rawState = (chat.data.state ?? {}) as Record<string, unknown>;
  const liveSummary =
    turn?.liveSummary ?? (typeof rawState.summary === "string" ? rawState.summary : "");
  const summaryUpto = typeof rawState.summary_upto === "number" ? rawState.summary_upto : 0;
  const events = Array.isArray(rawState.events) ? rawState.events : [];
  const isStreaming = turn?.status === "streaming";
  const memoryPending = patchState.isPending || isStreaming;

  /** Serialize settings patches against latest cached settings so rapid toggles do not clobber. */
  function patch(change: ChatSettings): void {
    let detailKey: readonly unknown[] = ["chats", "detail", resolvedId];
    try {
      if (typeof chatHooks.chatKeys?.detail === "function") {
        detailKey = chatHooks.chatKeys.detail(resolvedId);
      }
    } catch {
      /* partial test mock may omit chatKeys */
    }
    const cached = queryClient.getQueryData<ChatOut>(detailKey);
    const current = cached?.settings ?? latestSettingsRef.current;
    const next = { ...current, ...change };
    latestSettingsRef.current = next;
    update.mutate({ settings: next });
  }

  function submitMemoryPatch(statePatch: StatePatch): void {
    setStateSaved(false);
    patchState.mutate(statePatch, {
      onSuccess: () => {
        useChatStreamStore.getState().clearLiveFields(resolvedId, ["liveSummary"]);
        setStateSaved(true);
      },
    });
  }

  const directorEnabled = settings.director?.enabled ?? true;
  const streamMode = settings.director?.stream_mode ?? "draft_then_replace";
  const reasoningEffort = settings.writer?.reasoning ?? "medium";
  const loreMode = settings.lorebook?.mode ?? "hybrid";
  // `book_ids` null = the books linked to the card/world when the chat was created.
  const customBooks = Array.isArray(settings.lorebook?.book_ids);
  const chatBooks = settings.lorebook?.book_ids ?? chat.data.default_lorebook_ids ?? [];
  const personaList = personas.data ?? [];
  const currentPersonaId = chat.data.persona_id ?? "";
  const currentPersonaName =
    personaList.find((p) => p.id === currentPersonaId)?.data.name ??
    (currentPersonaId || t("newChat.noPersona"));
  const hasCurrentPersona =
    !currentPersonaId || personaList.some((p) => p.id === currentPersonaId);
  const personaOptions = [
    { value: "", label: t("newChat.noPersona") },
    ...personaList.map((p) => ({ value: p.id, label: p.data.name })),
    ...(hasCurrentPersona ? [] : [{ value: currentPersonaId, label: currentPersonaId }]),
  ];

  const writeMode = settings.group?.write_mode ?? "per_character";
  const chainMax = settings.group?.chain_max ?? 3;
  const contextTokens = settings.memory?.context_length;
  const summarizeRatio = settings.memory?.summarize_at ?? 0.8;
  const customModelsCount = Object.values(settings.models ?? {}).filter(Boolean).length;

  const directorSummary = directorEnabled
    ? t(`chatSettings.streamMode.${streamMode}`)
    : t("chatSettings.reasoningEffort.off");
  const writerSummary = t(`chatSettings.reasoningEffort.${reasoningEffort}`);
  const loreSummary = `${t(`chatSettings.lorebookMode.${loreMode}`)} · ${chatBooks.length}`;
  const memorySettingsSummary = `${contextTokens ? `${Math.round(contextTokens / 1000)}k` : t("chatSettings.models.default")} · ${Math.round(summarizeRatio * 100)}%`;
  const groupSummary = `${t(`chatSettings.group.writeModeOptions.${writeMode}`)} · ${chainMax}`;
  const singleMemorySummary =
    summaryUpto > 0
      ? `#${summaryUpto} · ${events.length}`
      : `${events.length}`;

  return (
    <div className="flex flex-col">
      <div className="sticky top-0 z-sticky flex items-center justify-between gap-2 border-b border-border-subtle bg-surface/95 px-3 py-2 backdrop-blur-sm">
        <h2 className="text-sm font-semibold text-fg">{t("chatSettings.title")}</h2>
        {update.isPending ? (
          <span role="status" className="text-xs text-muted">
            {t("chatSettings.saving")}
          </span>
        ) : update.isSuccess && !update.isError ? (
          <span role="status" className="inline-flex items-center gap-1 text-xs text-accent-text">
            <Check className="size-3.5" aria-hidden="true" />
            {t("chatSettings.saved")}
          </span>
        ) : null}
      </div>

      {update.isError ? (
        <p
          role="alert"
          className="mx-3 mt-2 flex items-center gap-1.5 rounded-md border border-danger bg-surface-2 p-2 text-xs text-danger-text"
        >
          <AlertCircle className="size-3.5 shrink-0" aria-hidden="true" />
          <span>{t("chatSettings.saveFailed")}</span>
        </p>
      ) : null}

      <div className="flex flex-col divide-y divide-border-subtle">
        {!hidePersona ? (
          <SidebarAccordion
            title={t("chatSettings.persona.title")}
            summary={currentPersonaName}
            defaultOpen
          >
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-end">
                {inRouter ? (
                  <Link
                    to="/library/personas/new"
                    className="link-inline text-xs font-medium text-accent-text hover:underline"
                  >
                    {t("chatSettings.persona.createLink")}
                  </Link>
                ) : (
                  <a
                    href="/library/personas/new"
                    className="link-inline text-xs font-medium text-accent-text hover:underline"
                  >
                    {t("chatSettings.persona.createLink")}
                  </a>
                )}
              </div>
              <SelectField
                id="cs-persona"
                label={t("chatSettings.persona.label")}
                value={currentPersonaId}
                options={personaOptions}
                onChange={(value) => update.mutate({ persona_id: value || null })}
              />
            </div>
          </SidebarAccordion>
        ) : null}

        {!isWorld && !hideMemory ? (
          <SidebarAccordion
            title={t("stateEditor.memory.title")}
            summary={singleMemorySummary}
          >
            <div className="flex flex-col gap-2">
              {stateSaved && !patchState.isError ? (
                <p role="status" className="text-xs text-accent-text">
                  {t("stateEditor.saved")}
                </p>
              ) : null}
              {patchState.isError ? (
                <p
                  role="alert"
                  className="rounded-md border border-danger bg-surface-2 p-2 text-xs text-danger-text"
                >
                  {t("stateEditor.saveFailed")}
                </p>
              ) : null}
              <MemorySection
                embedded
                chatId={resolvedId}
                summary={liveSummary}
                summaryUpto={summaryUpto}
                events={events}
                isStreaming={isStreaming}
                pending={memoryPending}
                onSaveSummary={(summary) => submitMemoryPatch({ summary })}
                onSaveEvents={(nextEvents) => submitMemoryPatch({ events: nextEvents })}
              />
            </div>
          </SidebarAccordion>
        ) : null}

        {isWorld ? (
          <SidebarAccordion
            title={t("chatSettings.group.title")}
            summary={groupSummary}
            defaultOpen={hidePersona}
          >
            <div className="flex flex-col gap-3">
              <SelectField
                id="cs-write-mode"
                label={t("chatSettings.group.writeMode")}
                value={writeMode}
                options={WRITE_MODES.map((mode) => ({
                  value: mode,
                  label: t(`chatSettings.group.writeModeOptions.${mode}`),
                }))}
                onChange={(value) =>
                  patch({
                    group: {
                      ...settings.group,
                      write_mode: value as (typeof WRITE_MODES)[number],
                    },
                  })
                }
              />
              <SelectField
                id="cs-chain-max"
                label={t("chatSettings.group.chainMax")}
                value={String(chainMax)}
                options={CHAIN_MAX_OPTIONS.map((count) => ({
                  value: String(count),
                  label: t("chatSettings.group.chainMaxOption", { count }),
                }))}
                onChange={(value) =>
                  patch({
                    group: {
                      ...settings.group,
                      chain_max: Number(value),
                    },
                  })
                }
              />
            </div>
          </SidebarAccordion>
        ) : null}

        <SidebarAccordion
          title={t("chatSettings.director.title")}
          summary={directorSummary}
          defaultOpen
        >
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="cs-director-on">{t("chatSettings.director.enabled")}</Label>
              <Switch
                id="cs-director-on"
                checked={directorEnabled}
                onCheckedChange={(enabled) => patch({ director: { ...settings.director, enabled } })}
              />
            </div>
            <SelectField
              id="cs-stream-mode"
              label={t("chatSettings.director.streamMode")}
              value={streamMode}
              disabled={!directorEnabled}
              options={STREAM_MODES.map((mode) => ({
                value: mode,
                label: t(`chatSettings.streamMode.${mode}`),
              }))}
              onChange={(value) =>
                patch({
                  director: {
                    ...settings.director,
                    stream_mode: value as (typeof STREAM_MODES)[number],
                  },
                })
              }
            />
          </div>
        </SidebarAccordion>

        <SidebarAccordion title={t("chatSettings.writer.title")} summary={writerSummary}>
          <div className="flex flex-col gap-2">
            <SelectField
              id="cs-reasoning"
              label={t("chatSettings.writer.reasoning")}
              value={reasoningEffort}
              options={REASONING_EFFORTS.map((effort) => ({
                value: effort,
                label: t(`chatSettings.reasoningEffort.${effort}`),
              }))}
              onChange={(value) =>
                patch({ writer: { reasoning: value as (typeof REASONING_EFFORTS)[number] } })
              }
            />
            <p className="text-xs text-muted">{t("chatSettings.writer.reasoningNote")}</p>
          </div>
        </SidebarAccordion>

        <SidebarAccordion title={t("chatSettings.lorebook.title")} summary={loreSummary}>
          <div className="flex flex-col gap-3">
            <SelectField
              id="cs-lorebook-mode"
              label={t("chatSettings.lorebook.mode")}
              value={loreMode}
              options={LOREBOOK_MODES.map((mode) => ({
                value: mode,
                label: t(`chatSettings.lorebookMode.${mode}`),
              }))}
              onChange={(value) =>
                patch({
                  lorebook: { ...settings.lorebook, mode: value as (typeof LOREBOOK_MODES)[number] },
                })
              }
            />
            <div className="flex flex-col gap-1">
              <p className="text-sm font-medium">{t("chatSettings.lorebook.books")}</p>
              <p className="text-xs text-muted">
                {customBooks
                  ? t("chatSettings.lorebook.booksCustom")
                  : t("chatSettings.lorebook.booksDefault")}
              </p>
            </div>
            <LorebookPicker
              selected={chatBooks}
              onChange={(book_ids) => patch({ lorebook: { ...settings.lorebook, book_ids } })}
            />
            {customBooks ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="self-start"
                onClick={() => patch({ lorebook: { ...settings.lorebook, book_ids: null } })}
              >
                {t("chatSettings.lorebook.booksReset")}
              </Button>
            ) : null}
          </div>
        </SidebarAccordion>

        <SidebarAccordion title={t("chatSettings.memory.title")} summary={memorySettingsSummary}>
          <MemorySettingsSection
            embedded
            memory={settings.memory}
            onChange={(memory) => patch({ memory })}
          />
        </SidebarAccordion>

        <section className="flex flex-col gap-2 px-3 py-3">
          <div className="flex items-center justify-between gap-3">
            <Label htmlFor="cs-nsfw">{t("chatSettings.nsfw.label")}</Label>
            <Switch
              id="cs-nsfw"
              checked={settings.nsfw ?? false}
              onCheckedChange={(nsfw) => patch({ nsfw })}
            />
          </div>
          <p data-testid="nsfw-note" className="text-xs text-muted">
            {t("chatSettings.nsfw.note")}
          </p>
        </section>

        <SidebarAccordion
          title={t("chatSettings.models.title")}
          summary={customModelsCount > 0 ? `${customModelsCount}` : t("chatSettings.models.default")}
        >
          <AgentModelSelects
            embedded
            mode={chat.data.mode}
            models={settings.models ?? {}}
            onChange={(models) => patch({ models })}
          />
        </SidebarAccordion>
      </div>
    </div>
  );
}
