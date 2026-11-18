import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import {
  runCreatorGenerateStream,
  runCreatorMessageStream,
  useCreateCreatorSession,
  useCreatorPools,
  useSaveCreatorSession,
} from "./hooks";
import { buildSeedPayload, emptySeedState, initializeSeedFromPools } from "./slotHelpers";
import type {
  CreatorMessage,
  CreatorMode,
  CreatorSeedState,
  CreatorStreamEvent,
  TargetType,
} from "./types";
import {
  applyGenerateEvent,
  emptyWorkspace,
  isPlainRecord,
  readWorkspace,
  workspaceKey,
  type WorkspaceKey,
  type WorkspaceMap,
  type WorkspaceState,
} from "./workspaceHelpers";

interface SeedByTarget {
  character: CreatorSeedState;
  world: CreatorSeedState;
}

export function useCreatorStudio() {
  const navigate = useNavigate();
  const poolsQuery = useCreatorPools();
  const createSession = useCreateCreatorSession();
  const saveSession = useSaveCreatorSession();

  const [targetType, setTargetType] = useState<TargetType>("character");
  const [mode, setMode] = useState<CreatorMode>("slots");
  const [seedByTarget, setSeedByTarget] = useState<SeedByTarget>(() => ({
    character: emptySeedState(),
    world: emptySeedState(),
  }));
  const [workspaces, setWorkspaces] = useState<WorkspaceMap>(() => ({
    "character:slots": emptyWorkspace(),
    "character:chat": emptyWorkspace(),
    "world:slots": emptyWorkspace(),
    "world:chat": emptyWorkspace(),
  }));
  const [activeMessageKey, setActiveMessageKey] = useState<WorkspaceKey | null>(null);
  const [activeGenerateKey, setActiveGenerateKey] = useState<WorkspaceKey | null>(null);

  const effectiveSeedByTarget = useMemo<SeedByTarget>(
    () => ({
      character: initializeSeedFromPools(seedByTarget.character, poolsQuery.data, "character"),
      world: initializeSeedFromPools(seedByTarget.world, poolsQuery.data, "world"),
    }),
    [poolsQuery.data, seedByTarget],
  );

  const workspacesRef = useRef(workspaces);
  const seedRef = useRef(effectiveSeedByTarget);
  useEffect(() => {
    workspacesRef.current = workspaces;
    seedRef.current = effectiveSeedByTarget;
  }, [workspaces, effectiveSeedByTarget]);

  const messageAbortRef = useRef<AbortController | null>(null);
  const generateAbortRef = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      messageAbortRef.current?.abort();
      generateAbortRef.current?.abort();
    },
    [],
  );

  const patchWorkspace = useCallback(
    (key: WorkspaceKey, updater: (prev: WorkspaceState) => WorkspaceState) => {
      setWorkspaces((prev) => ({ ...prev, [key]: updater(readWorkspace(prev, key)) }));
    },
    [],
  );

  const ensureSession = useCallback(
    async (
      target: TargetType,
      selectedMode: CreatorMode,
      errorField: "chatErrorCode" | "pipelineErrorCode",
    ): Promise<string | null> => {
      const key = workspaceKey(target, selectedMode);
      const existing = readWorkspace(workspacesRef.current, key).sessionId;
      if (existing) return existing;

      const seed = buildSeedPayload(seedRef.current[target], target);
      try {
        const session = await createSession.mutateAsync({
          mode: selectedMode,
          target_type: target,
          seed,
        });
        patchWorkspace(key, (prev) => ({ ...prev, sessionId: session.id }));
        return session.id;
      } catch (error) {
        const code = error instanceof ApiError ? error.code : "network_error";
        patchWorkspace(key, (prev) => ({
          ...prev,
          [errorField]: code,
          ...(errorField === "pipelineErrorCode" ? { stage: "error" as const } : {}),
        }));
        return null;
      }
    },
    [createSession, patchWorkspace],
  );

  const sendMessage = useCallback(
    async (text: string): Promise<boolean> => {
      if (activeMessageKey || activeGenerateKey) return false;
      const key = workspaceKey(targetType, "chat");
      const userMessage: CreatorMessage = { role: "user", content: text };

      setActiveMessageKey(key);
      patchWorkspace(key, (prev) => ({
        ...prev,
        chatErrorCode: null,
        streamingReply: "",
        messages: [...prev.messages, userMessage],
      }));

      const sessionId = await ensureSession(targetType, "chat", "chatErrorCode");
      if (!sessionId) {
        patchWorkspace(key, (prev) => ({ ...prev, messages: prev.messages.slice(0, -1) }));
        setActiveMessageKey(null);
        return false;
      }

      const controller = new AbortController();
      messageAbortRef.current = controller;
      let started = false;
      let failedEarly = false;
      let settled = false;

      await runCreatorMessageStream({
        sessionId,
        text,
        signal: controller.signal,
        onEvent: (event: CreatorStreamEvent) => {
          if (event.type === "delta") {
            started = true;
            patchWorkspace(key, (prev) => ({
              ...prev,
              streamingReply: prev.streamingReply + event.delta,
            }));
          } else if (event.type === "message") {
            started = true;
            patchWorkspace(key, (prev) => ({ ...prev, streamingReply: event.message.content }));
          } else if (event.type === "done") {
            settled = true;
            patchWorkspace(key, (prev) => ({
              ...prev,
              sessionId: event.session.id,
              messages:
                event.session.messages.length > 0
                  ? event.session.messages
                  : prev.streamingReply
                    ? [...prev.messages, { role: "assistant", content: prev.streamingReply }]
                    : prev.messages,
              streamingReply: "",
            }));
          } else if (event.type === "error") {
            settled = true;
            if (!started) failedEarly = true;
            patchWorkspace(key, (prev) => ({
              ...prev,
              chatErrorCode: event.code,
              streamingReply: "",
              messages: started ? prev.messages : prev.messages.slice(0, -1),
            }));
          }
        },
        onError: (code) => {
          settled = true;
          if (!started) failedEarly = true;
          patchWorkspace(key, (prev) => ({
            ...prev,
            chatErrorCode: code,
            streamingReply: "",
            messages: started ? prev.messages : prev.messages.slice(0, -1),
          }));
        },
        onDone: () => {
          if (!settled) {
            patchWorkspace(key, (prev) => ({
              ...prev,
              messages: prev.streamingReply
                ? [...prev.messages, { role: "assistant", content: prev.streamingReply }]
                : prev.messages,
              streamingReply: "",
            }));
          }
        },
      });

      messageAbortRef.current = null;
      setActiveMessageKey(null);
      return !failedEarly;
    },
    [activeGenerateKey, activeMessageKey, ensureSession, patchWorkspace, targetType],
  );

  const generate = useCallback(
    async (skipRaw: boolean): Promise<void> => {
      if (activeMessageKey || activeGenerateKey) return;
      const key = workspaceKey(targetType, mode);
      const current = readWorkspace(workspacesRef.current, key);
      const seed = buildSeedPayload(seedRef.current[targetType], targetType);
      saveSession.reset();

      setActiveGenerateKey(key);
      patchWorkspace(key, (prev) => ({
        ...prev,
        stage: skipRaw ? "formatting" : "drafting_raw",
        pipelineErrorCode: null,
        notices: [],
      }));

      const sessionId = await ensureSession(targetType, mode, "pipelineErrorCode");
      if (!sessionId) {
        setActiveGenerateKey(null);
        return;
      }

      const controller = new AbortController();
      generateAbortRef.current = controller;
      let settled = false;

      await runCreatorGenerateStream({
        sessionId,
        body: { skip_raw: skipRaw, ...(skipRaw ? { raw: current.rawText } : {}), seed },
        signal: controller.signal,
        onEvent: (event: CreatorStreamEvent) => {
          if (event.type === "done" || event.type === "error") settled = true;
          patchWorkspace(key, (prev) => applyGenerateEvent(prev, event));
        },
        onError: (code) => {
          settled = true;
          patchWorkspace(key, (prev) => ({ ...prev, pipelineErrorCode: code, stage: "error" }));
        },
        onDone: () => {
          if (!settled) {
            patchWorkspace(key, (prev) => ({
              ...prev,
              stage: prev.stage === "error" ? "error" : "idle",
            }));
          }
        },
      });

      generateAbortRef.current = null;
      setActiveGenerateKey(null);
    },
    [
      activeGenerateKey,
      activeMessageKey,
      ensureSession,
      mode,
      patchWorkspace,
      saveSession,
      targetType,
    ],
  );

  const currentKey = workspaceKey(targetType, mode);
  const currentWorkspace = readWorkspace(workspaces, currentKey);
  const currentSeed = effectiveSeedByTarget[targetType];
  const isStreamingChat = activeMessageKey !== null;
  const isGenerating = activeGenerateKey !== null;

  async function save(): Promise<void> {
    if (!currentWorkspace.sessionId || !currentWorkspace.generatedData) return;
    try {
      const saved = await saveSession.mutateAsync({
        sessionId: currentWorkspace.sessionId,
        body: { visibility: currentWorkspace.visibility, data: currentWorkspace.generatedData },
      });
      toast.success(t("create.pipeline.save.saved"));
      void navigate(
        saved.target_type === "character"
          ? `/characters/${saved.item_id}`
          : `/worlds/${saved.item_id}`,
      );
    } catch {
      /* error exposed via saveSession.error */
    }
  }

  function resetSession(): void {
    if (isStreamingChat || isGenerating) return;
    saveSession.reset();
    patchWorkspace(currentKey, () => emptyWorkspace());
  }

  function patchGeneratedData(patch: Record<string, unknown>): void {
    saveSession.reset();
    patchWorkspace(currentKey, (prev) => {
      if (!prev.generatedData) return prev;
      const next = { ...prev.generatedData, ...patch };
      return {
        ...prev,
        generatedData: next,
        jsonText: JSON.stringify(next, null, 2),
        jsonInvalid: false,
      };
    });
  }

  function changeJsonText(text: string): void {
    saveSession.reset();
    let parsed: Record<string, unknown> | null = null;
    let invalid = false;
    try {
      const candidate: unknown = JSON.parse(text);
      if (isPlainRecord(candidate)) parsed = candidate;
      else invalid = true;
    } catch {
      invalid = true;
    }
    patchWorkspace(currentKey, (prev) => ({
      ...prev,
      jsonText: text,
      jsonInvalid: invalid,
      ...(parsed ? { generatedData: parsed } : {}),
    }));
  }

  return {
    poolsQuery,
    targetType,
    setTargetType: (next: TargetType) => {
      saveSession.reset();
      setTargetType(next);
    },
    mode,
    setMode: (next: CreatorMode) => {
      saveSession.reset();
      setMode(next);
    },
    currentSeed,
    setCurrentSeed: (next: CreatorSeedState) =>
      setSeedByTarget((prev) => ({ ...prev, [targetType]: next })),
    currentWorkspace,
    patchCurrentWorkspace: (updater: (prev: WorkspaceState) => WorkspaceState) =>
      patchWorkspace(currentKey, updater),
    isStreamingChat,
    isGenerating,
    sendMessage,
    generate,
    save,
    isSaving: saveSession.isPending,
    saveError: saveSession.error,
    resetSaveError: () => saveSession.reset(),
    resetSession,
    patchGeneratedData,
    changeJsonText,
  };
}
