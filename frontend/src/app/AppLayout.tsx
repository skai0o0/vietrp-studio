import { PanelLeft, PanelRight } from "lucide-react";
import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { t } from "@/i18n";
import { useBreakpoint } from "@/lib/useBreakpoint";
import { BottomNav } from "./BottomNav";
import { IconRail } from "./IconRail";
import { usePageChromeStore } from "./pageChrome";

const MAIN_ID = "main-content";

export function AppLayout() {
  const breakpoint = useBreakpoint();
  const { pathname } = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const left = usePageChromeStore((state) => state.left);
  const right = usePageChromeStore((state) => state.right);
  const leftTitle = usePageChromeStore((state) => state.leftTitle);
  const rightTitle = usePageChromeStore((state) => state.rightTitle);
  const hideMobileNav = usePageChromeStore((state) => state.hideMobileNav);
  const hideToggleBar = usePageChromeStore((state) => state.hideToggleBar);
  const leftOpen = usePageChromeStore((state) => state.leftOpen);
  const rightOpen = usePageChromeStore((state) => state.rightOpen);
  const setLeftOpen = usePageChromeStore((state) => state.setLeftOpen);
  const setRightOpen = usePageChromeStore((state) => state.setRightOpen);

  useEffect(() => {
    setLeftOpen(false);
    setRightOpen(false);
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [pathname, setLeftOpen, setRightOpen]);

  const isDesktop = breakpoint === "desktop";
  const isMobile = breakpoint === "mobile";
  const showToggleBar = !isDesktop && !hideToggleBar && Boolean(left || right);
  const resolvedLeftTitle = leftTitle || t("layout.leftSidebarTitle");
  const resolvedRightTitle = rightTitle || t("layout.rightSidebarTitle");

  return (
    <div className="flex h-dvh-safe flex-col overflow-hidden bg-bg text-fg md:flex-row">
      <a
        href={`#${MAIN_ID}`}
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-skip focus:rounded-md focus:bg-accent focus:px-4 focus:py-2 focus:text-accent-fg"
      >
        {t("app.skipToContent")}
      </a>

      {isMobile ? null : <IconRail />}

      {isDesktop && left ? (
        <aside className="w-72 shrink-0 overflow-y-auto border-r border-border-subtle bg-surface">
          {left}
        </aside>
      ) : null}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col pt-safe md:pt-0">
        {showToggleBar ? (
          <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-border-subtle bg-surface px-2">
            {left ? (
              <Button
                variant="ghost"
                size="sm"
                aria-label={t("layout.openLeftSidebar")}
                onClick={() => setLeftOpen(true)}
                className="gap-1.5 text-fg"
              >
                <PanelLeft className="size-4" aria-hidden="true" />
                <span className="truncate text-xs font-medium">{resolvedLeftTitle}</span>
              </Button>
            ) : (
              <span />
            )}
            {right ? (
              <Button
                variant="ghost"
                size="sm"
                aria-label={t("layout.openRightSidebar")}
                onClick={() => setRightOpen(true)}
                className="gap-1.5 text-fg"
              >
                <span className="truncate text-xs font-medium">{resolvedRightTitle}</span>
                <PanelRight className="size-4" aria-hidden="true" />
              </Button>
            ) : null}
          </div>
        ) : null}
        <main
          ref={mainRef}
          id={MAIN_ID}
          tabIndex={-1}
          className="min-h-0 flex-1 scroll-pt-20 overflow-y-auto focus:outline-none"
        >
          <Outlet />
        </main>
        {isMobile && !hideMobileNav ? <BottomNav /> : null}
      </div>

      {isDesktop && right ? (
        <aside className="w-[21rem] shrink-0 overflow-y-auto border-l border-border-subtle bg-surface">
          {right}
        </aside>
      ) : null}

      {!isDesktop && left ? (
        <Sheet open={leftOpen} onOpenChange={setLeftOpen}>
          <SheetContent side="left" hideDefaultClose aria-describedby={undefined}>
            <SheetTitle className="sr-only">{resolvedLeftTitle}</SheetTitle>
            <SheetDescription className="sr-only">{resolvedLeftTitle}</SheetDescription>
            <SheetHeader title={resolvedLeftTitle} closeLabel={t("layout.closeSidebar")} />
            <div className="min-h-0 flex-1 overflow-y-auto">{left}</div>
          </SheetContent>
        </Sheet>
      ) : null}
      {!isDesktop && right ? (
        <Sheet open={rightOpen} onOpenChange={setRightOpen}>
          <SheetContent
            side={isMobile ? "bottom" : "right"}
            hideDefaultClose
            aria-describedby={undefined}
          >
            <SheetTitle className="sr-only">{resolvedRightTitle}</SheetTitle>
            <SheetDescription className="sr-only">{resolvedRightTitle}</SheetDescription>
            <SheetHeader
              title={resolvedRightTitle}
              closeLabel={t("layout.closeSidebar")}
              showHandle={isMobile}
            />
            <div className="min-h-0 flex-1 overflow-y-auto">{right}</div>
          </SheetContent>
        </Sheet>
      ) : null}
    </div>
  );
}
