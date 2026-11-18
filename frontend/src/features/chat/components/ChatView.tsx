import { GitBranch } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import {
  useChat,
  useChatMessages,
  useDeleteMessage,
  useEditMessage,
  useForkChat,
  useSetActiveVariant,
  useUndoChat,
} from "../hooks";
import { WorldPromptInspector } from "../state/WorldPromptInspector";
import { useTurnStream } from "../useTurnStream";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import { NoticeList } from "./NoticeList";
import { PromptInspector } from "./PromptInspector";
import { StreamingBubble } from "./StreamingBubble";
import { usePromptPreview } from "./usePromptPreview";

interface ChatViewProps {
  chatId: string;
}

function errorCodeFrom(error: unknown): string {
  return error instanceof ApiError ? error.code : "unknown";
}

/** Chat screen: message list, in-flight turn, notices, input with token bar, Prompt Inspector. */
export function ChatView({ chatId }: ChatViewProps) {
  const navigate = useNavigate();
  const chat = useChat(chatId);
  const messages = useChatMessages(chatId);
  const { turn, isStreaming, send, continueTurn, regenerate, stop } = useTurnStream(chatId);
  const setActiveVariant = useSetActiveVariant(chatId);
  const editMessage = useEditMessage(chatId);
  const deleteMessage = useDeleteMessage(chatId);
  const undoChat = useUndoChat(chatId);
  const forkChat = useForkChat(chatId);
  const [draftText, setDraftText] = useState("");
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [selectedSpeaker, setSelectedSpeaker] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const isWorld = chat.data?.mode === "world";
  const defaultSpeaker =
    chat.data?.settings.group?.write_mode === "single_call"
      ? "group"
      : (chat.data?.cast?.[0]?.id ?? "narrator");
  const previewSpeaker = selectedSpeaker ?? defaultSpeaker;
  const preview = usePromptPreview(chatId, draftText, isWorld ? previewSpeaker : undefined);

  if (chat.isError || messages.isError) {
    return <p className="p-6 text-center text-sm text-danger">{t("chat.page.loadFailed")}</p>;
  }
  if (!chat.data) {
    return <p className="p-6 text-center text-sm text-muted">{t("chat.page.loading")}</p>;
  }

  const holdUntilApproved = chat.data.settings.director?.stream_mode === "hold_until_approved";
  const list = messages.data ?? [];
  const cast = chat.data.cast;
  const isActionPending =
    setActiveVariant.isPending ||
    editMessage.isPending ||
    deleteMessage.isPending ||
    undoChat.isPending ||
    forkChat.isPending;
  const canUndo = list.some((m) => m.seq >= 1);

  async function handleSelectVariant(messageId: string, variantIdx: number) {
    setActionError(null);
    try {
      await setActiveVariant.mutateAsync({ messageId, variantIdx });
      return true;
    } catch (error) {
      setActionError(errorCodeFrom(error));
      return false;
    }
  }

  async function handleEdit(messageId: string, content: string) {
    setActionError(null);
    try {
      await editMessage.mutateAsync({ messageId, content });
      return true;
    } catch (error) {
      setActionError(errorCodeFrom(error));
      return false;
    }
  }

  async function handleDelete(messageId: string) {
    setActionError(null);
    try {
      await deleteMessage.mutateAsync(messageId);
      return true;
    } catch (error) {
      setActionError(errorCodeFrom(error));
      return false;
    }
  }

  async function handleUndo() {
    setActionError(null);
    try {
      await undoChat.mutateAsync();
    } catch (error) {
      setActionError(errorCodeFrom(error));
    }
  }

  async function handleFork(messageId: string, seq: number) {
    setActionError(null);
    try {
      const forked = await forkChat.mutateAsync({ message_id: messageId, upto_seq: seq });
      navigate(`/chat/${forked.id}`);
    } catch (error) {
      setActionError(errorCodeFrom(error));
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg">
      {chat.data.parent_chat_id ? (
        <div className="flex items-center gap-2 border-b border-border bg-surface px-3 py-1.5 text-xs text-muted md:px-6">
          <GitBranch className="size-3.5 shrink-0 text-accent-2" aria-hidden="true" />
          <span className="truncate">
            {t("chat.message.forkedAt", { seq: chat.data.forked_at_seq ?? 0 })}
          </span>
          <Link
            to={`/chat/${chat.data.parent_chat_id}`}
            className="ml-auto shrink-0 text-accent-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            {t("chat.message.forkParentLink")}
          </Link>
        </div>
      ) : null}
      <MessageList
        messages={list}
        characterName={chat.data.character_name ?? ""}
        avatarUrl={chat.data.avatar_url}
        cast={cast}
        worldName={chat.data.world_name ?? undefined}
        scrollKey={`${list.length}:${turn.speakerOrder.length}:${turn.buffer.length}:${turn.status}`}
        actionsDisabled={isStreaming || isActionPending}
        onSelectVariant={handleSelectVariant}
        onRegenerate={(messageId) => {
          setActionError(null);
          void regenerate(messageId);
        }}
        onEditMessage={handleEdit}
        onDeleteMessage={handleDelete}
        onForkMessage={handleFork}
      >
        <StreamingBubble turn={turn} holdUntilApproved={holdUntilApproved} cast={cast} />
        <NoticeList notices={turn.notices} errorCode={turn.errorCode ?? actionError} />
      </MessageList>
      <ChatInput
        isStreaming={isStreaming}
        usedTokens={preview.data?.total_tokens ?? null}
        budget={preview.data?.budget ?? null}
        onSend={(text, prefill) => {
          setActionError(null);
          return send({ text, prefill });
        }}
        onContinue={(prefill) => {
          setActionError(null);
          return continueTurn(prefill);
        }}
        onUndo={() => void handleUndo()}
        canContinue
        canUndo={canUndo}
        isActionPending={isActionPending}
        onStop={() => void stop()}
        onOpenInspector={() => setInspectorOpen(true)}
        onTextChange={setDraftText}
      />
      {isWorld ? (
        <WorldPromptInspector
          open={inspectorOpen}
          onOpenChange={setInspectorOpen}
          preview={preview.data}
          isLoading={preview.isLoading}
          isError={preview.isError}
          speaker={previewSpeaker}
          onSpeakerChange={setSelectedSpeaker}
          cast={cast ?? []}
        />
      ) : (
        <PromptInspector
          open={inspectorOpen}
          onOpenChange={setInspectorOpen}
          preview={preview.data}
          isLoading={preview.isLoading}
          isError={preview.isError}
        />
      )}
    </div>
  );
}
