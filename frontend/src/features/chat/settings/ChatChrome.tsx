import { AlertCircle, Check, Undo2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useInRouterContext } from "react-router-dom";
import { usePageChrome } from "@/app/pageChrome";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePersonas } from "@/features/library/hooks";
import { t } from "@/i18n";
import type { ChatOut, StatePatch } from "@/types/chat";
import { useChat, usePatchState, useUndoChat, useUpdateChat } from "../hooks";
import { RecentChats } from "../newChat/RecentChats";
import { BondsSection } from "../state/BondsSection";
import { LiveStateEditor } from "../state/LiveStateEditor";
import { MemorySection } from "../state/MemorySection";
import { useChatStreamStore, type LiveStreamField } from "../store";
import { ChatSettingsPanel } from "./ChatSettingsPanel";
import { SelectField } from "./SelectField";
import { SidebarAccordion } from "./SidebarAccordion";

function SingleSessionTab({ chat }: { chat: ChatOut }) {
  const inRouter = useInRouterContext();
  const personas = usePersonas();
  const update = useUpdateChat(chat.id);
  const patchState = usePatchState(chat.id);
  const undo = useUndoChat(chat.id);
  const turn = useChatStreamStore((s) => s.turns[chat.id]);
  const [savedFeedback, setSavedFeedback] = useState(false);

  const isStreaming = turn?.status === "streaming";
  const rawState = (chat.state ?? {}) as Record<string, unknown>;
  const bonds = (turn?.liveBonds ?? rawState.bonds ?? {}) as Record<string, unknown>;
  const liveSummary =
    turn?.liveSummary ?? (typeof rawState.summary === "string" ? rawState.summary : "");
  const summaryUpto = typeof rawState.summary_upto === "number" ? rawState.summary_upto : 0;
  const events = Array.isArray(rawState.events) ? rawState.events : [];
  const manualSet = new Set(Array.isArray(rawState.manual) ? (rawState.manual as string[]) : []);
  const bondCount = Object.keys(bonds).length;

  const personaList = personas.data ?? [];
  const currentPersonaId = chat.persona_id ?? "";
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

  function submitPatch(patch: StatePatch, clearFields: LiveStreamField[]): void {
    setSavedFeedback(false);
    patchState.mutate(patch, {
      onSuccess: () => {
        if (!isStreaming) {
          useChatStreamStore.getState().clearLiveFields(chat.id, clearFields);
        }
        setSavedFeedback(true);
      },
    });
  }

  return (
    <div className="flex flex-col">
      {(savedFeedback || patchState.isError || update.isError) && (
        <div className="border-b border-border-subtle px-3 py-2">
          {savedFeedback && !patchState.isError ? (
            <p role="status" className="inline-flex items-center gap-1 text-xs text-accent-text">
              <Check className="size-3.5" aria-hidden="true" />
              {t("stateEditor.saved")}
            </p>
          ) : null}
          {patchState.isError || update.isError ? (
            <p role="alert" className="inline-flex items-center gap-1 text-xs text-danger-text">
              <AlertCircle className="size-3.5 shrink-0" aria-hidden="true" />
              {t("stateEditor.saveFailed")}
            </p>
          ) : null}
        </div>
      )}

      <div className="flex flex-col divide-y divide-border-subtle">
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
              id="session-persona"
              label={t("chatSettings.persona.label")}
              value={currentPersonaId}
              options={personaOptions}
              onChange={(value) => {
                setSavedFeedback(false);
                update.mutate(
                  { persona_id: value || null },
                  { onSuccess: () => setSavedFeedback(true) },
                );
              }}
            />
          </div>
        </SidebarAccordion>

        <SidebarAccordion
          title={t("stateEditor.bonds.title")}
          summary={t("stateEditor.bonds.summaryCount", { count: bondCount })}
        >
          <BondsSection
            embedded
            bonds={bonds}
            cast={chat.cast ?? []}
            pending={patchState.isPending || isStreaming}
            onSavePair={(pairId, payload) =>
              submitPatch({ bonds: { ...bonds, [pairId]: payload } }, ["liveBonds"])
            }
          />
        </SidebarAccordion>

        <SidebarAccordion
          title={t("stateEditor.memory.title")}
          summary={summaryUpto > 0 ? `#${summaryUpto} · ${events.length}` : `${events.length}`}
        >
          <MemorySection
            embedded
            chatId={chat.id}
            summary={liveSummary}
            summaryUpto={summaryUpto}
            events={events}
            isStreaming={isStreaming}
            pending={patchState.isPending || isStreaming}
            isManualSummary={manualSet.has("summary")}
            isManualEvents={manualSet.has("events")}
            onSaveSummary={(summary) => submitPatch({ summary }, ["liveSummary"])}
            onSaveEvents={(nextEvents) => submitPatch({ events: nextEvents }, ["liveSummary"])}
          />
        </SidebarAccordion>

        <SidebarAccordion title={t("chatSettings.session.quickActionsTitle")}>
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted">{t("chatSettings.session.undoHint")}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full justify-start"
              disabled={isStreaming || undo.isPending || chat.messages_count <= 1}
              onClick={() => undo.mutate()}
            >
              <Undo2 className="size-4" aria-hidden="true" />
              {t("chat.input.undo")}
            </Button>
          </div>
        </SidebarAccordion>
      </div>
    </div>
  );
}

