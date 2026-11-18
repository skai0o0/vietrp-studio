import { apiClient } from "@/lib/apiClient";
import { buildQuery } from "@/features/library/api";
import type {
  ActiveVariantRequest,
  ChatCreate,
  ChatListParams,
  ChatOut,
  ChatSummary,
  ChatUpdate,
  ForkRequest,
  MessageOut,
  MessageUpdate,
  MessagesParams,
  ModelInfo,
  PresetIn,
  PresetOut,
  PromptPreview,
  StatePatch,
  StopResult,
  TokenCount,
  UndoResult,
  UsageRow,
} from "@/types/chat";

const BASE = "/api/chats";

export const chatApi = {
  list: (params: ChatListParams = {}) =>
    apiClient.get<ChatSummary[]>(`${BASE}${buildQuery(params)}`),
  get: (id: string) => apiClient.get<ChatOut>(`${BASE}/${id}`),
  create: (body: ChatCreate) => apiClient.post<ChatOut>(BASE, body),
  update: (id: string, body: ChatUpdate) => apiClient.patch<ChatOut>(`${BASE}/${id}`, body),
  remove: (id: string) => apiClient.delete<void>(`${BASE}/${id}`),
  messages: (id: string, params: MessagesParams = {}) =>
    apiClient.get<MessageOut[]>(`${BASE}/${id}/messages${buildQuery(params)}`),
  stop: (id: string) => apiClient.post<StopResult>(`${BASE}/${id}/stop`),
  promptPreview: (id: string, text: string, speaker?: string) =>
    apiClient.get<PromptPreview>(
      `${BASE}/${id}/prompt-preview${buildQuery(speaker ? { text, speaker } : { text })}`,
    ),
  patchState: (id: string, patch: StatePatch): Promise<ChatOut> =>
    apiClient.patch<ChatOut>(`${BASE}/${id}/state`, patch),
  patchBonds: (id: string, bonds: Record<string, unknown>): Promise<ChatOut> =>
    chatApi.patchState(id, { bonds }),
  summarize: (id: string): Promise<ChatOut> => apiClient.post<ChatOut>(`${BASE}/${id}/summarize`),
  setActiveVariant: (chatId: string, messageId: string, variantIdx: number): Promise<MessageOut> =>
    apiClient.put<MessageOut>(`${BASE}/${chatId}/messages/${messageId}/active-variant`, {
      variant_idx: variantIdx,
    } satisfies ActiveVariantRequest),
  editMessage: (chatId: string, messageId: string, content: string): Promise<MessageOut> =>
    apiClient.patch<MessageOut>(`${BASE}/${chatId}/messages/${messageId}`, {
      content,
    } satisfies MessageUpdate),
  deleteMessage: (chatId: string, messageId: string): Promise<UndoResult> =>
    apiClient.delete<UndoResult>(`${BASE}/${chatId}/messages/${messageId}`),
  undo: (chatId: string): Promise<UndoResult> =>
    apiClient.post<UndoResult>(`${BASE}/${chatId}/undo`),
  fork: (chatId: string, body: ForkRequest = {}): Promise<ChatOut> =>
    apiClient.post<ChatOut>(`${BASE}/${chatId}/fork`, body),
  turnUrl: (id: string) => `${BASE}/${id}/turn`,
  continueUrl: (id: string) => `${BASE}/${id}/continue`,
  regenerateUrl: (id: string, messageId: string) =>
    `${BASE}/${id}/messages/${messageId}/regenerate`,
};

export const presetApi = {
  list: () => apiClient.get<PresetOut[]>("/api/presets"),
  create: (body: PresetIn) => apiClient.post<PresetOut>("/api/presets", body),
  update: (id: string, body: PresetIn) => apiClient.put<PresetOut>(`/api/presets/${id}`, body),
  remove: (id: string) => apiClient.delete<void>(`/api/presets/${id}`),
};

export const utilityApi = {
  models: () => apiClient.get<ModelInfo[]>("/api/models"),
  countTokens: (text: string) => apiClient.post<TokenCount>("/api/tokens/count", { text }),
  usage: (chatId: string) =>
    apiClient.get<UsageRow[]>(`/api/usage${buildQuery({ chat_id: chatId })}`),
};
