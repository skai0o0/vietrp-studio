export type TokenBarLevel = "ok" | "notice" | "warn" | "full";

/** Color steps for the token bar (AGENTS §5.3): 60 / 80 / 100 percent of the budget. */
export const TOKEN_BAR_STEPS = { notice: 0.6, warn: 0.8, full: 1 } as const;

export interface TokenBarState {
  /** Share of the budget used, clamped to 0..1 for drawing. */
  ratio: number;
  /** Rounded percent of the budget (not clamped, so overflow stays visible). */
  percent: number;
  level: TokenBarLevel;
}

export function tokenBarState(used: number, budget: number): TokenBarState {
  if (!Number.isFinite(used) || !Number.isFinite(budget) || budget <= 0 || used <= 0) {
    return { ratio: 0, percent: 0, level: "ok" };
  }
  const raw = used / budget;
  let level: TokenBarLevel = "ok";
  if (raw >= TOKEN_BAR_STEPS.full) level = "full";
  else if (raw >= TOKEN_BAR_STEPS.warn) level = "warn";
  else if (raw >= TOKEN_BAR_STEPS.notice) level = "notice";
  return { ratio: Math.min(raw, 1), percent: Math.round(raw * 100), level };
}

/** Fill uses `data-level` so E-ink can tell steps apart without colour (see e-ink.css). */
/** Theme-token classes per level; no raw colors. */
export const TOKEN_BAR_CLASS: Record<TokenBarLevel, string> = {
  ok: "bg-accent-2",
  notice: "bg-accent",
  warn: "bg-danger/70",
  full: "bg-danger",
};
