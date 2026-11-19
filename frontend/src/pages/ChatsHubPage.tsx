import { Globe2, MessageSquarePlus, UserRound } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { usePageChrome } from "@/app/pageChrome";
import { useChats } from "@/features/chat/hooks";
import { RecentChats } from "@/features/chat/newChat/RecentChats";
import { t } from "@/i18n";
import { useBreakpoint } from "@/lib/useBreakpoint";

export default function ChatsHubPage() {
  const breakpoint = useBreakpoint();
  const isDesktop = breakpoint === "desktop";
  const chats = useChats({ limit: 8 });
  const left = useMemo(() => (isDesktop ? <RecentChats /> : undefined), [isDesktop]);
  usePageChrome({ left, leftTitle: t("newChat.recent") });

  const items = chats.data ?? [];

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-4 pb-16 md:p-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{t("pages.chatsHub.title")}</h1>
        <p className="text-sm text-muted">{t("pages.chatsHub.subtitle")}</p>
      </header>

      <section aria-label={t("newChat.newChatLink")} className="grid gap-3 sm:grid-cols-2">
        <Link
          to="/chats/new"
          className="card-interactive flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 hover:border-border-strong"
        >
          <span className="flex items-center gap-2 text-base font-semibold text-fg">
            <UserRound className="size-5 text-accent-text" aria-hidden="true" />
            {t("pages.chatsHub.singleTitle")}
          </span>
          <p className="text-sm text-muted">{t("pages.chatsHub.singleDesc")}</p>
          <span className="mt-auto inline-flex items-center gap-1 pt-2 text-sm font-medium text-accent-text">
            <MessageSquarePlus className="size-4" aria-hidden="true" />
            {t("pages.chatsHub.startSingle")}
          </span>
        </Link>

        <Link
          to="/chats/new?mode=world"
          className="card-interactive flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 hover:border-border-strong"
        >
          <span className="flex items-center gap-2 text-base font-semibold text-fg">
            <Globe2 className="size-5 text-accent-2" aria-hidden="true" />
            {t("pages.chatsHub.worldTitle")}
          </span>
          <p className="text-sm text-muted">{t("pages.chatsHub.worldDesc")}</p>
          <span className="mt-auto inline-flex items-center gap-1 pt-2 text-sm font-medium text-accent-text">
            <MessageSquarePlus className="size-4" aria-hidden="true" />
            {t("pages.chatsHub.startWorld")}
          </span>
        </Link>
      </section>

      {!isDesktop ? (
        <section
          aria-label={t("pages.chatsHub.resumeTitle")}
          className="overflow-hidden rounded-lg border border-border-subtle bg-surface"
        >
          <RecentChats />
        </section>
      ) : (
        <section aria-labelledby="hub-recent-heading" className="flex flex-col gap-3">
          <h2 id="hub-recent-heading" className="text-base font-semibold">
            {t("pages.chatsHub.resumeTitle")}
          </h2>
          {chats.isPending ? (
            <p role="status" className="text-sm text-muted">
              {t("pages.loading")}
            </p>
          ) : items.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border bg-surface p-6 text-sm text-muted">
              {t("pages.chatsHub.empty")}
            </p>
          ) : (
            <ul className="grid gap-2.5 sm:grid-cols-2">
              {items.map((chat) => {
                const title = chat.title || chat.world_name || chat.character_name;
                const context = chat.world_name || chat.character_name;
                return (
                  <li key={chat.id}>
                    <Link
                      to={`/chat/${chat.id}`}
                      className="card-interactive flex flex-col gap-1 rounded-lg border border-border bg-surface p-3.5 hover:border-border-strong"
                    >
                      <span className="flex items-center gap-1.5 text-sm font-semibold text-fg">
                        {chat.mode === "world" ? (
                          <Globe2 className="size-4 shrink-0 text-accent-2" aria-hidden="true" />
                        ) : (
                          <UserRound className="size-4 shrink-0 text-muted" aria-hidden="true" />
                        )}
                        <span className="truncate">{title}</span>
                      </span>
                      <span className="truncate text-xs text-muted">
                        {context ? `${context} · ` : ""}
                        {t("newChat.messagesCount", { count: chat.messages_count })}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
