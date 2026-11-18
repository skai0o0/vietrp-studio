import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { libraryKeys } from "@/features/library/hooks";
import { ApiError } from "@/lib/apiClient";
import { streamSse, type SseEvent } from "@/lib/sse";
import { creatorApi, type CreatorSaveInput } from "./api";
import type {
  CreatorGenerateIn,
  CreatorSessionCreate,
  CreatorSessionUpdate,
  CreatorStreamEvent,
} from "./types";

export const creatorKeys = {
  all: ["creator"] as const,
  pools: () => ["creator", "pools"] as const,
  session: (sessionId: string | undefined) => ["creator", "session", sessionId] as const,
};

export function useCreatorPools() {
  return useQuery({
    queryKey: creatorKeys.pools(),
    queryFn: creatorApi.getPools,
    staleTime: 5 * 60_000,
  });
}

export function useCreatorSession(sessionId: string | undefined) {
  return useQuery({
    queryKey: creatorKeys.session(sessionId),
    enabled: Boolean(sessionId),
    queryFn: () => creatorApi.getSession(sessionId as string),
  });
}

export function useCreateCreatorSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatorSessionCreate) => creatorApi.createSession(body),
    onSuccess: (session) => {
      client.setQueryData(creatorKeys.session(session.id), session);
    },
  });
}

export function useUpdateCreatorSession(sessionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatorSessionUpdate) => creatorApi.updateSession(sessionId, body),
    onSuccess: (session) => {
      client.setQueryData(creatorKeys.session(sessionId), session);
    },
  });
}

export function useSaveCreatorSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (params: { sessionId: string; body: CreatorSaveInput }) =>
      creatorApi.saveSession(params.sessionId, params.body),
    onSuccess: (saved) => {
      if (saved.target_type === "character") {
        if (saved.character) {
          client.setQueryData(libraryKeys.character(saved.item_id), saved.character);
        }
        void client.invalidateQueries({ queryKey: ["characters"] });
      } else {
        if (saved.world) {
          client.setQueryData(libraryKeys.world(saved.item_id), saved.world);
        }
        void client.invalidateQueries({ queryKey: ["worlds"] });
      }
      void client.invalidateQueries({ queryKey: ["gallery"] });
    },
  });
}

export function toCreatorEvent(raw: SseEvent): CreatorStreamEvent | null {
  const data = raw.data;
  if (typeof data !== "object" || data === null) return null;
  const type = (data as { type?: unknown }).type ?? raw.event;
  if (typeof type !== "string") return null;
  return { ...(data as object), type } as CreatorStreamEvent;
}

export async function runCreatorMessageStream(params: {
  sessionId: string;
  text: string;
  signal?: AbortSignal;
  onEvent: (event: CreatorStreamEvent) => void;
  onError: (code: string) => void;
  onDone?: () => void;
}): Promise<void> {
  await streamSse({
    url: creatorApi.messageUrl(params.sessionId),
    body: { text: params.text },
    ...(params.signal ? { signal: params.signal } : {}),
    onEvent: (raw) => {
      const event = toCreatorEvent(raw);
      if (event) params.onEvent(event);
    },
    onError: (err) => {
      params.onError(err instanceof ApiError ? err.code : "network_error");
    },
    ...(params.onDone ? { onDone: params.onDone } : {}),
  });
}

export async function runCreatorGenerateStream(params: {
  sessionId: string;
  body: CreatorGenerateIn;
  signal?: AbortSignal;
  onEvent: (event: CreatorStreamEvent) => void;
  onError: (code: string) => void;
  onDone?: () => void;
}): Promise<void> {
  await streamSse({
    url: creatorApi.generateUrl(params.sessionId),
    body: params.body,
    ...(params.signal ? { signal: params.signal } : {}),
    onEvent: (raw) => {
      const event = toCreatorEvent(raw);
      if (event) params.onEvent(event);
    },
    onError: (err) => {
      params.onError(err instanceof ApiError ? err.code : "network_error");
    },
    ...(params.onDone ? { onDone: params.onDone } : {}),
  });
}
