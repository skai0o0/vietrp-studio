import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ChatCreate,
  ChatListParams,
  ChatUpdate,
  ForkRequest,
  MessageOut,
  MessagesParams,
  PresetIn,
  StatePatch,
} from "@/types/chat";
import { chatApi, presetApi, utilityApi } from "./api";

export const chatKeys = {
  all: ["chats"] as const,
  list: (params: ChatListParams) => ["chats", "list", params] as const,
  detail: (id: string) => ["chats", "detail", id] as const,
  messages: (id: string) => ["chats", "messages", id] as const,
};

export function useChats(params: ChatListParams = {}) {
  return useQuery({
    queryKey: chatKeys.list(params),
    queryFn: () => chatApi.list(params),
    placeholderData: keepPreviousData,
  });
}

export function useChat(id: string | undefined) {
  return useQuery({
    queryKey: chatKeys.detail(id ?? ""),
    queryFn: () => chatApi.get(id as string),
    enabled: Boolean(id),
  });
}

export function useChatMessages(id: string | undefined, params: MessagesParams = {}) {
  return useQuery({
    queryKey: [...chatKeys.messages(id ?? ""), params],
    queryFn: () => chatApi.messages(id as string, params),
    enabled: Boolean(id),
  });
}

export function useCreateChat() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ChatCreate) => chatApi.create(body),
    onSuccess: () => void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] }),
  });
}

export function useUpdateChat(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ChatUpdate) => chatApi.update(id, body),
    onSuccess: (chat) => {
      client.setQueryData(chatKeys.detail(id), chat);
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
    },
  });
}

export function useDeleteChat() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => chatApi.remove(id),
    onSuccess: (_void, id) => {
      client.removeQueries({ queryKey: chatKeys.detail(id) });
      client.removeQueries({ queryKey: chatKeys.messages(id) });
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
    },
  });
}

export function usePatchState(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: StatePatch) => chatApi.patchState(id, patch),
    onSuccess: (chat) => client.setQueryData(chatKeys.detail(id), chat),
  });
}

export function usePatchBonds(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (bonds: Record<string, unknown>) => chatApi.patchBonds(id, bonds),
    onSuccess: (chat) => client.setQueryData(chatKeys.detail(id), chat),
  });
}

export function useSummarizeChat(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => chatApi.summarize(id),
    onSuccess: (chat) => {
      client.setQueryData(chatKeys.detail(id), chat);
      void client.invalidateQueries({ queryKey: chatKeys.messages(id) });
      void client.invalidateQueries({ queryKey: chatKeys.detail(id) });
    },
  });
}

export function useSetActiveVariant(chatId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId, variantIdx }: { messageId: string; variantIdx: number }) =>
      chatApi.setActiveVariant(chatId, messageId, variantIdx),
    onSuccess: (updated) => {
      client.setQueriesData<MessageOut[]>(
        { queryKey: chatKeys.messages(chatId) },
        (prev) => prev?.map((m) => (m.id === updated.id ? updated : m)) ?? prev,
      );
      void client.invalidateQueries({ queryKey: chatKeys.messages(chatId) });
      void client.invalidateQueries({ queryKey: chatKeys.detail(chatId) });
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
    },
  });
}

export function useEditMessage(chatId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId, content }: { messageId: string; content: string }) =>
      chatApi.editMessage(chatId, messageId, content),
    onSuccess: (updated) => {
      client.setQueriesData<MessageOut[]>(
        { queryKey: chatKeys.messages(chatId) },
        (prev) => prev?.map((m) => (m.id === updated.id ? updated : m)) ?? prev,
      );
      void client.invalidateQueries({ queryKey: chatKeys.messages(chatId) });
      void client.invalidateQueries({ queryKey: chatKeys.detail(chatId) });
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
    },
  });
}

export function useDeleteMessage(chatId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) => chatApi.deleteMessage(chatId, messageId),
    onSuccess: (result) => {
      client.setQueryData(chatKeys.detail(chatId), result.chat);
      void client.invalidateQueries({ queryKey: chatKeys.messages(chatId) });
      void client.invalidateQueries({ queryKey: chatKeys.detail(chatId) });
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
    },
  });
}

export function useUndoChat(chatId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => chatApi.undo(chatId),
    onSuccess: (result) => {
      client.setQueryData(chatKeys.detail(chatId), result.chat);
      void client.invalidateQueries({ queryKey: chatKeys.messages(chatId) });
      void client.invalidateQueries({ queryKey: chatKeys.detail(chatId) });
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
    },
  });
}

export function useForkChat(chatId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ForkRequest = {}) => chatApi.fork(chatId, body),
    onSuccess: (forked) => {
      client.setQueryData(chatKeys.detail(forked.id), forked);
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
    },
  });
}

/** Prompt Inspector data; the caller passes `enabled=false` until the sheet opens. */
export function usePromptPreview(
  id: string | undefined,
  text: string,
  enabled = true,
  speaker?: string,
) {
  return useQuery({
    queryKey: ["chats", "prompt-preview", id ?? "", text, speaker ?? ""],
    queryFn: () => chatApi.promptPreview(id as string, text, speaker),
    enabled: Boolean(id) && enabled,
    staleTime: 0,
  });
}

export function useModels() {
  return useQuery({ queryKey: ["models"], queryFn: utilityApi.models, staleTime: 5 * 60_000 });
}

export function useChatUsage(chatId: string | undefined) {
  return useQuery({
    queryKey: ["usage", chatId ?? ""],
    queryFn: () => utilityApi.usage(chatId as string),
    enabled: Boolean(chatId),
  });
}

export function usePresets() {
  return useQuery({ queryKey: ["presets"], queryFn: presetApi.list });
}

export function useSavePreset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: PresetIn }) =>
      id ? presetApi.update(id, body) : presetApi.create(body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["presets"] }),
  });
}

export function useDeletePreset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => presetApi.remove(id),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["presets"] }),
  });
}
