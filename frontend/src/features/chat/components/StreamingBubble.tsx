import { Check, Loader2 } from "lucide-react";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { CastMemberSummary } from "@/types/chat";
import type { SpeakerTurnBuffer, TurnState } from "../store";
import { resolveSpeaker, SpeakerAvatar } from "./MessageList";
import { ReasoningBlock } from "./ReasoningBlock";
import { RpText } from "./RpText";
import { NARRATOR_SPEAKER } from "./grouping";

interface StreamingBubbleProps {
  turn: TurnState;
  /** `hold_until_approved`: do not show text before the Director approves; show progress only. */
  holdUntilApproved: boolean;
  cast?: readonly CastMemberSummary[];
}

function streamStatusText(
  entry: Pick<SpeakerTurnBuffer, "attempt" | "directorPending" | "isDraft" | "done" | "stopped">,
  holdUntilApproved: boolean,
): { text: string; holding: boolean; muted: boolean } {
  const holding = holdUntilApproved && entry.directorPending;
  const muted = entry.isDraft || entry.directorPending;
  if (entry.stopped) return { text: t("chat.message.stopped"), holding: false, muted: false };
  if (entry.done) return { text: t("chat.stream.done"), holding: false, muted: false };
  if (entry.attempt > 0 && entry.directorPending) {
    return { text: t("chat.stream.rewriting", { attempt: entry.attempt }), holding, muted };
  }
  if (holding) return { text: t("chat.stream.holding"), holding, muted };
  if (entry.isDraft || entry.directorPending) {
    return { text: t("chat.stream.draft"), holding, muted };
  }
  return { text: t("chat.stream.writing"), holding, muted };
}

function SpeakerStreamRow({
  entry,
  holdUntilApproved,
  cast,
}: {
  entry: SpeakerTurnBuffer;
  holdUntilApproved: boolean;
  cast?: readonly CastMemberSummary[];
}) {
  const resolved = resolveSpeaker(entry.speaker, cast, entry.speaker, null);
  const { text: status, holding, muted } = streamStatusText(entry, holdUntilApproved);

  return (
    <div
      data-speaker={entry.speaker}
      className={cn("flex gap-2", resolved.isNarrator && "justify-center")}
    >
      {!resolved.isNarrator ? (
        <SpeakerAvatar url={resolved.avatarUrl} label={resolved.name} />
      ) : null}
      <div
        className={cn(
          "flex min-w-0 flex-1 flex-col gap-1",
          resolved.isNarrator ? "items-center" : "items-start",
        )}
      >
        <span className={cn("text-xs text-muted", resolved.isNarrator && "italic")}>
          {resolved.name}
        </span>
        <div
          className={cn(
            "max-w-[92%] rounded-lg border border-border bg-surface px-3 py-2 md:max-w-[75%]",
            resolved.isNarrator && "border-dashed bg-surface/40 text-center italic",
            entry.stopped && "opacity-80",
          )}
        >
          <ReasoningBlock
            text={entry.reasoning}
            attempt={entry.attempt}
            thinking={
              !entry.done && !entry.stopped && entry.buffer === "" && !entry.directorPending
            }
          />
          {!holding && entry.buffer !== "" ? (
            <div
              data-draft={muted || undefined}
              className={cn(muted && "border-l-2 border-dashed border-accent/60 pl-2.5 text-fg/85")}
            >
              <RpText text={entry.buffer} />
            </div>
          ) : null}
          {entry.done ? (
            <p className="mt-1 flex items-center gap-1 text-xs text-muted">
              {!entry.stopped ? <Check className="size-3" aria-hidden="true" /> : null}
              {status}
            </p>
          ) : (
            <p role="status" className="mt-1 flex items-center gap-1 text-xs text-muted">
              <Loader2 className="size-3 motion-safe:animate-spin" aria-hidden="true" />
              {status}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/** The in-flight reply. Multi-speaker aware; falls back cleanly to single-speaker buffer. */
export function StreamingBubble({ turn, holdUntilApproved, cast }: StreamingBubbleProps) {
  if (turn.status !== "streaming") {
    return null;
  }

  if (
    turn.speaker === null &&
    turn.speakerOrder.length === 0 &&
    turn.buffer === "" &&
    !turn.directorPending
  ) {
    return (
      <div
        data-testid="streaming-bubble"
        data-preparing="true"
        aria-live="polite"
        className="flex items-start gap-2"
      >
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border bg-surface-2 text-muted">
          <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" />
        </div>
        <div className="flex max-w-[75%] flex-col gap-2 rounded-lg border border-border-subtle bg-surface px-3.5 py-2.5">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-24 rounded bg-surface-2 motion-safe:animate-pulse" />
            <span className="h-2.5 w-16 rounded bg-surface-2 motion-safe:animate-pulse" />
          </div>
          <p role="status" className="text-xs text-muted">
            {t("chat.stream.preparing")}
          </p>
        </div>
      </div>
    );
  }

  if (turn.speakerOrder.length > 0) {
    return (
      <div data-testid="streaming-bubble" aria-live="polite" className="flex flex-col gap-3">
        {turn.speakerOrder.map((messageId) => {
          const entry = turn.speakerBuffers[messageId];
          if (!entry) return null;
          return (
            <SpeakerStreamRow
              key={messageId}
              entry={entry}
              holdUntilApproved={holdUntilApproved}
              cast={cast}
            />
          );
        })}
      </div>
    );
  }

  const {
    text: status,
    holding,
    muted,
  } = streamStatusText(
    {
      attempt: turn.attempt,
      directorPending: turn.directorPending,
      isDraft: turn.isDraft,
      done: false,
      stopped: false,
    },
    holdUntilApproved,
  );
  return (
    <div
      data-testid="streaming-bubble"
      aria-live="polite"
      className={cn(
        "flex flex-col",
        turn.speaker === NARRATOR_SPEAKER ? "items-center" : "items-start",
      )}
    >
      <div className="max-w-[92%] rounded-lg border border-border bg-surface px-3.5 py-2.5 md:max-w-[75%]">
        {!holding && turn.buffer !== "" && (
          <div
            data-draft={muted || undefined}
            className={cn(muted && "border-l-2 border-dashed border-accent/60 pl-2.5 text-fg/85")}
          >
            <RpText text={turn.buffer} />
          </div>
        )}
        <p role="status" className="mt-1 flex items-center gap-1 text-xs text-muted">
          <Loader2 className="size-3 motion-safe:animate-spin" aria-hidden="true" />
          {status}
        </p>
      </div>
    </div>
  );
}
