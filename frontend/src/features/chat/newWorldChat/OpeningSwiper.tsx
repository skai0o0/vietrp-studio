import { ChevronLeft, ChevronRight, Clock, MapPin, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { pathLabel } from "@/features/library/world/treeOps";
import { t } from "@/i18n";
import type { WorldOut } from "@/types/library";

interface OpeningSwiperProps {
  world: WorldOut | undefined;
  isLoading?: boolean;
  isError?: boolean;
  index: number;
  onIndex: (index: number) => void;
  userName?: string | null;
}

type TensionKey = "t0" | "t1" | "t2" | "t3" | "t4";

export function OpeningSwiper({
  world,
  isLoading = false,
  isError = false,
  index,
  onIndex,
  userName,
}: OpeningSwiperProps) {
  const openings = world?.data.openings ?? [];
  const locations = world?.data.locations ?? [];
  const total = openings.length;
  const safeIndex = total > 0 ? Math.min(Math.max(0, index), total - 1) : 0;
  const opening = openings[safeIndex];

  const tensionLevel = Math.min(4, Math.max(0, Math.round(opening?.tension ?? 0)));
  const tensionKey: TensionKey = `t${tensionLevel}` as TensionKey;
  const locationText = opening
    ? pathLabel(locations, opening.location_id) ||
      opening.location_id ||
      t("worldChat.unknownLocation")
    : "";
  const previewMessage = (opening?.message ?? "").replaceAll(
    "{{user}}",
    userName || t("newChat.userFallback"),
  );

  return (
    <section aria-labelledby="worldchat-opening" className="flex flex-col gap-2">
      <h2 id="worldchat-opening" className="text-sm font-semibold">
        {t("worldChat.step.opening")}
      </h2>
      {isError ? (
        <p role="alert" className="text-sm text-danger">
          {t("worldChat.worldLoadFailed")}
        </p>
      ) : !world && isLoading ? (
        <p role="status" className="text-sm text-muted">
          {t("newChat.loading")}
        </p>
      ) : !world ? (
        <p className="text-sm text-muted">{t("worldChat.pickWorldFirst")}</p>
      ) : total === 0 || !opening ? (
        <p className="text-sm text-muted">{t("worldChat.noOpenings")}</p>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label={t("worldChat.prevOpening")}
              disabled={safeIndex <= 0}
              onClick={() => onIndex(safeIndex - 1)}
            >
              <ChevronLeft aria-hidden="true" />
            </Button>
            <span data-testid="opening-counter" className="text-sm tabular-nums">
              {t("worldChat.openingIndex", { index: safeIndex + 1, total })}
            </span>
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label={t("worldChat.nextOpening")}
              disabled={safeIndex >= total - 1}
              onClick={() => onIndex(safeIndex + 1)}
            >
              <ChevronRight aria-hidden="true" />
            </Button>
          </div>
          <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">
                {opening.title?.trim() || t("worldChat.openingFallback", { n: safeIndex + 1 })}
              </h3>
              <span
                data-testid="opening-tension"
                className="rounded-sm border border-border bg-surface-2 px-2 py-0.5 text-xs font-medium text-fg"
              >
                {t(`library.world.tension.${tensionKey}`)}
              </span>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
              <span className="inline-flex items-center gap-1">
                <MapPin className="size-3.5 shrink-0" aria-hidden="true" />
                <span>{locationText}</span>
              </span>
              {opening.time ? (
                <span className="inline-flex items-center gap-1">
                  <Clock className="size-3.5 shrink-0" aria-hidden="true" />
                  <span>{opening.time}</span>
                </span>
              ) : null}
              {opening.player_role ? (
                <span className="inline-flex items-center gap-1">
                  <UserRound className="size-3.5 shrink-0" aria-hidden="true" />
                  <span>
                    {t("worldChat.playerRole")}: {opening.player_role}
                  </span>
                </span>
              ) : null}
            </div>
            {previewMessage ? (
              <p className="whitespace-pre-wrap break-words font-content text-sm leading-relaxed">
                {previewMessage}
              </p>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}
