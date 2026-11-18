import { Home, Library, PlusCircle, Settings, type LucideIcon } from "lucide-react";
import type { MessageKey } from "@/i18n";

export interface NavItem {
  id: string;
  to: string;
  labelKey: MessageKey;
  icon: LucideIcon;
  /** Match nested routes (e.g. /library/*) instead of the exact path. */
  matchPrefix: boolean;
}

// BottomNav allows at most 5 items; the chat room has no index route, so it is reached from the Gallery.
export const NAV_ITEMS: readonly NavItem[] = [
  { id: "gallery", to: "/", labelKey: "nav.gallery", icon: Home, matchPrefix: false },
  {
    id: "library",
    to: "/library/characters",
    labelKey: "nav.library",
    icon: Library,
    matchPrefix: true,
  },
  { id: "create", to: "/create", labelKey: "nav.create", icon: PlusCircle, matchPrefix: false },
  { id: "settings", to: "/settings", labelKey: "nav.settings", icon: Settings, matchPrefix: false },
];

export function isNavActive(item: NavItem, pathname: string): boolean {
  if (item.id === "library") return pathname.startsWith("/library");
  if (item.matchPrefix) return pathname.startsWith(item.to);
  return pathname === item.to;
}
