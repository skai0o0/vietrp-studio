import { Home, Library, MessageSquare, PlusCircle, Settings, type LucideIcon } from "lucide-react";
import type { MessageKey } from "@/i18n";

export interface NavItem {
  id: string;
  to: string;
  labelKey: MessageKey;
  icon: LucideIcon;
  /** Match nested routes (e.g. /library/*) instead of the exact path. */
  matchPrefix: boolean;
}

// BottomNav allows at most 5 items.
export const NAV_ITEMS: readonly NavItem[] = [
  { id: "gallery", to: "/", labelKey: "nav.gallery", icon: Home, matchPrefix: false },
  { id: "chats", to: "/chats", labelKey: "nav.chats", icon: MessageSquare, matchPrefix: true },
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
  if (item.id === "chats") {
    return (
      pathname.startsWith("/chats") ||
      pathname.startsWith("/chat/") ||
      pathname === "/create/chat"
    );
  }
  if (item.id === "library") {
    return (
      pathname.startsWith("/library") ||
      pathname.startsWith("/characters/") ||
      pathname.startsWith("/worlds/")
    );
  }
  if (item.id === "create") return pathname === "/create";
  if (item.matchPrefix) return pathname.startsWith(item.to);
  return pathname === item.to;
}
