import { NavLink, useLocation } from "react-router-dom";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { NAV_ITEMS, isNavActive } from "./navItems";

export function BottomNav() {
  const { pathname } = useLocation();

  return (
    <nav
      aria-label={t("nav.mobile")}
      className="shrink-0 border-t border-border-subtle bg-surface pb-safe"
    >
      <ul className="flex items-stretch justify-around px-1 py-1">
        {NAV_ITEMS.map((item) => {
          const active = isNavActive(item, pathname);
          const Icon = item.icon;
          return (
            <li key={item.id} className="min-w-0 flex-1">
              <NavLink
                to={item.to}
                aria-current={active ? "page" : undefined}
                data-eink-active={active || undefined}
                className={cn(
                  "flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-md px-1 text-xs transition-colors duration-fast ease-ui",
                  active
                    ? "bg-accent/15 font-semibold text-accent-text"
                    : "text-muted hover:bg-hover/10 hover:text-fg",
                )}
              >
                <Icon className="size-5 shrink-0" aria-hidden="true" />
                <span className="max-w-full truncate">{t(item.labelKey)}</span>
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
