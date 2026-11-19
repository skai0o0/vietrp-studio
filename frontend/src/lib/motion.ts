import type { Transition, Variants } from "framer-motion";
import { useReducedMotion } from "./useReducedMotion";

/** Shared Framer Motion curves, durations, and variants (zero overshoot, E-ink safe). */
export const EASE_UI = [0.2, 0.8, 0.2, 1] as const;
export const EASE_ENTER = [0.22, 1, 0.36, 1] as const;
export const EASE_EXIT = [0.4, 0, 1, 1] as const;

export const DURATIONS = {
  press: 0.09,
  fast: 0.12,
  base: 0.15,
  panelIn: 0.2,
  panelOut: 0.12,
  sheetIn: 0.24,
  sheetOut: 0.16,
  slide: 0.24,
} as const;

/** Critically damped spring (zeta ~ 1.04): snaps cleanly without bounce or overshoot. */
export const SNAPPY_SPRING: Transition = {
  type: "spring",
  stiffness: 420,
  damping: 38,
  mass: 0.8,
};

const NO_MOTION: Transition = { duration: 0 };

export interface MotionKit {
  reduced: boolean;
  transition: Transition;
  spring: Transition;
  activeIndicator: Transition;
  fadeIn: Variants;
  panel: Variants;
  crossfade: Variants;
  hoverTap: { whileTap?: { scale: number; transition?: Transition } };
}

export function useMotionKit(): MotionKit {
  const reduced = useReducedMotion();
  return {
    reduced,
    transition: reduced ? NO_MOTION : { duration: DURATIONS.base, ease: EASE_UI },
    spring: reduced ? NO_MOTION : SNAPPY_SPRING,
    activeIndicator: reduced ? NO_MOTION : SNAPPY_SPRING,
    fadeIn: reduced
      ? { hidden: { opacity: 1 }, visible: { opacity: 1 } }
      : {
          hidden: { opacity: 0, y: 6 },
          visible: {
            opacity: 1,
            y: 0,
            transition: { duration: DURATIONS.panelIn, ease: EASE_ENTER },
          },
        },
    panel: reduced
      ? { initial: { opacity: 1 }, animate: { opacity: 1 }, exit: { opacity: 1 } }
      : {
          initial: { opacity: 0, y: 6, scale: 0.98 },
          animate: {
            opacity: 1,
            y: 0,
            scale: 1,
            transition: { duration: DURATIONS.panelIn, ease: EASE_ENTER },
          },
          exit: {
            opacity: 0,
            y: 4,
            scale: 0.98,
            transition: { duration: DURATIONS.panelOut, ease: EASE_EXIT },
          },
        },
    crossfade: reduced
      ? { initial: { opacity: 1 }, animate: { opacity: 1 }, exit: { opacity: 1 } }
      : {
          initial: { opacity: 0 },
          animate: { opacity: 1, transition: { duration: DURATIONS.base, ease: EASE_UI } },
          exit: { opacity: 0, transition: { duration: DURATIONS.panelOut, ease: EASE_EXIT } },
        },
    hoverTap: reduced
      ? {}
      : { whileTap: { scale: 0.96, transition: { duration: DURATIONS.press, ease: EASE_UI } } },
  };
}
