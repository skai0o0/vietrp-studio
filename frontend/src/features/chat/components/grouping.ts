import type { MessageOut } from "@/types/chat";

export interface MessageGroup {
  speaker: string;
  messages: MessageOut[];
}

/** Consecutive messages from the same speaker share one group (avatar + name once). */
export function groupMessages(messages: readonly MessageOut[]): MessageGroup[] {
  const groups: MessageGroup[] = [];
  for (const message of messages) {
    const last = groups[groups.length - 1];
    if (last && last.speaker === message.speaker) last.messages.push(message);
    else groups.push({ speaker: message.speaker, messages: [message] });
  }
  return groups;
}

export const USER_SPEAKER = "user";
export const NARRATOR_SPEAKER = "narrator";

export function activeVariant(message: MessageOut) {
  return message.variants.find((v) => v.idx === message.active_variant) ?? message.variants[0];
}
