import { useEffect, type ReactNode } from "react";
import { create } from "zustand";

/** UI state for the layout slots and responsive drawer controls that pages can fill. */
interface PageChromeState {
  left: ReactNode;
  right: ReactNode;
  leftTitle: string | null;
  rightTitle: string | null;
  hideMobileNav: boolean;
  hideToggleBar: boolean;
  leftOpen: boolean;
  rightOpen: boolean;
  railFooter: ReactNode;
  setSidebars: (slots: PageChromeSlots) => void;
  setLeftOpen: (open: boolean) => void;
  setRightOpen: (open: boolean) => void;
  setRailFooter: (node: ReactNode) => void;
}

export interface PageChromeSlots {
  left?: ReactNode;
  right?: ReactNode;
  leftTitle?: string;
  rightTitle?: string;
  hideMobileNav?: boolean;
  hideToggleBar?: boolean;
}

export const usePageChromeStore = create<PageChromeState>((set) => ({
  left: null,
  right: null,
  leftTitle: null,
  rightTitle: null,
  hideMobileNav: false,
  hideToggleBar: false,
  leftOpen: false,
  rightOpen: false,
  railFooter: null,
  setSidebars: ({
    left = null,
    right = null,
    leftTitle,
    rightTitle,
    hideMobileNav = false,
    hideToggleBar = false,
  }) =>
    set({
      left,
      right,
      leftTitle: leftTitle ?? null,
      rightTitle: rightTitle ?? null,
      hideMobileNav,
      hideToggleBar,
    }),
  setLeftOpen: (leftOpen) => set({ leftOpen }),
  setRightOpen: (rightOpen) => set({ rightOpen }),
  setRailFooter: (node) => set({ railFooter: node }),
}));

/**
 * Declares the sidebars and shell hints for the current page. They are cleared on unmount.
 * Pass memoized nodes (useMemo) to avoid re-registering on every render.
 */
export function usePageChrome({
  left,
  right,
  leftTitle,
  rightTitle,
  hideMobileNav,
  hideToggleBar,
}: PageChromeSlots): void {
  const setSidebars = usePageChromeStore((state) => state.setSidebars);
  useEffect(() => {
    setSidebars({ left, right, leftTitle, rightTitle, hideMobileNav, hideToggleBar });
    return () => setSidebars({});
  }, [left, right, leftTitle, rightTitle, hideMobileNav, hideToggleBar, setSidebars]);
}

/** Fills the IconRail footer slot (the vault lock button goes here). */
export function useRailFooter(node: ReactNode): void {
  const setRailFooter = usePageChromeStore((state) => state.setRailFooter);
  useEffect(() => {
    setRailFooter(node);
    return () => setRailFooter(null);
  }, [node, setRailFooter]);
}
