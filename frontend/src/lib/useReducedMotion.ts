import { useEffect, useState } from "react";
import { useThemeStore } from "@/app/theme";

const QUERY = "(prefers-reduced-motion: reduce)";

function prefersReduced(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(QUERY).matches;
}

/** True for the E-ink theme and for `prefers-reduced-motion`. */
export function useReducedMotion(): boolean {
  const theme = useThemeStore((state) => state.theme);
  const [systemReduced, setSystemReduced] = useState(prefersReduced);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(QUERY);
    const onChange = (): void => setSystemReduced(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  return theme === "e-ink" || systemReduced;
}
