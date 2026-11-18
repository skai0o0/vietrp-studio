import type { Transition, Variants } from "framer-motion";
import { useReducedMotion } from "./useReducedMotion";

/** Shared framer-motion variants. All motion in the app goes through here. */
const FADE_DURATION_S = 0.18;
const SPRING: Transition = { type: "spring", stiffness: 300, damping: 25 };
const NO_MOTION: Transition = { duration: 0 };

export interface MotionKit {
  reduced: boolean;
  transition: Transition;
  spring: Transition;
  fadeIn: Variants;
  hoverTap: { whileHover?: { scale: number }; whileTap?: { scale: number } };
}

export function useMotionKit(): MotionKit {
  const reduced = useReducedMotion();
  return {
    reduced,
    transition: reduced ? NO_MOTION : { duration: FADE_DURATION_S },
    spring: reduced ? NO_MOTION : SPRING,
    fadeIn: reduced
      ? { hidden: { opacity: 1 }, visible: { opacity: 1 } }
      : { hidden: { opacity: 0, y: 6 }, visible: { opacity: 1, y: 0 } },
    hoverTap: reduced ? {} : { whileHover: { scale: 1.08 }, whileTap: { scale: 0.95 } },
  };
}
