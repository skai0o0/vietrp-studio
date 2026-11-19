import { ArrowDown, Archive, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { CastMemberSummary, MessageOut } from "@/types/chat";
import { MessageBubble } from "./MessageBubble";
import { RpText } from "./RpText";
import { NARRATOR_SPEAKER, USER_SPEAKER, groupMessages } from "./grouping";

interface MessageListProps {
  messages: readonly MessageOut[];
  characterName: string;
  avatarUrl: string | null | undefined;
  cast?: readonly CastMemberSummary[];
  worldName?: string;
  summaryUpto?: number;
  optimisticUserMessage?: string | null;
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

const STICKY_THRESHOLD_PX = 64;

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
  summaryUpto = 0,
  optimisticUserMessage,
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
  const atBottomRef = useRef(true);
  const [showJumpButton, setShowJumpButton] = useState(false);

  function handleScroll() {
    const el = ref.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const nearBottom = distanceFromBottom <= STICKY_THRESHOLD_PX;
    atBottomRef.current = nearBottom;
    if (nearBottom) setShowJumpButton(false);
  }

  function jumpToBottom() {
    const el = ref.current;
    if (!el) return;
    atBottomRef.current = true;
    el.scrollTop = el.scrollHeight;
    setShowJumpButton(false);
  }

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (atBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    } else {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (distanceFromBottom > STICKY_THRESHOLD_PX) {
        setShowJumpButton(true);
      }
    }
  }, [scrollKey]);

  const groups = groupMessages(messages);

  let dividerAfterGroup = -1;
  if (summaryUpto > 0) {
    groups.forEach((group, idx) => {
      if (group.messages.some((m) => m.seq <= summaryUpto)) {
        dividerAfterGroup = idx;
      }
    });
  }

  const lastMessage = messages[messages.length - 1];
  const lastVariantText =
    lastMessage?.variants.find((v) => v.idx === lastMessage.active_variant)?.content ??
    lastMessage?.variants[0]?.content ??
    "";
  const showOptimisticUser =
    Boolean(optimisticUserMessage?.trim()) &&
    !(
      lastMessage?.speaker === USER_SPEAKER &&
      lastVariantText.trim() === optimisticUserMessage?.trim()
    );

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={ref}
        onScroll={handleScroll}
        className="h-full overflow-y-auto px-3 py-4 md:px-6"
        role="log"
        aria-live="off"
      >
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {worldName ? (
            <p className="text-center text-xs font-medium text-muted">{worldName}</p>
          ) : null}
          {groups.length === 0 && !showOptimisticUser && (
            <div className="flex flex-col items-center gap-1 py-10 text-center">
              <p className="text-sm font-medium text-fg">{t("chat.page.empty")}</p>
              <p className="text-xs text-muted">{t("chat.page.emptyHint")}</p>
            </div>
          )}
          {groups.map((group, groupIdx) => {
            const resolved = resolveSpeaker(group.speaker, cast, characterName, avatarUrl);
            const { isUser, isNarrator, name } = resolved;
            const first = group.messages[0];
            return (
              <div key={first?.id} className="flex flex-col gap-4">
                <section
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

                {dividerAfterGroup === groupIdx ? (
                  <div
                    role="separator"
                    className="my-1 flex items-center gap-3 text-2xs text-muted"
                  >
                    <span className="h-px flex-1 bg-border-subtle" />
                    <span className="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-surface px-2.5 py-0.5">
                      <Archive className="size-3 shrink-0" aria-hidden="true" />
                      {t("chat.page.summaryDivider", { seq: summaryUpto })}
                    </span>
                    <span className="h-px flex-1 bg-border-subtle" />
                  </div>
                ) : null}
              </div>
            );
          })}
          {showOptimisticUser ? (
            <section data-optimistic="true" className="flex flex-row-reverse gap-2">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border bg-surface-2 text-muted">
                <UserRound className="size-4" aria-hidden="true" />
              </div>
              <div className="flex min-w-0 flex-1 flex-col items-end gap-1">
                <span className="text-xs text-muted">{t("chat.message.you")}</span>
                <div className="max-w-[92%] rounded-lg border border-accent/40 bg-surface-2 px-3 py-2 text-fg opacity-85 md:max-w-[75%]">
                  <RpText text={optimisticUserMessage ?? ""} />
                  <p role="status" className="mt-1 text-right text-2xs text-muted">
                    {t("chat.page.sending")}
                  </p>
                </div>
              </div>
            </section>
          ) : null}
          {children}
        </div>
      </div>
      {showJumpButton ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={jumpToBottom}
          className="absolute bottom-3 left-1/2 z-sticky -translate-x-1/2 rounded-full border-border-strong shadow-popover"
        >
          <ArrowDown className="size-3.5" aria-hidden="true" />
          <span>{t("chat.page.jumpToBottom")}</span>
        </Button>
      ) : null}
    </div>
  );
}
