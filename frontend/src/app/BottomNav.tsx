import { NavLink, useLocation } from "react-router-dom";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { NAV_ITEMS, isNavActive } from "./navItems";

export function BottomNav() {
  const { pathname } = useLocation();

  return (
    <nav
      aria-label={t("nav.mobile")}
      className="shrink-0 border-t border-border bg-surface pb-safe"
    >
      <ul className="flex items-stretch justify-around">
        {NAV_ITEMS.map((item) => {
          const active = isNavActive(item, pathname);
          const Icon = item.icon;
          return (
            <li key={item.id} className="flex-1">
              <NavLink
                to={item.to}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-h-14 flex-col items-center justify-center gap-1 text-[11px] transition-colors",
                  active ? "text-accent" : "text-muted hover:text-fg",
                )}
              >
                <Icon className="size-5" aria-hidden="true" />
                <span className={cn(active && "underline underline-offset-4")}>
                  {t(item.labelKey)}
                </span>
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
