import { UserRound } from "lucide-react";
import { useEffect, useRef } from "react";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { CastMemberSummary, MessageOut } from "@/types/chat";
import { MessageBubble } from "./MessageBubble";
import { NARRATOR_SPEAKER, USER_SPEAKER, groupMessages } from "./grouping";

interface MessageListProps {
  messages: readonly MessageOut[];
  characterName: string;
  avatarUrl: string | null | undefined;
  cast?: readonly CastMemberSummary[];
  worldName?: string;
  /** Changes whenever new content arrives, to keep the view pinned to the bottom. */
  scrollKey: string | number;
  actionsDisabled?: boolean;
  onSelectVariant?: (messageId: string, variantIdx: number) => Promise<boolean | void> | void;
  onRegenerate?: (messageId: string) => void;
  onEditMessage?: (messageId: string, content: string) => Promise<boolean | void> | void;
  onDeleteMessage?: (messageId: string) => Promise<boolean | void> | void;
  onForkMessage?: (messageId: string, seq: number) => void;
  children?: React.ReactNode;
}

export interface ResolvedSpeaker {
  name: string;
  avatarUrl: string | null | undefined;
  isUser: boolean;
  isNarrator: boolean;
}

export function resolveSpeaker(
  speaker: string,
  cast: readonly CastMemberSummary[] | undefined,
  fallbackName: string,
  fallbackAvatar: string | null | undefined,
): ResolvedSpeaker {
  if (speaker === USER_SPEAKER) {
    return { name: t("chat.message.you"), avatarUrl: null, isUser: true, isNarrator: false };
  }
  if (speaker === NARRATOR_SPEAKER) {
    return { name: t("chat.message.narrator"), avatarUrl: null, isUser: false, isNarrator: true };
  }
  const member = cast?.find((m) => m.id === speaker || m.character_id === speaker);
  if (member) {
    return {
      name: member.name,
      avatarUrl: member.avatar_url ?? null,
      isUser: false,
      isNarrator: false,
    };
  }
  return {
    name: fallbackName || speaker,
    avatarUrl: fallbackAvatar,
    isUser: false,
    isNarrator: false,
  };
}

export function SpeakerAvatar({ url, label }: { url: string | null | undefined; label: string }) {
  return (
    <div className="flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-surface-2 text-xs text-muted">
      {url ? (
        <img src={url} alt="" className="size-full object-cover" />
      ) : (
        <span aria-hidden="true">{label.slice(0, 1)}</span>
      )}
    </div>
  );
}

export function MessageList({
  messages,
  characterName,
  avatarUrl,
  cast,
  worldName,
  scrollKey,
  actionsDisabled = false,
  onSelectVariant,
  onRegenerate,
  onEditMessage,
  onDeleteMessage,
  onForkMessage,
  children,
}: MessageListProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scrollKey]);

  const groups = groupMessages(messages);
  return (
    <div
      ref={ref}
      className="min-h-0 flex-1 overflow-y-auto px-3 py-4 md:px-6"
      role="log"
      aria-live="off"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {worldName ? (
          <p className="text-center text-xs font-medium text-muted">{worldName}</p>
        ) : null}
        {groups.length === 0 && (
          <p className="py-10 text-center text-sm text-muted">{t("chat.page.empty")}</p>
        )}
        {groups.map((group) => {
          const resolved = resolveSpeaker(group.speaker, cast, characterName, avatarUrl);
          const { isUser, isNarrator, name } = resolved;
          const first = group.messages[0];
          return (
            <section
              key={first?.id}
              className={cn(
                "flex gap-2",
                isUser && "flex-row-reverse",
                isNarrator && "justify-center",
              )}
            >
              {!isNarrator &&
                (isUser ? (
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border bg-surface-2 text-muted">
                    <UserRound className="size-4" aria-hidden="true" />
                  </div>
                ) : (
                  <SpeakerAvatar url={resolved.avatarUrl} label={name} />
                ))}
              <div
                className={cn(
                  "flex min-w-0 flex-1 flex-col gap-1",
                  isUser && "items-end",
                  isNarrator && "items-center",
                )}
              >
                {!isNarrator && <span className="text-xs text-muted">{name}</span>}
                {isNarrator && <span className="text-xs italic text-muted">{name}</span>}
                {group.messages.map((message, i) => (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    isFirstInGroup={i === 0}
                    isLastInGroup={i === group.messages.length - 1}
                    disabled={actionsDisabled}
                    onSelectVariant={
                      onSelectVariant
                        ? (variantIdx) => onSelectVariant(message.id, variantIdx)
                        : undefined
                    }
                    onRegenerate={onRegenerate}
                    onEdit={onEditMessage}
                    onDelete={onDeleteMessage}
                    onFork={onForkMessage}
                  />
                ))}
              </div>
            </section>
          );
        })}
        {children}
      </div>
    </div>
  );
}
