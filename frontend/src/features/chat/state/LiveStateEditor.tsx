import { useState } from "react";
import { useWorld } from "@/features/library/hooks";
import { t } from "@/i18n";
import type { ChatOut, StatePatch } from "@/types/chat";
import { usePatchState } from "../hooks";
import { useChatStreamStore } from "../store";
import { BondsSection } from "./BondsSection";
import { MemorySection } from "./MemorySection";
import { SceneSection } from "./SceneSection";
import { mergeLiveWorldState } from "./stateHelpers";
import { StructuredStateSection } from "./StructuredStateSection";

interface LiveStateEditorProps {
  chat: ChatOut;
}

/** Right-sidebar Live State Editor for world chats (structured state, scene, bonds). */
export function LiveStateEditor({ chat }: LiveStateEditorProps) {
  const world = useWorld(chat.world_id ?? undefined);
  const turn = useChatStreamStore((s) => s.turns[chat.id]);
  const patchState = usePatchState(chat.id);
  const [savedNotice, setSavedNotice] = useState(false);

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

  function submitPatch(patch: StatePatch): void {
    setSavedNotice(false);
    patchState.mutate(patch, {
      onSuccess: () => {
        if (turn?.status !== "streaming") {
          useChatStreamStore.getState().clear(chat.id);
        }
        setSavedNotice(true);
      },
    });
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{t("stateEditor.title")}</h2>
        {savedNotice && !patchState.isError ? (
          <span role="status" className="text-xs text-accent-2">
            {t("stateEditor.saved")}
          </span>
        ) : null}
      </div>

      {patchState.isError ? (
        <p
          role="alert"
          className="rounded-md border border-danger bg-surface p-2 text-xs text-danger"
        >
          {t("stateEditor.saveFailed")}
        </p>
      ) : null}

      <StructuredStateSection
        value={{
          location_id: state.location_id ?? "",
          time: state.time ?? "",
          tension: state.tension ?? 0,
          present_ids: state.present_ids ?? [],
          awaiting_reply: state.awaiting_reply ?? [],
        }}
        locations={locations}
        cast={cast}
        silence={state.silence ?? {}}
        manualKeys={manualSet}
        pending={isBusy}
        onSave={submitPatch}
      />

      <SceneSection
        scene={state.scene}
        presentIds={state.present_ids ?? []}
        cast={cast}
        isManual={sceneManual}
        pending={isBusy}
        onSave={(scene) => submitPatch({ scene })}
      />

      <BondsSection
        bonds={(state.bonds ?? {}) as Record<string, unknown>}
        cast={cast}
        pending={isBusy}
        onSavePair={(pairId, payload) =>
          submitPatch({ bonds: { ...(state.bonds ?? {}), [pairId]: payload } })
        }
      />

      <MemorySection
        chatId={chat.id}
        summary={liveSummary}
        summaryUpto={summaryUpto}
        events={events}
        isStreaming={turn?.status === "streaming"}
        pending={isBusy}
        isManualSummary={manualSet.has("summary")}
        isManualEvents={manualSet.has("events")}
        onSaveSummary={(summary) => submitPatch({ summary })}
        onSaveEvents={(nextEvents) => submitPatch({ events: nextEvents })}
      />
    </div>
  );
}
