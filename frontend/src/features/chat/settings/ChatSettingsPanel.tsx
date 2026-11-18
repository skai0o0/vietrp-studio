import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { t } from "@/i18n";
import type { ChatSettings, StatePatch } from "@/types/chat";
import { chatApi } from "../api";
import * as chatHooks from "../hooks";
import { MemorySection } from "../state/MemorySection";
import { useChatStreamStore } from "../store";
import { AgentModelSelects } from "./AgentModelSelects";
import { SelectField } from "./SelectField";

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

type MemorySettings = NonNullable<ChatSettings["memory"]>;

interface MemorySettingsSectionProps {
  memory: MemorySettings | undefined;
  onChange: (memory: MemorySettings) => void;
}

function MemorySettingsSection({ memory, onChange }: MemorySettingsSectionProps) {
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

  return (
    <section className="flex flex-col gap-3" aria-labelledby="cs-memory">
      <h3 id="cs-memory" className="text-sm font-semibold">
        {t("chatSettings.memory.title")}
      </h3>
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
    </section>
  );
}

/** Per-chat settings (Archivist memory, director, lorebook mode, group, NSFW, per-agent model) & single-chat memory editor. */
export function ChatSettingsPanel({ chatId }: { chatId: string }) {
  const chat = chatHooks.useChat(chatId);
  const update = chatHooks.useUpdateChat(chatId);
  const patchState = useResolvedPatchState(chatId);
  const turn = useChatStreamStore((s) => s.turns[chatId]);
  const [stateSaved, setStateSaved] = useState(false);

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

  /** PATCH with the full merged settings object so untouched keys are preserved. */
  function patch(change: ChatSettings): void {
    update.mutate({ settings: { ...settings, ...change } });
  }

  function submitMemoryPatch(statePatch: StatePatch): void {
    setStateSaved(false);
    patchState.mutate(statePatch, {
      onSuccess: () => {
        useChatStreamStore.getState().clearMemory(resolvedId);
        setStateSaved(true);
      },
    });
  }

  const directorEnabled = settings.director?.enabled ?? true;
  return (
    <div className="flex flex-col gap-5 p-4">
      <h2 className="text-lg font-semibold">{t("chatSettings.title")}</h2>
      {update.isError ? (
        <p role="alert" className="text-xs text-danger">
          {t("chatSettings.saveFailed")}
        </p>
      ) : null}

      {!isWorld ? (
        <>
          <div className="flex flex-col gap-2">
            {stateSaved && !patchState.isError ? (
              <p role="status" className="text-xs text-accent-2">
                {t("stateEditor.saved")}
              </p>
            ) : null}
            {patchState.isError ? (
              <p
                role="alert"
                className="rounded-md border border-danger bg-surface p-2 text-xs text-danger"
              >
                {t("stateEditor.saveFailed")}
              </p>
            ) : null}
            <MemorySection
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
          <Separator />
        </>
      ) : null}

      {isWorld ? (
        <section className="flex flex-col gap-3" aria-labelledby="cs-group">
          <h3 id="cs-group" className="text-sm font-semibold">
            {t("chatSettings.group.title")}
          </h3>
          <SelectField
            id="cs-write-mode"
            label={t("chatSettings.group.writeMode")}
            value={settings.group?.write_mode ?? "per_character"}
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
            value={String(settings.group?.chain_max ?? 3)}
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
        </section>
      ) : null}

      <MemorySettingsSection memory={settings.memory} onChange={(memory) => patch({ memory })} />

      <section className="flex flex-col gap-3" aria-labelledby="cs-director">
        <h3 id="cs-director" className="text-sm font-semibold">
          {t("chatSettings.director.title")}
        </h3>
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
          value={settings.director?.stream_mode ?? "draft_then_replace"}
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
      </section>

      <section className="flex flex-col gap-2" aria-labelledby="cs-writer">
        <h3 id="cs-writer" className="text-sm font-semibold">
          {t("chatSettings.writer.title")}
        </h3>
        <SelectField
          id="cs-reasoning"
          label={t("chatSettings.writer.reasoning")}
          value={settings.writer?.reasoning ?? "medium"}
          options={REASONING_EFFORTS.map((effort) => ({
            value: effort,
            label: t(`chatSettings.reasoningEffort.${effort}`),
          }))}
          onChange={(value) =>
            patch({ writer: { reasoning: value as (typeof REASONING_EFFORTS)[number] } })
          }
        />
        <p className="text-xs text-muted">{t("chatSettings.writer.reasoningNote")}</p>
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="cs-lorebook">
        <h3 id="cs-lorebook" className="text-sm font-semibold">
          {t("chatSettings.lorebook.title")}
        </h3>
        <SelectField
          id="cs-lorebook-mode"
          label={t("chatSettings.lorebook.mode")}
          value={settings.lorebook?.mode ?? "hybrid"}
          options={LOREBOOK_MODES.map((mode) => ({
            value: mode,
            label: t(`chatSettings.lorebookMode.${mode}`),
          }))}
          onChange={(value) =>
            patch({ lorebook: { mode: value as (typeof LOREBOOK_MODES)[number] } })
          }
        />
      </section>

      <section className="flex flex-col gap-2">
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

      <AgentModelSelects models={settings.models ?? {}} onChange={(models) => patch({ models })} />
    </div>
  );
}
