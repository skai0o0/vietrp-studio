import { Dices, RefreshCw } from "lucide-react";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import { SeedCarouselCard, SlotReelCard } from "./SlotCards";
import { cycleOption, getPoolSection, randomizeUnlockedSeed } from "./slotHelpers";
import type { CreatorPoolsOut, CreatorSeedState, TargetType } from "./types";

export interface SlotMachineSectionProps {
  targetType: TargetType;
  pools: CreatorPoolsOut | undefined;
  poolsPending: boolean;
  poolsError: boolean;
  onRetryPools: () => void;
  seedState: CreatorSeedState;
  onChangeSeed: (next: CreatorSeedState) => void;
  disabled?: boolean;
}

/** Basic seed inputs, Carousels (swipe + custom + lock), and Slot Machine reels + Pull lever. */
export function SlotMachineSection({
  targetType,
  pools,
  poolsPending,
  poolsError,
  onRetryPools,
  seedState,
  onChangeSeed,
  disabled = false,
}: SlotMachineSectionProps) {
  const nameId = useId();
  const ageId = useId();
  const notesId = useId();

  const { carousels, slots } = getPoolSection(pools, targetType);
  const carouselEntries = Object.entries(carousels);
  const slotEntries = Object.entries(slots);

  function toggleLock(key: string): void {
    onChangeSeed({
      ...seedState,
      locked: { ...seedState.locked, [key]: !seedState.locked[key] },
    });
  }

  function setFieldValue(key: string, value: string): void {
    onChangeSeed({
      ...seedState,
      values: { ...seedState.values, [key]: value },
    });
  }

  function toggleCustomMode(key: string): void {
    onChangeSeed({
      ...seedState,
      customMode: { ...seedState.customMode, [key]: !seedState.customMode[key] },
    });
  }

  function stepOption(key: string, options: readonly string[], delta: -1 | 1): void {
    const { value } = cycleOption(options, seedState.values[key], delta);
    onChangeSeed({
      ...seedState,
      values: { ...seedState.values, [key]: value },
      customMode: { ...seedState.customMode, [key]: false },
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 md:p-5">
        <h2 className="text-base font-semibold">{t("create.seed.basicTitle")}</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor={nameId}>{t("create.seed.name")}</Label>
            <Input
              id={nameId}
              disabled={disabled}
              value={seedState.name}
              placeholder={
                targetType === "character"
                  ? t("create.seed.nameCharacterPlaceholder")
                  : t("create.seed.nameWorldPlaceholder")
              }
              onChange={(e) => onChangeSeed({ ...seedState, name: e.target.value })}
            />
          </div>
          {targetType === "character" ? (
            <div className="flex min-w-0 flex-col gap-1.5">
              <Label htmlFor={ageId}>{t("create.seed.age")}</Label>
              <Input
                id={ageId}
                type="number"
                inputMode="numeric"
                min={0}
                max={10000}
                disabled={disabled}
                value={seedState.age}
                placeholder={t("create.seed.agePlaceholder")}
                onChange={(e) => onChangeSeed({ ...seedState, age: e.target.value })}
              />
              <p className="text-xs text-muted">{t("create.seed.ageHint")}</p>
            </div>
          ) : null}
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor={notesId}>{t("create.seed.notes")}</Label>
          <textarea
            id={notesId}
            rows={2}
            disabled={disabled}
            value={seedState.notes}
            placeholder={t("create.seed.notesPlaceholder")}
            onChange={(e) => onChangeSeed({ ...seedState, notes: e.target.value })}
            className="flex min-h-16 w-full resize-y rounded-md border border-border bg-surface-2 px-3 py-2 font-content text-sm text-fg placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>
      </section>

      {poolsPending ? (
        <p
          role="status"
          className="rounded-lg border border-border bg-surface p-6 text-sm text-muted"
        >
          {t("create.pools.loading")}
        </p>
      ) : poolsError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border-2 border-danger bg-surface p-4 text-sm"
        >
          <span>{t("create.pools.loadFailed")}</span>
          <Button type="button" variant="outline" size="sm" onClick={onRetryPools}>
            <RefreshCw className="size-4" aria-hidden="true" />
            {t("create.pools.retry")}
          </Button>
        </div>
      ) : (
        <>
          <section className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 md:p-5">
            <header className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 flex-col gap-1">
                <h2 className="text-base font-semibold">{t("create.seed.slotsTitle")}</h2>
                <p className="text-xs text-muted">{t("create.seed.slotsHint")}</p>
              </div>
              <Button
                type="button"
                disabled={disabled || (slotEntries.length === 0 && carouselEntries.length === 0)}
                onClick={() => onChangeSeed(randomizeUnlockedSeed(seedState, pools, targetType))}
                className="min-h-11 shrink-0 shadow-glow"
              >
                <Dices className="size-4" aria-hidden="true" />
                {t("create.seed.pullLever")}
              </Button>
            </header>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {slotEntries.map(([key, options]) => (
                <SlotReelCard
                  key={key}
                  targetType={targetType}
                  fieldKey={key}
                  options={options}
                  value={seedState.values[key] ?? options[0] ?? ""}
                  locked={Boolean(seedState.locked[key])}
                  disabled={disabled}
                  onToggleLock={() => toggleLock(key)}
                  onStep={(delta) => stepOption(key, options, delta)}
                />
              ))}
            </div>
          </section>

          <section className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 md:p-5">
            <header className="flex flex-col gap-1">
              <h2 className="text-base font-semibold">{t("create.seed.carouselsTitle")}</h2>
              <p className="text-xs text-muted">{t("create.seed.carouselsHint")}</p>
            </header>

            <div className="flex flex-col gap-3">
              {carouselEntries.map(([key, options]) => (
                <SeedCarouselCard
                  key={key}
                  targetType={targetType}
                  fieldKey={key}
                  options={options}
                  value={seedState.values[key] ?? options[0] ?? ""}
                  locked={Boolean(seedState.locked[key])}
                  isCustom={Boolean(seedState.customMode[key])}
                  disabled={disabled}
                  onToggleLock={() => toggleLock(key)}
                  onToggleCustom={() => toggleCustomMode(key)}
                  onChangeValue={(value) => setFieldValue(key, value)}
                  onStep={(delta) => stepOption(key, options, delta)}
                />
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
