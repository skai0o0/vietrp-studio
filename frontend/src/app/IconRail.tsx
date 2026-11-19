import { motion } from "framer-motion";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { useMotionKit } from "@/lib/motion";
import { NAV_ITEMS, isNavActive, type NavItem } from "./navItems";
import { usePageChromeStore } from "./pageChrome";
import { ThemeToggle } from "./ThemeToggle";

function RailItem({ item }: { item: NavItem }) {
  const { pathname } = useLocation();
  const { hoverTap, activeIndicator } = useMotionKit();
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
          data-eink-active={active || undefined}
          className="relative block rounded-md"
        >
          <motion.span
            {...hoverTap}
            className={cn(
              "flex flex-col items-center justify-center gap-0.5 rounded-md px-1.5 py-2 transition-colors duration-fast ease-ui xl:size-10 xl:p-0",
              active
                ? "bg-accent/15 text-accent-text"
                : "text-muted hover:bg-hover/10 hover:text-fg",
            )}
          >
            <Icon className="size-5" aria-hidden="true" />
            <span className="max-w-16 truncate text-xs leading-tight xl:hidden">{label}</span>
          </motion.span>
          {active ? (
            <motion.span
              layoutId="rail-active"
              transition={activeIndicator}
              aria-hidden="true"
              className="absolute -left-2.5 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-accent shadow-glow xl:-left-3"
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
      className="flex w-[72px] shrink-0 flex-col items-center gap-2 border-r border-border-subtle bg-surface py-4 pt-safe xl:w-16"
    >
      <Link
        to="/"
        aria-label={t("app.name")}
        className="mb-2 flex size-10 items-center justify-center rounded-md text-lg font-semibold text-accent-text transition-colors duration-fast hover:bg-hover/10"
      >
        V
      </Link>
      <ul className="flex flex-1 flex-col items-center gap-1.5">
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
