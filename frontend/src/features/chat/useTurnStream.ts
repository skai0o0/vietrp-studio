import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";
import { ApiError } from "@/lib/apiClient";
import { streamSse, type SseEvent } from "@/lib/sse";
import type { ChatOut, TurnStreamEvent } from "@/types/chat";
import { chatApi } from "./api";
import { chatKeys } from "./hooks";
import { initialTurnState, useChatStreamStore, type TurnState } from "./store";

export interface SendOptions {
  text: string;
  prefill?: string;
}

export interface UseTurnStream {
  turn: TurnState;
  isStreaming: boolean;
  /** Resolves false when the request failed before the stream started (text can be restored). */
  send: (options: SendOptions) => Promise<boolean>;
  continueTurn: (prefill?: string) => Promise<boolean>;
  regenerate: (messageId: string, prefill?: string) => Promise<boolean>;
  stop: () => Promise<void>;
  reset: () => void;
}

/** The wire carries the event name in both the SSE `event:` line and `data.type`. */
function toTurnEvent(raw: SseEvent): TurnStreamEvent | null {
  const data = raw.data;
  if (typeof data !== "object" || data === null) return null;
  const type = (data as { type?: unknown }).type ?? raw.event;
  if (typeof type !== "string") return null;
  return { ...(data as object), type } as TurnStreamEvent;
}

function mergeCachedChatState(
  client: ReturnType<typeof useQueryClient>,
  chatId: string,
  patch: Record<string, unknown>,
): void {
  const key = chatKeys.detail(chatId);
  if (!client.getQueryData<ChatOut>(key)) return;
  client.setQueryData<ChatOut>(key, (prev) =>
    prev ? { ...prev, state: { ...prev.state, ...patch } } : prev,
  );
}

export function useTurnStream(chatId: string): UseTurnStream {
  const client = useQueryClient();
  const turn = useChatStreamStore((s) => s.turns[chatId]) ?? initialTurnState;
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), [chatId]);

  const refresh = useCallback(() => {
    void client.invalidateQueries({ queryKey: chatKeys.messages(chatId) });
    void client.invalidateQueries({ queryKey: chatKeys.detail(chatId) });
    void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
  }, [client, chatId]);

  const runStream = useCallback(
    async (url: string, body: unknown, refreshOnError: boolean): Promise<boolean> => {
      if (controllerRef.current) return false;
      const controller = new AbortController();
      controllerRef.current = controller;
      useChatStreamStore.getState().begin(chatId);
      let settled = false;
      let started = false;
      let failedEarly = false;
      await streamSse({
        url,
        body,
        signal: controller.signal,
        onEvent: (raw) => {
          const event = toTurnEvent(raw);
          if (!event) return;
          started = true;
          useChatStreamStore.getState().apply(chatId, event);
          if (event.type === "state") {
            mergeCachedChatState(client, chatId, event.state as Record<string, unknown>);
          } else if (event.type === "bonds") {
            mergeCachedChatState(client, chatId, { bonds: event.bonds });
          } else if (event.type === "archivist") {
            if (event.summary != null) {
              mergeCachedChatState(client, chatId, { summary: event.summary });
            }
          } else if (event.type === "done") {
            settled = true;
            refresh();
          } else if (event.type === "error") {
            settled = true;
            const current = useChatStreamStore.getState().turns[chatId];
            const hasSavedSpeaker = Object.values(current?.speakerBuffers ?? {}).some(
              (entry) => entry.done,
            );
            if (
              refreshOnError ||
              (current &&
                (hasSavedSpeaker ||
                  current.liveState !== null ||
                  current.liveBonds !== null ||
                  current.liveSummary !== null))
            ) {
              refresh();
            }
          }
        },
        onError: (error) => {
          settled = true;
          if (!started) failedEarly = true;
          const code = error instanceof ApiError ? error.code : "network_error";
          useChatStreamStore.getState().fail(chatId, code);
        },
        onDone: () => {
          if (settled) return;
          // Aborted (stop) or closed early: reload what the server persisted.
          useChatStreamStore.getState().finish(chatId);
          refresh();
        },
      });
      controllerRef.current = null;
      return !failedEarly;
    },
    [chatId, client, refresh],
  );

  const send = useCallback(
    ({ text, prefill }: SendOptions) =>
      runStream(chatApi.turnUrl(chatId), { text, ...(prefill ? { prefill } : {}) }, false),
    [chatId, runStream],
  );

  const continueTurn = useCallback(
    (prefill?: string) => runStream(chatApi.continueUrl(chatId), prefill ? { prefill } : {}, false),
    [chatId, runStream],
  );

  const regenerate = useCallback(
    (messageId: string, prefill?: string) =>
      runStream(chatApi.regenerateUrl(chatId, messageId), prefill ? { prefill } : {}, true),
    [chatId, runStream],
  );

  const stop = useCallback(async () => {
    // Ask the server first so the partial text is saved, then drop the connection.
    try {
      await chatApi.stop(chatId);
    } catch {
      /* the abort below still ends the stream */
    }
    controllerRef.current?.abort();
  }, [chatId]);

  const reset = useCallback(() => useChatStreamStore.getState().clear(chatId), [chatId]);

  return {
    turn,
    isStreaming: turn.status === "streaming",
    send,
    continueTurn,
    regenerate,
    stop,
    reset,
  };
}
