import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ChatCreate,
  ChatListParams,
  ChatOut,
  ChatUpdate,
  ForkRequest,
  MessageOut,
  MessagesParams,
  PresetIn,
  StatePatch,
} from "@/types/chat";
import { chatApi, presetApi, utilityApi } from "./api";
import { useChatStreamStore } from "./store";

export const chatKeys = {
  all: ["chats"] as const,
  list: (params: ChatListParams) => ["chats", "list", params] as const,
  detail: (id: string) => ["chats", "detail", id] as const,
  messages: (id: string) => ["chats", "messages", id] as const,
  promptPreview: (id: string) => ["chats", "prompt-preview", id] as const,
  usage: (id: string) => ["usage", id] as const,
};

function invalidateChatDerived(client: ReturnType<typeof useQueryClient>, chatId: string): void {
  void client.invalidateQueries({ queryKey: chatKeys.promptPreview(chatId) });
  void client.invalidateQueries({ queryKey: chatKeys.usage(chatId) });
}

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
    onMutate: async (body) => {
      await client.cancelQueries({ queryKey: chatKeys.detail(id) });
      const previous = client.getQueryData<ChatOut>(chatKeys.detail(id));
      if (previous) {
        client.setQueryData<ChatOut>(chatKeys.detail(id), {
          ...previous,
          ...(body.title !== undefined && body.title !== null ? { title: body.title } : {}),
          ...("persona_id" in body ? { persona_id: body.persona_id ?? null } : {}),
          ...(body.settings ? { settings: body.settings } : {}),
        });
      }
      return { previous };
    },
    onError: (_err, _body, context) => {
      if (context?.previous) {
        client.setQueryData(chatKeys.detail(id), context.previous);
      }
    },
    onSuccess: (chat) => {
      client.setQueryData(chatKeys.detail(id), chat);
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
      void client.invalidateQueries({ queryKey: chatKeys.promptPreview(id) });
    },
  });
}

export function useDeleteChat() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => chatApi.remove(id),
    onSuccess: (_void, id) => {
      useChatStreamStore.getState().clear(id);
      client.removeQueries({ queryKey: chatKeys.detail(id) });
      client.removeQueries({ queryKey: chatKeys.messages(id) });
      client.removeQueries({ queryKey: chatKeys.promptPreview(id) });
      client.removeQueries({ queryKey: chatKeys.usage(id) });
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
    },
  });
}

export function usePatchState(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: StatePatch) => chatApi.patchState(id, patch),
    onSuccess: (chat) => {
      client.setQueryData(chatKeys.detail(id), chat);
      void client.invalidateQueries({ queryKey: chatKeys.promptPreview(id) });
    },
  });
}

export function usePatchBonds(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (bonds: Record<string, unknown>) => chatApi.patchBonds(id, bonds),
    onSuccess: (chat) => {
      client.setQueryData(chatKeys.detail(id), chat);
      void client.invalidateQueries({ queryKey: chatKeys.promptPreview(id) });
    },
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
      void client.invalidateQueries({ queryKey: chatKeys.promptPreview(id) });
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
      void client.invalidateQueries({ queryKey: chatKeys.promptPreview(chatId) });
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
      void client.invalidateQueries({ queryKey: chatKeys.promptPreview(chatId) });
    },
  });
}

export function useDeleteMessage(chatId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) => chatApi.deleteMessage(chatId, messageId),
    onSuccess: (result) => {
      useChatStreamStore.getState().clear(chatId);
      client.setQueryData(chatKeys.detail(chatId), result.chat);
      void client.invalidateQueries({ queryKey: chatKeys.messages(chatId) });
      void client.invalidateQueries({ queryKey: chatKeys.detail(chatId) });
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
      invalidateChatDerived(client, chatId);
    },
  });
}

export function useUndoChat(chatId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => chatApi.undo(chatId),
    onSuccess: (result) => {
      useChatStreamStore.getState().clear(chatId);
      client.setQueryData(chatKeys.detail(chatId), result.chat);
      void client.invalidateQueries({ queryKey: chatKeys.messages(chatId) });
      void client.invalidateQueries({ queryKey: chatKeys.detail(chatId) });
      void client.invalidateQueries({ queryKey: [...chatKeys.all, "list"] });
      invalidateChatDerived(client, chatId);
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
    queryKey: [...chatKeys.promptPreview(id ?? ""), text, speaker ?? ""],
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
    queryKey: chatKeys.usage(chatId ?? ""),
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
