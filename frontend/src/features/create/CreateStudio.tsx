import { Globe, RotateCcw, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ImportButton } from "@/features/io";
import { t } from "@/i18n";
import { ChatCreatorSection } from "./ChatCreatorSection";
import { PipelineOutputPanel } from "./PipelineOutputPanel";
import { SlotMachineSection } from "./SlotMachineSection";
import { useCreatorStudio } from "./useCreatorStudio";

/** Creator Studio: Carousel + Slot Machine, Chat Interview, 2-step Generator, and Card Judge. */
export function CreateStudio() {
  const studio = useCreatorStudio();
  const busy = studio.isStreamingChat || studio.isGenerating;
  const ws = studio.currentWorkspace;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 pb-20 md:px-8">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">{t("create.title")}</h1>
          <p className="max-w-2xl text-sm text-muted">{t("create.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {ws.sessionId || ws.rawText || ws.messages.length > 0 ? (
            <Button type="button" variant="outline" disabled={busy} onClick={studio.resetSession}>
              <RotateCcw className="size-4" aria-hidden="true" />
              {t("create.resetSession")}
            </Button>
          ) : null}
          <ImportButton />
        </div>
      </header>

      <Tabs
        value={studio.mode}
        onValueChange={(next) => {
          if (busy) return;
          studio.setMode(next === "chat" ? "chat" : "slots");
        }}
        className="flex flex-col gap-6"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            role="group"
            aria-label={t("create.targetLabel")}
            className="inline-flex rounded-md border border-border bg-surface p-1"
          >
            <Button
              type="button"
              size="sm"
              variant={studio.targetType === "character" ? "default" : "ghost"}
              disabled={busy}
              aria-pressed={studio.targetType === "character"}
              onClick={() => studio.setTargetType("character")}
            >
              <UserRound className="size-4" aria-hidden="true" />
              {t("create.targets.character")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant={studio.targetType === "world" ? "default" : "ghost"}
              disabled={busy}
              aria-pressed={studio.targetType === "world"}
              onClick={() => studio.setTargetType("world")}
            >
              <Globe className="size-4" aria-hidden="true" />
              {t("create.targets.world")}
            </Button>
          </div>

          <TabsList aria-label={t("create.modeLabel")}>
            <TabsTrigger value="slots" disabled={busy}>
              {t("create.modes.slots")}
            </TabsTrigger>
            <TabsTrigger value="chat" disabled={busy}>
              {t("create.modes.chat")}
            </TabsTrigger>
          </TabsList>
        </div>

        <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-12">
          <div className="min-w-0 xl:col-span-7">
            <TabsContent value="slots" className="mt-0">
              <SlotMachineSection
                targetType={studio.targetType}
                pools={studio.poolsQuery.data}
                poolsPending={studio.poolsQuery.isPending}
                poolsError={studio.poolsQuery.isError}
                onRetryPools={() => void studio.poolsQuery.refetch()}
                seedState={studio.currentSeed}
                onChangeSeed={studio.setCurrentSeed}
                disabled={studio.isGenerating}
              />
            </TabsContent>

            <TabsContent value="chat" className="mt-0">
              <ChatCreatorSection
                targetType={studio.targetType}
                messages={ws.messages}
                streamingReply={ws.streamingReply}
                isStreaming={studio.isStreamingChat}
                isGenerating={studio.isGenerating}
                errorCode={ws.chatErrorCode}
                onSendMessage={studio.sendMessage}
                onFinalize={() => void studio.generate(false)}
              />
            </TabsContent>
          </div>

          <div className="min-w-0 xl:sticky xl:top-6 xl:col-span-5">
            <PipelineOutputPanel
              targetType={studio.targetType}
              stage={ws.stage}
              isGenerating={studio.isGenerating}
              isStreamingChat={studio.isStreamingChat}
              rawText={ws.rawText}
              onChangeRaw={(rawText) =>
                studio.patchCurrentWorkspace((prev) => ({ ...prev, rawText }))
              }
              onGenerateFull={() => void studio.generate(false)}
              onGenerateFromRaw={() => void studio.generate(true)}
              generatedData={ws.generatedData}
              warnings={ws.warnings}
              jsonText={ws.jsonText}
              jsonInvalid={ws.jsonInvalid}
              onPatchData={studio.patchGeneratedData}
              onChangeJsonText={studio.changeJsonText}
              judgeScore={ws.judgeScore}
              notices={ws.notices}
              onDismissNotice={(idx) =>
                studio.patchCurrentWorkspace((prev) => ({
                  ...prev,
                  notices: prev.notices.filter((_, i) => i !== idx),
                }))
              }
              pipelineErrorCode={ws.pipelineErrorCode}
              visibility={ws.visibility}
              onVisibility={(visibility) => {
                studio.resetSaveError();
                studio.patchCurrentWorkspace((prev) => ({ ...prev, visibility }));
              }}
              isSaving={studio.isSaving}
              saveError={studio.saveError}
              onSave={() => void studio.save()}
            />
          </div>
        </div>
      </Tabs>
    </div>
  );
}
