import {
  Archive,
  ArrowLeft,
  Eye,
  Globe,
  Menu,
  MoreVertical,
  SlidersHorizontal,
  Undo2,
} from "lucide-react";
import { Link, useInRouterContext } from "react-router-dom";
import { usePageChromeStore } from "@/app/pageChrome";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { ChatOut, WorldState } from "@/types/chat";
import { SpeakerAvatar } from "./MessageList";

export interface ChatHeaderProps {
  chat: ChatOut;
  personaName?: string | null;
  isStreaming?: boolean;
  canUndo?: boolean;
  onOpenInspector?: () => void;
  onSummarize?: () => void;
  onUndo?: () => void;
}

/** Sticky compact workspace header: navigation, title, active Persona pill, world scene strip, and actions. */
export function ChatHeader({
  chat,
  personaName,
  isStreaming = false,
  canUndo = false,
  onOpenInspector,
  onSummarize,
  onUndo,
}: ChatHeaderProps) {
  const inRouter = useInRouterContext();
  const setLeftOpen = usePageChromeStore((s) => s.setLeftOpen);
  const setRightOpen = usePageChromeStore((s) => s.setRightOpen);

  const title = chat.title || chat.character_name || chat.world_name || "";
  const isWorld = chat.mode === "world";
  const worldState = (chat.state ?? {}) as Partial<WorldState>;
  const sceneSummary = isWorld
    ? [
        worldState.location_id || chat.world_name || null,
        worldState.time || null,
        typeof worldState.tension === "number"
          ? t("chat.header.tensionLabel", { value: worldState.tension })
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : "";

  const backButton = inRouter ? (
    <Link
      to="/chats"
      aria-label={t("chat.header.back")}
      title={t("chat.header.back")}
      className="inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted transition-colors duration-fast ease-ui hover:bg-hover hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent md:hidden"
    >
      <ArrowLeft className="size-4" aria-hidden="true" />
    </Link>
  ) : (
    <a
      href="/chats"
      aria-label={t("chat.header.back")}
      title={t("chat.header.back")}
      className="inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted transition-colors duration-fast ease-ui hover:bg-hover hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent md:hidden"
    >
      <ArrowLeft className="size-4" aria-hidden="true" />
    </a>
  );

  return (
    <header className="sticky top-0 z-sticky flex h-14 shrink-0 items-center gap-2 border-b border-border-subtle bg-surface/95 px-2.5 backdrop-blur-sm md:px-4">
      <div className="flex items-center gap-1 lg:hidden">
        {backButton}
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={t("chat.header.openRecent")}
          title={t("chat.header.openRecent")}
          onClick={() => setLeftOpen(true)}
        >
          <Menu className="size-4" aria-hidden="true" />
        </Button>
      </div>

      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        {isWorld && !chat.avatar_url ? (
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border bg-surface-2 text-accent-2">
            <Globe className="size-4" aria-hidden="true" />
          </div>
        ) : (
          <SpeakerAvatar url={chat.avatar_url} label={title} />
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="truncate text-sm font-semibold text-fg md:text-base">{title}</h1>
            <button
              type="button"
              onClick={() => setRightOpen(true)}
              className={cn(
                "hidden shrink-0 items-center rounded border px-1.5 py-0.5 text-2xs font-medium transition-colors duration-fast ease-ui focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent sm:inline-flex",
                personaName
                  ? "border-border-strong bg-surface-2 text-fg hover:bg-hover"
                  : "border-border bg-surface text-muted hover:text-fg",
              )}
            >
              {personaName
                ? t("chat.header.personaLabel", { name: personaName })
                : t("chat.header.personaNone")}
            </button>
          </div>
          {sceneSummary ? (
            <p className="truncate text-xs text-muted">{sceneSummary}</p>
          ) : (
            <p className="truncate text-xs text-muted sm:hidden">
              {personaName
                ? t("chat.header.personaLabel", { name: personaName })
                : t("chat.header.personaNone")}
            </p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="lg:hidden"
          aria-label={t("chat.header.openPanel")}
          title={t("chat.header.openPanel")}
          onClick={() => setRightOpen(true)}
        >
          <SlidersHorizontal className="size-4" aria-hidden="true" />
        </Button>

        {(onOpenInspector || onSummarize || onUndo) && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("chat.header.moreActions")}
                title={t("chat.header.moreActions")}
              >
                <MoreVertical className="size-4" aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {onOpenInspector ? (
                <DropdownMenuItem onSelect={onOpenInspector}>
                  <Eye className="size-4" aria-hidden="true" />
                  {t("chat.header.openInspector")}
                </DropdownMenuItem>
              ) : null}
              {onSummarize ? (
                <DropdownMenuItem disabled={isStreaming} onSelect={onSummarize}>
                  <Archive className="size-4" aria-hidden="true" />
                  {t("chat.header.summarizeNow")}
                </DropdownMenuItem>
              ) : null}
              {onUndo ? (
                <DropdownMenuItem disabled={isStreaming || !canUndo} onSelect={onUndo}>
                  <Undo2 className="size-4" aria-hidden="true" />
                  {t("chat.header.undoTurn")}
                </DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  );
}
