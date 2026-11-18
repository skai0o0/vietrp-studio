import type { CreatorPoolsOut, CreatorSeedState, CreatorWorkspaceState, TargetType } from "./types";

export function emptySeedState(): CreatorSeedState {
  return {
    name: "",
    age: "",
    notes: "",
    values: {},
    customMode: {},
    locked: {},
  };
}

export function emptyWorkspaceState(): CreatorWorkspaceState {
  return {
    session: null,
    messages: [],
    streamingReply: "",
    rawText: "",
    generatedData: null,
    warnings: [],
    judgeScore: null,
    notices: [],
    stage: "idle",
    errorCode: null,
  };
}

export function getPoolSection(
  pools: CreatorPoolsOut | undefined,
  targetType: TargetType,
): { carousels: Record<string, string[]>; slots: Record<string, string[]> } {
  const target = pools?.[targetType];
  return {
    carousels: target?.carousels ?? {},
    slots: target?.slots ?? {},
  };
}

/** Populates uninitialized keys with the first item of each pool without clobbering user edits. */
export function initializeSeedFromPools(
  current: CreatorSeedState,
  pools: CreatorPoolsOut | undefined,
  targetType: TargetType,
): CreatorSeedState {
  const { carousels, slots } = getPoolSection(pools, targetType);
  let changed = false;
  const nextValues = { ...current.values };
  for (const group of [carousels, slots]) {
    for (const [key, options] of Object.entries(group)) {
      if (nextValues[key] === undefined && options.length > 0) {
        nextValues[key] = options[0] ?? "";
        changed = true;
      }
    }
  }
  return changed ? { ...current, values: nextValues } : current;
}

/** Cycles through pool options with wrap-around. */
export function cycleOption(
  options: readonly string[],
  currentValue: string | undefined,
  delta: -1 | 1,
): { value: string; index: number } {
  if (options.length === 0) return { value: "", index: -1 };
  const currentIdx = currentValue ? options.indexOf(currentValue) : -1;
  const baseIdx = currentIdx >= 0 ? currentIdx : 0;
  const nextIdx = (baseIdx + delta + options.length) % options.length;
  return { value: options[nextIdx] ?? "", index: nextIdx };
}

/**
 * Picks a random option from `options`, preferring an index different from `currentValue`
 * when `options.length > 1` so pulling the lever visibly changes unlocked reels.
 */
export function pickRandomOption(
  options: readonly string[],
  currentValue: string | undefined,
  rng: () => number = Math.random,
): string {
  if (options.length === 0) return "";
  if (options.length === 1) return options[0] ?? "";
  const currentIdx = currentValue ? options.indexOf(currentValue) : -1;
  const candidates: number[] = [];
  for (let i = 0; i < options.length; i += 1) {
    if (i !== currentIdx) candidates.push(i);
  }
  const pool = candidates.length > 0 ? candidates : options.map((_, i) => i);
  const chosen = pool[Math.floor(rng() * pool.length)] ?? 0;
  return options[chosen] ?? "";
}

/** Randomizes all unlocked carousels and slots while preserving locked fields verbatim. */
export function randomizeUnlockedSeed(
  current: CreatorSeedState,
  pools: CreatorPoolsOut | undefined,
  targetType: TargetType,
  rng: () => number = Math.random,
): CreatorSeedState {
  const { carousels, slots } = getPoolSection(pools, targetType);
  const nextValues = { ...current.values };
  const nextCustomMode = { ...current.customMode };

  for (const group of [carousels, slots]) {
    for (const [key, options] of Object.entries(group)) {
      if (current.locked[key] || options.length === 0) continue;
      nextValues[key] = pickRandomOption(options, nextValues[key], rng);
      nextCustomMode[key] = false;
    }
  }

  return {
    ...current,
    values: nextValues,
    customMode: nextCustomMode,
  };
}

/** Serializes local UI seed state into a clean API `seed` payload (omitting blanks). */
export function buildSeedPayload(
  seedState: CreatorSeedState,
  targetType: TargetType,
): Record<string, unknown> {
  const out: Record<string, unknown> = { target_type: targetType };
  for (const [key, value] of Object.entries(seedState.values)) {
    const trimmed = value.trim();
    if (trimmed) out[key] = trimmed;
  }
  const name = seedState.name.trim();
  if (name) out.name = name;
  if (targetType === "character") {
    const ageText = seedState.age.trim();
    if (/^\d+$/.test(ageText)) {
      const parsed = Number.parseInt(ageText, 10);
      if (parsed >= 0 && parsed <= 10000) out.age = parsed;
    }
  }
  const notes = seedState.notes.trim();
  if (notes) out.notes = notes;
  return out;
}
