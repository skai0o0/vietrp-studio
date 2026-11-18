import { useEffect, type ReactNode } from "react";
import { create } from "zustand";

/** UI state for the layout slots that pages (and later work packages) can fill. */
interface PageChromeState {
  left: ReactNode;
  right: ReactNode;
  railFooter: ReactNode;
  setSidebars: (slots: { left?: ReactNode; right?: ReactNode }) => void;
  setRailFooter: (node: ReactNode) => void;
}

export const usePageChromeStore = create<PageChromeState>((set) => ({
  left: null,
  right: null,
  railFooter: null,
  setSidebars: ({ left = null, right = null }) => set({ left, right }),
  setRailFooter: (node) => set({ railFooter: node }),
}));

export interface PageChromeSlots {
  left?: ReactNode;
  right?: ReactNode;
}

/**
 * Declares the sidebars for the current page. They are cleared on unmount.
 * Pass memoized nodes (useMemo) to avoid re-registering on every render.
 */
export function usePageChrome({ left, right }: PageChromeSlots): void {
  const setSidebars = usePageChromeStore((state) => state.setSidebars);
  useEffect(() => {
    setSidebars({ left, right });
    return () => setSidebars({});
  }, [left, right, setSidebars]);
}

/** Fills the IconRail footer slot (the vault lock button goes here in a later work package). */
export function useRailFooter(node: ReactNode): void {
  const setRailFooter = usePageChromeStore((state) => state.setRailFooter);
  useEffect(() => {
    setRailFooter(node);
    return () => setRailFooter(null);
  }, [node, setRailFooter]);
}
