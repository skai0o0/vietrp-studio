import { motion } from "framer-motion";
import { NavLink, useLocation } from "react-router-dom";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { useMotionKit } from "@/lib/motion";
import { NAV_ITEMS, isNavActive, type NavItem } from "./navItems";
import { usePageChromeStore } from "./pageChrome";
import { ThemeToggle } from "./ThemeToggle";

function RailItem({ item }: { item: NavItem }) {
  const { pathname } = useLocation();
  const { hoverTap } = useMotionKit();
  const active = isNavActive(item, pathname);
  const label = t(item.labelKey);
  const Icon = item.icon;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <NavLink
          to={item.to}
          aria-label={label}
          aria-current={active ? "page" : undefined}
          className="relative block rounded-md"
        >
          <motion.span
            {...hoverTap}
            className={cn(
              "flex size-10 items-center justify-center rounded-md transition-colors",
              active ? "bg-accent/15 text-accent" : "text-muted hover:bg-surface-2 hover:text-fg",
            )}
          >
            <Icon className="size-5" aria-hidden="true" />
          </motion.span>
          {active ? (
            <span
              aria-hidden="true"
              className="absolute -left-3 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-accent shadow-glow"
            />
          ) : null}
        </NavLink>
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

export function IconRail() {
  const railFooter = usePageChromeStore((state) => state.railFooter);

  return (
    <nav
      aria-label={t("nav.primary")}
      className="flex w-16 shrink-0 flex-col items-center gap-2 border-r border-border bg-surface py-4 pt-safe"
    >
      <span
        aria-hidden="true"
        className="mb-2 flex size-10 items-center justify-center text-lg font-semibold text-accent"
      >
        V
      </span>
      <ul className="flex flex-1 flex-col items-center gap-2">
        {NAV_ITEMS.map((item) => (
          <li key={item.id}>
            <RailItem item={item} />
          </li>
        ))}
      </ul>
      <div className="flex flex-col items-center gap-2 pb-safe">
        {railFooter}
        <ThemeToggle />
      </div>
    </nav>
  );
}
