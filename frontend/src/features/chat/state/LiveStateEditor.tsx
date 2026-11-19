import { Check, AlertCircle } from "lucide-react";
import { useCallback, useState } from "react";
import { useWorld } from "@/features/library/hooks";
import { pathLabel } from "@/features/library/world/treeOps";
import { t } from "@/i18n";
import type { ChatOut, StatePatch } from "@/types/chat";
import { usePatchState } from "../hooks";
import { SidebarAccordion } from "../settings/SidebarAccordion";
import { useChatStreamStore, type LiveStreamField } from "../store";
import { BondsSection } from "./BondsSection";
import { MemorySection } from "./MemorySection";
import { SceneSection } from "./SceneSection";
import { mergeLiveWorldState } from "./stateHelpers";
import { StructuredStateSection } from "./StructuredStateSection";

interface LiveStateEditorProps {
  chat: ChatOut;
}

/** Right-sidebar Live State Editor for world chats (structured state, scene, bonds, memory). */
export function LiveStateEditor({ chat }: LiveStateEditorProps) {
  const world = useWorld(chat.world_id ?? undefined);
  const turn = useChatStreamStore((s) => s.turns[chat.id]);
  const patchState = usePatchState(chat.id);
  const [savedNotice, setSavedNotice] = useState(false);
  const [structuredDirty, setStructuredDirty] = useState(false);
  const [sceneDirty, setSceneDirty] = useState(false);
  const [memoryDirty, setMemoryDirty] = useState(false);

  const state = mergeLiveWorldState(chat.state, turn);
  const liveSummary = turn?.liveSummary ?? state.summary ?? "";
  const summaryUpto = state.summary_upto ?? 0;
  const events = state.events ?? [];
  const locations = world.data?.data.locations ?? [];
  const cast = chat.cast ?? [];
  const manualSet = new Set(state.manual ?? []);
  const sceneManual =
    manualSet.has("scene") || [...manualSet].some((key) => key.startsWith("scene."));
  const isBusy = patchState.isPending || turn?.status === "streaming";

  const submitPatch = useCallback(
    (patch: StatePatch, clearFields: LiveStreamField[]) => {
      setSavedNotice(false);
      patchState.mutate(patch, {
        onSuccess: () => {
          if (turn?.status !== "streaming") {
            useChatStreamStore.getState().clearLiveFields(chat.id, clearFields);
          }
          setSavedNotice(true);
        },
      });
    },
    [chat.id, patchState, turn?.status],
  );

  const locationSummary = state.location_id ? pathLabel(locations, state.location_id) : "";
  const structuredSummary = [
    locationSummary || null,
    state.time || null,
    `${state.tension ?? 0}/4`,
  ]
    .filter(Boolean)
    .join(" · ");

  const presentIds = state.present_ids ?? [];
  const itemCount = state.scene?.items?.length ?? 0;
  const sceneSummary = `${presentIds.length} · ${itemCount}`;
  const bondCount = Object.keys(state.bonds ?? {}).length;
  const bondsSummary = t("stateEditor.bonds.summaryCount", { count: bondCount });
  const memorySummary =
    summaryUpto > 0
      ? `#${summaryUpto} · ${t("stateEditor.memory.eventsCount", { count: events.length, max: 24 })}`
      : t("stateEditor.memory.eventsCount", { count: events.length, max: 24 });

  return (
    <div className="flex flex-col">
      <div className="sticky top-0 z-sticky flex items-center justify-between gap-2 border-b border-border-subtle bg-surface/95 px-3 py-2 backdrop-blur-sm">
        <h2 className="text-sm font-semibold text-fg">{t("stateEditor.title")}</h2>
        {patchState.isPending ? (
          <span role="status" className="text-xs text-muted">
            {t("stateEditor.saving")}
          </span>
        ) : savedNotice && !patchState.isError ? (
          <span role="status" className="inline-flex items-center gap-1 text-xs text-accent-text">
            <Check className="size-3.5" aria-hidden="true" />
            {t("stateEditor.saved")}
          </span>
        ) : null}
      </div>

      {patchState.isError ? (
        <p
          role="alert"
          className="mx-3 mt-2 flex items-center gap-1.5 rounded-md border border-danger bg-surface-2 p-2 text-xs text-danger-text"
        >
          <AlertCircle className="size-3.5 shrink-0" aria-hidden="true" />
          <span>{t("stateEditor.saveFailed")}</span>
        </p>
      ) : null}

      <div className="flex flex-col divide-y divide-border-subtle">
        <SidebarAccordion
          title={t("stateEditor.structured.title")}
          summary={structuredSummary}
          dirty={structuredDirty}
          defaultOpen
        >
          <StructuredStateSection
            embedded
            value={{
              location_id: state.location_id ?? "",
              time: state.time ?? "",
              tension: state.tension ?? 0,
              present_ids: presentIds,
              awaiting_reply: state.awaiting_reply ?? [],
            }}
            locations={locations}
            cast={cast}
            silence={state.silence ?? {}}
            manualKeys={manualSet}
            pending={isBusy}
            onDirtyChange={setStructuredDirty}
            onSave={(patch) => submitPatch(patch, ["liveState"])}
          />
        </SidebarAccordion>

        <SidebarAccordion
          title={t("stateEditor.scene.title")}
          summary={sceneSummary}
          dirty={sceneDirty}
        >
          <SceneSection
            embedded
            scene={state.scene}
            presentIds={presentIds}
            cast={cast}
            isManual={sceneManual}
            pending={isBusy}
            onDirtyChange={setSceneDirty}
            onSave={(scene) => submitPatch({ scene }, ["liveScene"])}
          />
        </SidebarAccordion>

        <SidebarAccordion title={t("stateEditor.bonds.title")} summary={bondsSummary}>
          <BondsSection
            embedded
            bonds={(state.bonds ?? {}) as Record<string, unknown>}
            cast={cast}
            pending={isBusy}
            onSavePair={(pairId, payload) =>
              submitPatch(
                { bonds: { ...(state.bonds ?? {}), [pairId]: payload } },
                ["liveBonds"],
              )
            }
          />
        </SidebarAccordion>

        <SidebarAccordion
          title={t("stateEditor.memory.title")}
          summary={memorySummary}
          dirty={memoryDirty}
        >
          <MemorySection
            embedded
            chatId={chat.id}
            summary={liveSummary}
            summaryUpto={summaryUpto}
            events={events}
            isStreaming={turn?.status === "streaming"}
            pending={isBusy}
            isManualSummary={manualSet.has("summary")}
            isManualEvents={manualSet.has("events")}
            onDirtyChange={setMemoryDirty}
            onSaveSummary={(summary) => submitPatch({ summary }, ["liveSummary"])}
            onSaveEvents={(nextEvents) => submitPatch({ events: nextEvents }, ["liveSummary"])}
          />
        </SidebarAccordion>
      </div>
    </div>
  );
}