function SingleRightSidebar({ chatId }: { chatId: string }) {
  const chat = useChat(chatId);
  if (!chat.data) return null;

  return (
    <Tabs defaultValue="session" className="flex flex-col">
      <div className="sticky top-0 z-sticky border-b border-border-subtle bg-surface px-3 py-2">
        <TabsList aria-label={t("chatSettings.tabs.label")} className="grid w-full grid-cols-2">
          <TabsTrigger value="session">{t("chatSettings.tabs.session")}</TabsTrigger>
          <TabsTrigger value="settings">{t("chatSettings.tabs.settings")}</TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="session" className="mt-0">
        <SingleSessionTab chat={chat.data} />
      </TabsContent>
      <TabsContent value="settings" className="mt-0">
        <ChatSettingsPanel chatId={chatId} hidePersona hideMemory />
      </TabsContent>
    </Tabs>
  );
}

function WorldRightSidebar({ chatId }: { chatId: string }) {
  const chat = useChat(chatId);
  if (!chat.data) return null;

  return (
    <Tabs defaultValue="state" className="flex flex-col">
      <div className="sticky top-0 z-sticky border-b border-border-subtle bg-surface px-3 py-2">
        <TabsList aria-label={t("chatSettings.tabs.label")} className="grid w-full grid-cols-2">
          <TabsTrigger value="state">{t("chatSettings.tabs.state")}</TabsTrigger>
          <TabsTrigger value="settings">{t("chatSettings.tabs.settings")}</TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="state" className="mt-0">
        <LiveStateEditor chat={chat.data} />
      </TabsContent>
      <TabsContent value="settings" className="mt-0">
        <ChatSettingsPanel chatId={chatId} />
      </TabsContent>
    </Tabs>
  );
}

/** Renders nothing; fills the left (recent chats) and right (session/state + settings) sidebars for a chat page. */
export function ChatChrome({ chatId }: { chatId: string }) {
  const chat = useChat(chatId);
  const isWorld = chat.data?.mode === "world";
  const left = useMemo(() => <RecentChats key={chatId} />, [chatId]);
  const right = useMemo(
    () =>
      isWorld ? (
        <WorldRightSidebar key={chatId} chatId={chatId} />
      ) : (
        <SingleRightSidebar key={chatId} chatId={chatId} />
      ),
    [chatId, isWorld],
  );
  usePageChrome({
    left,
    right,
    leftTitle: t("newChat.recent"),
    rightTitle: isWorld ? t("chatSettings.tabs.state") : t("chatSettings.tabs.session"),
    hideMobileNav: true,
    hideToggleBar: true,
  });
  return null;
}
