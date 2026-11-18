import { useEffect, useState } from "react";

export type Breakpoint = "mobile" | "tablet" | "desktop";

// Layout breakpoints from KIEN-TRUC §9.1 / WP-B: tablet from 768px, desktop from 1280px.
const TABLET_QUERY = "(min-width: 768px)";
const DESKTOP_QUERY = "(min-width: 1280px)";

function current(): Breakpoint {
  if (typeof window.matchMedia !== "function") return "desktop";
  if (window.matchMedia(DESKTOP_QUERY).matches) return "desktop";
  if (window.matchMedia(TABLET_QUERY).matches) return "tablet";
  return "mobile";
}

export function useBreakpoint(): Breakpoint {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(current);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const queries = [window.matchMedia(TABLET_QUERY), window.matchMedia(DESKTOP_QUERY)];
    const update = (): void => setBreakpoint(current());
    queries.forEach((query) => query.addEventListener("change", update));
    update();
    return () => queries.forEach((query) => query.removeEventListener("change", update));
  }, []);

  return breakpoint;
}
