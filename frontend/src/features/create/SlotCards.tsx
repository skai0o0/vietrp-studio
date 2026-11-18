import { ChevronLeft, ChevronRight, Lock, PencilLine, Unlock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { t, type MessageKey } from "@/i18n";
import { cn } from "@/lib/cn";
import type { TargetType } from "./types";

export function seedFieldLabel(targetType: TargetType, key: string): string {
  const scope = targetType === "character" ? "characterFields" : "worldFields";
  const path = `create.seed.${scope}.${key}` as MessageKey;
  const label = t(path);
  return label === path ? key : label;
}

export function formatSlotDisplay(targetType: TargetType, key: string, value: string): string {
  if (targetType === "world" && key === "root_level" && value) {
    const path = `library.world.levels.${value}` as MessageKey;
    const translated = t(path);
    return translated === path ? value : `${translated} (${value})`;
  }
  return value;
}

interface SlotReelCardProps {
  targetType: TargetType;
  fieldKey: string;
  options: readonly string[];
  value: string;
  locked: boolean;
  disabled: boolean;
  onToggleLock: () => void;
  onStep: (delta: -1 | 1) => void;
}

/** Single reel inside the Slot Machine deck with prev/next arrows and lock button. */
export function SlotReelCard({
  targetType,
  fieldKey,
  options,
  value,
  locked,
  disabled,
  onToggleLock,
  onStep,
}: SlotReelCardProps) {
  const label = seedFieldLabel(targetType, fieldKey);
  const idx = options.indexOf(value);
  const displayIdx = idx >= 0 ? idx + 1 : 1;

  return (
    <div
      data-testid={`slot-reel-${fieldKey}`}
      data-locked={locked}
      className={cn(
        "flex min-w-0 flex-col gap-2 rounded-md border p-3",
        locked ? "border-2 border-accent bg-accent/10" : "border-border bg-surface-2",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-semibold uppercase tracking-wide text-muted">
          {label}
        </span>
        <div className="flex items-center gap-1.5">
          {locked ? (
            <span className="rounded-sm border border-accent px-1.5 py-0.5 text-[11px] font-medium text-fg">
              {t("create.seed.lockedBadge")}
            </span>
          ) : null}
          <Button
            type="button"
            variant={locked ? "default" : "ghost"}
            size="icon"
            className="size-9"
            disabled={disabled}
            aria-pressed={locked}
            aria-label={
              locked
                ? t("create.seed.unlockField", { label })
                : t("create.seed.lockField", { label })
            }
            onClick={onToggleLock}
          >
            {locked ? (
              <Lock className="size-3.5" aria-hidden="true" />
            ) : (
              <Unlock className="size-3.5" aria-hidden="true" />
            )}
          </Button>
        </div>
      </div>

      <div
        data-testid={`slot-value-${fieldKey}`}
        className="flex min-h-12 items-center rounded-sm border border-border bg-bg px-3 py-2 text-sm text-fg"
      >
        <span className="line-clamp-2 break-words">
          {formatSlotDisplay(targetType, fieldKey, value)}
        </span>
      </div>

      <div className="flex items-center justify-between gap-2">
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="size-9"
          disabled={disabled || options.length <= 1}
          aria-label={t("create.seed.prevOption", { label })}
          onClick={() => onStep(-1)}
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
        </Button>
        <span className="font-mono text-xs text-muted tabular-nums">
          {t("create.seed.indexCount", {
            index: displayIdx,
            total: Math.max(options.length, 1),
          })}
        </span>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="size-9"
          disabled={disabled || options.length <= 1}
          aria-label={t("create.seed.nextOption", { label })}
          onClick={() => onStep(1)}
        >
          <ChevronRight className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

interface CarouselCardProps {
  targetType: TargetType;
  fieldKey: string;
  options: readonly string[];
  value: string;
  locked: boolean;
  isCustom: boolean;
  disabled: boolean;
  onToggleLock: () => void;
  onToggleCustom: () => void;
  onChangeValue: (next: string) => void;
  onStep: (delta: -1 | 1) => void;
}

/** Carousel card supporting prev/next cycling, custom text input, and lock toggle. */
export function SeedCarouselCard({
  targetType,
  fieldKey,
  options,
  value,
  locked,
  isCustom,
  disabled,
  onToggleLock,
  onToggleCustom,
  onChangeValue,
  onStep,
}: CarouselCardProps) {
  const label = seedFieldLabel(targetType, fieldKey);
  const idx = options.indexOf(value);
  const displayIdx = idx >= 0 ? idx + 1 : 1;

  return (
    <div
      data-testid={`carousel-${fieldKey}`}
      data-locked={locked}
      className={cn(
        "flex min-w-0 flex-col gap-2.5 rounded-md border p-3.5",
        locked ? "border-2 border-accent bg-accent/10" : "border-border bg-surface-2",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-sm font-semibold">{label}</span>
          <span className="rounded-sm border border-border bg-bg px-1.5 py-0.5 font-mono text-[11px] text-muted tabular-nums">
            {isCustom
              ? t("create.seed.customTag")
              : t("create.seed.indexCount", {
                  index: displayIdx,
                  total: Math.max(options.length, 1),
                })}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            variant={isCustom ? "default" : "outline"}
            size="sm"
            className="h-9 px-2.5 text-xs"
            disabled={disabled}
            aria-pressed={isCustom}
            onClick={onToggleCustom}
          >
            <PencilLine className="size-3.5" aria-hidden="true" />
            {isCustom ? t("create.seed.poolToggle") : t("create.seed.customToggle")}
          </Button>
          <Button
            type="button"
            variant={locked ? "default" : "ghost"}
            size="icon"
            className="size-9"
            disabled={disabled}
            aria-pressed={locked}
            aria-label={
              locked
                ? t("create.seed.unlockField", { label })
                : t("create.seed.lockField", { label })
            }
            onClick={onToggleLock}
          >
            {locked ? (
              <Lock className="size-3.5" aria-hidden="true" />
            ) : (
              <Unlock className="size-3.5" aria-hidden="true" />
            )}
          </Button>
        </div>
      </div>

      {isCustom ? (
        <textarea
          rows={2}
          disabled={disabled}
          aria-label={t("create.seed.customInputAria", { label })}
          placeholder={t("create.seed.customInputPlaceholder")}
          value={value}
          onChange={(e) => onChangeValue(e.target.value)}
          className="flex min-h-16 w-full resize-y rounded-sm border border-border bg-bg px-3 py-2 font-content text-sm text-fg placeholder:text-muted"
        />
      ) : (
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="size-10 shrink-0"
            disabled={disabled || options.length <= 1}
            aria-label={t("create.seed.prevOption", { label })}
            onClick={() => onStep(-1)}
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </Button>
          <p
            data-testid={`carousel-value-${fieldKey}`}
            className="min-w-0 flex-1 rounded-sm border border-border bg-bg px-3 py-2 font-content text-sm leading-relaxed text-fg"
          >
            {value}
          </p>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="size-10 shrink-0"
            disabled={disabled || options.length <= 1}
            aria-label={t("create.seed.nextOption", { label })}
            onClick={() => onStep(1)}
          >
            <ChevronRight className="size-4" aria-hidden="true" />
          </Button>
        </div>
      )}
    </div>
  );
}
