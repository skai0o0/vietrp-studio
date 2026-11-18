import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";

interface GreetingSwiperProps {
  /** `null` while no usable card is selected. */
  greetings: readonly string[] | null;
  index: number;
  onIndex: (index: number) => void;
  characterName: string;
  /** Selected persona name; falls back to the same word the backend uses. */
  userName?: string | null;
}

export function GreetingSwiper({ greetings, index, onIndex, characterName, userName }: GreetingSwiperProps) {
  const total = greetings?.length ?? 0;
  return (
    <section aria-labelledby="newchat-greeting" className="flex flex-col gap-2">
      <h2 id="newchat-greeting" className="text-sm font-semibold">
        {t("newChat.step.greeting")}
      </h2>
      {greetings === null ? (
        <p className="text-sm text-muted">{t("newChat.pickCharacterFirst")}</p>
      ) : total === 0 ? (
        <p className="text-sm text-muted">{t("newChat.noGreeting")}</p>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label={t("newChat.prevGreeting")}
              disabled={index <= 0}
              onClick={() => onIndex(index - 1)}
            >
              <ChevronLeft aria-hidden="true" />
            </Button>
            <span data-testid="greeting-counter" className="text-sm tabular-nums">
              {t("newChat.greetingIndex", { index: index + 1, total })}
            </span>
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label={t("newChat.nextGreeting")}
              disabled={index >= total - 1}
              onClick={() => onIndex(index + 1)}
            >
              <ChevronRight aria-hidden="true" />
            </Button>
          </div>
          <p className="whitespace-pre-wrap rounded-lg border border-border bg-surface p-3 font-serif text-sm">
            {greetings[index]
              ?.replaceAll("{{char}}", characterName)
              .replaceAll("{{user}}", userName || t("newChat.userFallback"))}
          </p>
        </>
      )}
    </section>
  );
}
