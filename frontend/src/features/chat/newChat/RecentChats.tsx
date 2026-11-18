import { GitBranch, Globe, Layers, Plus, UserRound } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { ChatSummary } from "@/types/chat";
import { useChats } from "../hooks";

interface ChatTreeNode {
  chat: ChatSummary;
  children: ChatTreeNode[];
}

interface ChatGroup {
  key: string;
  label: string;
  mode: ChatSummary["mode"];
  roots: ChatTreeNode[];
}

function normalizeQuery(value: string): string {
  return value.normalize("NFC").trim().toLowerCase();
}

function matchesSearch(chat: ChatSummary, q: string): boolean {
  if (!q) return true;
  return [chat.title, chat.world_name, chat.character_name].some(
    (field) => typeof field === "string" && normalizeQuery(field).includes(q),
  );
}

function buildTree(items: readonly ChatSummary[]): ChatTreeNode[] {
  const byId = new Map(items.map((c) => [c.id, c]));
  const childrenMap = new Map<string, ChatSummary[]>();
  const roots: ChatSummary[] = [];

  for (const chat of items) {
    const parentId = chat.parent_chat_id;
    if (parentId && parentId !== chat.id && byId.has(parentId)) {
      const bucket = childrenMap.get(parentId);
      if (bucket) bucket.push(chat);
      else childrenMap.set(parentId, [chat]);
    } else {
      roots.push(chat);
    }
  }

  function toNode(chat: ChatSummary, seen: Set<string>): ChatTreeNode {
    const nextSeen = new Set(seen);
    nextSeen.add(chat.id);
    const childList = (childrenMap.get(chat.id) ?? []).filter((c) => !nextSeen.has(c.id));
    return {
      chat,
      children: childList.map((child) => toNode(child, nextSeen)),
    };
  }

  return roots.map((root) => toNode(root, new Set()));
}

function groupRoots(roots: readonly ChatTreeNode[]): ChatGroup[] {
  const groups = new Map<string, ChatGroup>();
  for (const node of roots) {
    const { chat } = node;
    const isWorld = chat.mode === "world";
    const key = isWorld
      ? `world:${chat.world_id ?? chat.world_name ?? "unknown"}`
      : `char:${chat.character_id ?? chat.character_name ?? "unknown"}`;
    const label = isWorld
      ? chat.world_name || t("newChat.groupWorldFallback")
      : chat.character_name || t("newChat.groupSingleFallback");
    const existing = groups.get(key);
    if (existing) {
      existing.roots.push(node);
    } else {
      groups.set(key, { key, label, mode: chat.mode, roots: [node] });
    }
  }
  return Array.from(groups.values());
}

function ChatTreeItem({ node, depth }: { node: ChatTreeNode; depth: number }): ReactNode {
  const { chat, children } = node;
  const title = chat.title || chat.world_name || chat.character_name;
  const subtitleContext = chat.world_name || chat.character_name || t("worldChat.badge");
  const forkLabel =
    chat.forked_at_seq !== null && chat.forked_at_seq !== undefined
      ? t("newChat.forkBadge", { seq: chat.forked_at_seq })
      : t("newChat.forkBadgeShort");

  return (
    <li className={cn(depth > 0 && "ml-3 border-l border-border pl-2")}>
      <NavLink
        to={`/chat/${chat.id}`}
        className={({ isActive }) =>
          cn(
            "flex flex-col rounded-md px-3 py-2 text-sm hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus",
            isActive && "bg-surface-2 text-fg",
          )
        }
      >
        <span className="flex min-w-0 items-center gap-1.5 font-medium">
          {chat.mode === "world" ? (
            <Globe className="size-3.5 shrink-0 text-accent-2" aria-hidden="true" />
          ) : null}
          <span className="truncate">{title}</span>
        </span>
        <span className="truncate text-xs text-muted">
          {subtitleContext} · {t("newChat.messagesCount", { count: chat.messages_count })}
        </span>
        {chat.parent_chat_id ? (
          <span className="mt-1 inline-flex w-fit items-center gap-1 rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 text-[11px] text-accent-2">
            <GitBranch className="size-3 shrink-0" aria-hidden="true" />
            <span>{forkLabel}</span>
          </span>
        ) : null}
      </NavLink>
      {children.length > 0 ? (
        <ul className="mt-1 flex flex-col gap-1">
          {children.map((child) => (
            <ChatTreeItem key={child.chat.id} node={child} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/** Left-sidebar list of recent chats with search, grouping, and fork tree. */
export function RecentChats() {
  const chats = useChats({ limit: 30 });
  const [search, setSearch] = useState("");
  const [grouped, setGrouped] = useState(true);

  const items = useMemo(() => chats.data ?? [], [chats.data]);
  const query = normalizeQuery(search);
  const filtered = useMemo(
    () => items.filter((chat) => matchesSearch(chat, query)),
    [items, query],
  );
  const roots = useMemo(() => buildTree(filtered), [filtered]);
  const groups = useMemo(() => groupRoots(roots), [roots]);

  return (
    <nav aria-label={t("newChat.recent")} className="flex flex-col gap-2 p-3">
      <NavLink
        to="/create/chat"
        end
        className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        <Plus className="size-4" aria-hidden="true" />
        {t("newChat.newChatLink")}
      </NavLink>
      <Input
        type="search"
        aria-label={t("newChat.searchChats")}
        placeholder={t("newChat.searchChats")}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        className="h-9"
      />
      <div className="flex items-center justify-between gap-2 px-1">
        <h2 className="text-xs font-semibold uppercase text-muted">{t("newChat.recent")}</h2>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-pressed={grouped}
          onClick={() => setGrouped((g) => !g)}
          className={cn("h-7 gap-1 px-2 text-xs", grouped && "bg-surface-2 text-fg")}
        >
          <Layers className="size-3.5" aria-hidden="true" />
          <span>{t("newChat.groupChats")}</span>
        </Button>
      </div>
      {chats.isError ? (
        <p className="px-1 text-xs text-danger">{t("newChat.recentLoadFailed")}</p>
      ) : null}
      {chats.isSuccess && items.length === 0 ? (
        <p className="px-1 text-xs text-muted">{t("newChat.recentEmpty")}</p>
      ) : null}
      {items.length > 0 && filtered.length === 0 ? (
        <p className="px-1 text-xs text-muted">{t("newChat.searchEmpty")}</p>
      ) : null}
      {grouped ? (
        <div className="flex flex-col gap-3">
          {groups.map((group) => (
            <section key={group.key} aria-label={group.label} className="flex flex-col gap-1">
              <h3 className="flex items-center gap-1.5 px-1 text-xs font-medium text-muted">
                {group.mode === "world" ? (
                  <Globe className="size-3.5 shrink-0 text-accent-2" aria-hidden="true" />
                ) : (
                  <UserRound className="size-3.5 shrink-0" aria-hidden="true" />
                )}
                <span className="truncate">{group.label}</span>
              </h3>
              <ul className="flex flex-col gap-1">
                {group.roots.map((node) => (
                  <ChatTreeItem key={node.chat.id} node={node} depth={0} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        <ul className="flex flex-col gap-1">
          {roots.map((node) => (
            <ChatTreeItem key={node.chat.id} node={node} depth={0} />
          ))}
        </ul>
      )}
    </nav>
  );
}
