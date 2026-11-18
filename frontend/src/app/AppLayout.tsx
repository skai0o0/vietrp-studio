import { PanelLeft, PanelRight } from "lucide-react";
import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { t } from "@/i18n";
import { useBreakpoint } from "@/lib/useBreakpoint";
import { BottomNav } from "./BottomNav";
import { IconRail } from "./IconRail";
import { usePageChromeStore } from "./pageChrome";

const MAIN_ID = "main-content";

export function AppLayout() {
  const breakpoint = useBreakpoint();
  const left = usePageChromeStore((state) => state.left);
  const right = usePageChromeStore((state) => state.right);
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  const isDesktop = breakpoint === "desktop";
  const isMobile = breakpoint === "mobile";
  const showToggleBar = !isDesktop && (left || right);

  return (
    <div className="flex h-dvh-safe flex-col overflow-hidden bg-bg text-fg md:flex-row">
      <a
        href={`#${MAIN_ID}`}
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:rounded-md focus:bg-accent focus:px-4 focus:py-2 focus:text-accent-fg"
      >
        {t("app.skipToContent")}
      </a>

      {isMobile ? null : <IconRail />}

      {isDesktop && left ? (
        <aside className="w-72 shrink-0 overflow-y-auto border-r border-border bg-surface">
          {left}
        </aside>
      ) : null}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col pt-safe md:pt-0">
        {showToggleBar ? (
          <div className="flex shrink-0 items-center justify-between border-b border-border px-2">
            {left ? (
              <Button
                variant="ghost"
                size="icon"
                aria-label={t("layout.openLeftSidebar")}
                onClick={() => setLeftOpen(true)}
              >
                <PanelLeft aria-hidden="true" />
              </Button>
            ) : (
              <span />
            )}
            {right ? (
              <Button
                variant="ghost"
                size="icon"
                aria-label={t("layout.openRightSidebar")}
                onClick={() => setRightOpen(true)}
              >
                <PanelRight aria-hidden="true" />
              </Button>
            ) : null}
          </div>
        ) : null}
        <main
          id={MAIN_ID}
          tabIndex={-1}
          className="min-h-0 flex-1 overflow-y-auto focus:outline-none"
        >
          <Outlet />
        </main>
        {isMobile ? <BottomNav /> : null}
      </div>

      {isDesktop && right ? (
        <aside className="w-80 shrink-0 overflow-y-auto border-l border-border bg-surface">
          {right}
        </aside>
      ) : null}

      {!isDesktop && left ? (
        <Sheet open={leftOpen} onOpenChange={setLeftOpen}>
          <SheetContent side="left" aria-describedby={undefined}>
            <SheetTitle className="sr-only">{t("layout.leftSidebarTitle")}</SheetTitle>
            <SheetDescription className="sr-only">{t("layout.leftSidebarTitle")}</SheetDescription>
            <div className="min-h-0 flex-1 overflow-y-auto">{left}</div>
          </SheetContent>
        </Sheet>
      ) : null}
      {!isDesktop && right ? (
        <Sheet open={rightOpen} onOpenChange={setRightOpen}>
          <SheetContent side={isMobile ? "bottom" : "right"} aria-describedby={undefined}>
            <SheetTitle className="sr-only">{t("layout.rightSidebarTitle")}</SheetTitle>
            <SheetDescription className="sr-only">{t("layout.rightSidebarTitle")}</SheetDescription>
            <div className="min-h-0 flex-1 overflow-y-auto">{right}</div>
          </SheetContent>
        </Sheet>
      ) : null}
    </div>
  );
}
