import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronRight,
  GitBranch,
  Globe,
  Layers,
  MoreHorizontal,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { ChatSummary, ChatUpdate } from "@/types/chat";
import { chatApi } from "../api";
import * as chatHooks from "../hooks";

type ModeFilter = "all" | "single" | "world";

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

function resolveOptionalHook<T>(getter: () => T, fallback: T): T {
  try {
    const candidate = getter();
    return typeof candidate === "function" ? candidate : fallback;
  } catch {
    return fallback;
  }
}

function useFallbackUpdateChat(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ChatUpdate) => chatApi.update(id, body),
    onSuccess: (chat) => {
      client.setQueryData(["chats", "detail", id], chat);
      void client.invalidateQueries({ queryKey: ["chats", "list"] });
    },
  });
}

function useFallbackDeleteChat() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => chatApi.remove(id),
    onSuccess: (_void, id) => {
      client.removeQueries({ queryKey: ["chats", "detail", id] });
      client.removeQueries({ queryKey: ["chats", "messages", id] });
      void client.invalidateQueries({ queryKey: ["chats", "list"] });
    },
  });
}

const useResolvedUpdateChat = resolveOptionalHook(
  () => chatHooks.useUpdateChat,
  useFallbackUpdateChat,
);

const useResolvedDeleteChat = resolveOptionalHook(
  () => chatHooks.useDeleteChat,
  useFallbackDeleteChat,
);

function normalizeQuery(value: string): string {
  return value.normalize("NFC").trim().toLowerCase();
}

function matchesSearch(chat: ChatSummary, q: string): boolean {
  if (!q) return true;
  return [chat.title, chat.world_name, chat.character_name].some(
    (field) => typeof field === "string" && normalizeQuery(field).includes(q),
  );
}

function formatRelativeTime(iso: string | undefined): string {
  if (!iso) return "";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "";
  const diffMin = Math.floor((Date.now() - ms) / 60_000);
  if (diffMin < 1) return t("newChat.timeJustNow");
  if (diffMin < 60) return t("newChat.timeMinutesAgo", { count: diffMin });
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return t("newChat.timeHoursAgo", { count: diffHour });
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return t("newChat.timeDaysAgo", { count: diffDay });
  return new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit" }).format(ms);
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

interface ChatTreeItemProps {
  node: ChatTreeNode;
  depth: number;
  groupLabel?: string;
  renamingId: string | null;
  renameDraft: string;
  renamePending: boolean;
  onRenameDraftChange: (value: string) => void;
  onStartRename: (chat: ChatSummary) => void;
  onCommitRename: () => void;
  onCancelRename: () => void;
  onRequestDelete: (chat: ChatSummary) => void;
}

function ChatTreeItem({
  node,
  depth,
  groupLabel,
  renamingId,
  renameDraft,
  renamePending,
  onRenameDraftChange,
  onStartRename,
  onCommitRename,
  onCancelRename,
  onRequestDelete,
}: ChatTreeItemProps): ReactNode {
  const { chat, children } = node;
  const location = useLocation();
  const isActive = location.pathname === `/chat/${chat.id}`;
  const title = chat.title || chat.world_name || chat.character_name || "";
  const subtitleContext = chat.world_name || chat.character_name || t("worldChat.badge");
  const showContext = !groupLabel || subtitleContext !== groupLabel;
  const relativeTime = formatRelativeTime(chat.updated_at);
  const metaParts = [
    showContext ? subtitleContext : null,
    t("newChat.messagesCount", { count: chat.messages_count }),
    relativeTime || null,
  ].filter(Boolean);

  const forkLabel =
    chat.forked_at_seq !== null && chat.forked_at_seq !== undefined
      ? t("newChat.forkBadge", { seq: chat.forked_at_seq })
      : t("newChat.forkBadgeShort");

  const isRenaming = renamingId === chat.id;
  const renameInputRef = useRef<HTMLInputElement>(null);
  const indent = depth > 0 && depth <= 3;

  useEffect(() => {
    if (isRenaming) renameInputRef.current?.focus();
  }, [isRenaming]);

  function handleRenameKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      onCommitRename();
    } else if (event.key === "Escape") {
      event.preventDefault();
      onCancelRename();
    }
  }

  return (
    <li className={cn(indent && "ml-3 border-l border-border-subtle pl-2")}>
      {isRenaming ? (
        <div className="flex flex-col gap-1.5 rounded-md border border-accent bg-surface-2 p-2">
          <Input
            ref={renameInputRef}
            aria-label={t("newChat.renamePlaceholder")}
            placeholder={t("newChat.renamePlaceholder")}
            value={renameDraft}
            disabled={renamePending}
            onChange={(e) => onRenameDraftChange(e.target.value)}
            onKeyDown={handleRenameKey}
            className="h-8 text-xs md:h-8"
          />
          <div className="flex items-center justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t("newChat.renameCancel")}
              onClick={onCancelRename}
              className="size-8"
            >
              <X className="size-3.5" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              size="icon-sm"
              disabled={!renameDraft.trim() || renamePending}
              aria-label={t("newChat.renameSave")}
              onClick={() => onCommitRename()}
              className="size-8"
            >
              <Check className="size-3.5" aria-hidden="true" />
            </Button>
          </div>
        </div>
      ) : (
        <div
          data-eink-active={isActive || undefined}
          className={cn(
            "group relative flex items-start gap-1 rounded-md border-l-2 border-transparent transition-colors duration-fast ease-ui",
            isActive ? "border-l-accent bg-surface-2 text-fg" : "hover:bg-hover",
          )}
        >
          <NavLink
            to={`/chat/${chat.id}`}
            className="flex min-w-0 flex-1 flex-col px-2.5 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            <span className="flex min-w-0 items-center gap-1.5 font-medium">
              {chat.mode === "world" ? (
                <Globe className="size-3.5 shrink-0 text-accent-2" aria-hidden="true" />
              ) : null}
              <span className="truncate">{title}</span>
            </span>
            <span className="truncate text-xs text-muted">{metaParts.join(" · ")}</span>
            {chat.parent_chat_id ? (
              <span className="mt-1 inline-flex w-fit items-center gap-1 rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 text-2xs text-accent-2">
                <GitBranch className="size-3 shrink-0" aria-hidden="true" />
                <span>{forkLabel}</span>
              </span>
            ) : null}
          </NavLink>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("newChat.rowActions", { title })}
                className="mr-1 mt-1.5 size-8 shrink-0 opacity-100 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 data-[state=open]:opacity-100"
              >
                <MoreHorizontal className="size-4" aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => onStartRename(chat)}>
                <Pencil className="size-4" aria-hidden="true" />
                {t("newChat.rename")}
              </DropdownMenuItem>
              <DropdownMenuItem destructive onSelect={() => onRequestDelete(chat)}>
                <Trash2 className="size-4" aria-hidden="true" />
                {t("newChat.deleteChat")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      {children.length > 0 ? (
        <ul className="mt-1 flex flex-col gap-1">
          {children.map((child) => (
            <ChatTreeItem
              key={child.chat.id}
              node={child}
              depth={depth + 1}
              groupLabel={groupLabel}
              renamingId={renamingId}
              renameDraft={renameDraft}
              renamePending={renamePending}
              onRenameDraftChange={onRenameDraftChange}
              onStartRename={onStartRename}
              onCommitRename={onCommitRename}
              onCancelRename={onCancelRename}
              onRequestDelete={onRequestDelete}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/** Left-sidebar list of recent chats with search, mode filters, collapsible groups, fork tree, and row actions. */
export function RecentChats() {
  const chats = chatHooks.useChats({ limit: 30 });
  const location = useLocation();
  const navigate = useNavigate();

  const [search, setSearch] = useState("");
  const [modeFilter, setModeFilter] = useState<ModeFilter>("all");
  const [grouped, setGrouped] = useState(true);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ChatSummary | null>(null);
  const [actionError, setActionError] = useState(false);

  const renameMutation = useResolvedUpdateChat(renamingId ?? "");
  const deleteMutation = useResolvedDeleteChat();

  const items = useMemo(() => chats.data ?? [], [chats.data]);
  const query = normalizeQuery(search);
  const filtered = useMemo(
    () =>
      items.filter(
        (chat) =>
          (modeFilter === "all" || chat.mode === modeFilter) && matchesSearch(chat, query),
      ),
    [items, modeFilter, query],
  );
  const roots = useMemo(() => buildTree(filtered), [filtered]);
  const groups = useMemo(() => groupRoots(roots), [roots]);

  function startRename(chat: ChatSummary) {
    setActionError(false);
    setRenamingId(chat.id);
    setRenameDraft(chat.title || chat.world_name || chat.character_name || "");
  }

  function commitRename() {
    const nextTitle = renameDraft.trim();
    if (!nextTitle || !renamingId) return;
    setActionError(false);
    renameMutation.mutate(
      { title: nextTitle },
      {
        onSuccess: () => setRenamingId(null),
        onError: () => setActionError(true),
      },
    );
  }

  function confirmDelete() {
    if (!deleteTarget) return;
    const removed = deleteTarget;
    setActionError(false);
    deleteMutation.mutate(removed.id, {
      onSuccess: () => {
        setDeleteTarget(null);
        if (location.pathname === `/chat/${removed.id}`) {
          navigate("/chats", { replace: true });
        }
      },
      onError: () => setActionError(true),
    });
  }

  function toggleGroup(key: string) {
    setCollapsedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  const modeFilters: Array<{ value: ModeFilter; label: string }> = [
    { value: "all", label: t("newChat.filterAll") },
    { value: "single", label: t("newChat.filterSingle") },
    { value: "world", label: t("newChat.filterWorld") },
  ];

  return (
    <nav aria-label={t("newChat.recent")} className="flex flex-col">
      <div className="sticky top-0 z-sticky flex flex-col gap-2 border-b border-border-subtle bg-surface/95 px-3 pb-2.5 pt-3 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <NavLink
            to="/chats/new"
            end
            className="inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md border border-border bg-surface-2 px-3 text-sm font-medium text-fg transition-colors duration-fast ease-ui hover:border-border-strong hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            <Plus className="size-4" aria-hidden="true" />
            <span>{t("newChat.newChatLink")}</span>
          </NavLink>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-pressed={grouped}
            aria-label={t("newChat.groupChats")}
            title={t("newChat.groupChats")}
            data-eink-active={grouped || undefined}
            onClick={() => setGrouped((g) => !g)}
            className={cn(grouped && "bg-surface-2 text-fg")}
          >
            <Layers className="size-4" aria-hidden="true" />
          </Button>
        </div>

        <Input
          type="search"
          aria-label={t("newChat.searchChats")}
          placeholder={t("newChat.searchChats")}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="h-9 md:h-9"
        />

        <div
          role="group"
          aria-label={t("newChat.filterLabel")}
          className="grid grid-cols-3 gap-1"
        >
          {modeFilters.map((f) => {
            const active = modeFilter === f.value;
            return (
              <button
                key={f.value}
                type="button"
                aria-pressed={active}
                data-eink-active={active || undefined}
                onClick={() => setModeFilter(f.value)}
                className={cn(
                  "h-8 rounded-md px-2 text-xs font-medium transition-colors duration-fast ease-ui",
                  active
                    ? "bg-surface-2 text-fg border border-border-strong"
                    : "text-muted hover:bg-hover hover:text-fg",
                )}
              >
                {f.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2 p-3">
        {actionError ? (
          <p role="alert" className="text-xs text-danger-text">
            {t("newChat.actionFailed")}
          </p>
        ) : null}

        {chats.isLoading ? (
          <div aria-busy="true" className="flex flex-col gap-2">
            {[0, 1, 2].map((idx) => (
              <div
                key={idx}
                className="h-12 rounded-md border border-border-subtle bg-surface-2 motion-safe:animate-pulse"
              />
            ))}
          </div>
        ) : null}

        {chats.isError ? (
          <div className="flex flex-col items-start gap-2 rounded-md border border-danger/40 bg-surface-2 p-2.5">
            <p className="text-xs text-danger-text">{t("newChat.recentLoadFailed")}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void chats.refetch?.()}
            >
              <RotateCcw className="size-3.5" aria-hidden="true" />
              {t("newChat.retry")}
            </Button>
          </div>
        ) : null}

        {chats.isSuccess && items.length === 0 ? (
          <p className="px-1 text-xs text-muted">{t("newChat.recentEmpty")}</p>
        ) : null}
        {items.length > 0 && filtered.length === 0 ? (
          <p className="px-1 text-xs text-muted">{t("newChat.searchEmpty")}</p>
        ) : null}

        {grouped ? (
          <div className="flex flex-col gap-2.5">
            {groups.map((group) => {
              const collapsed = Boolean(collapsedGroups[group.key]);
              return (
                <section key={group.key} aria-label={group.label} className="flex flex-col gap-1">
                  <button
                    type="button"
                    aria-expanded={!collapsed}
                    aria-label={t("newChat.toggleGroup", { name: group.label })}
                    onClick={() => toggleGroup(group.key)}
                    className="flex min-h-8 items-center gap-1.5 rounded px-1 text-left text-xs font-medium text-muted hover:bg-hover hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                  >
                    <ChevronRight
                      className={cn(
                        "size-3.5 shrink-0 transition-transform duration-fast ease-ui motion-reduce:transition-none",
                        !collapsed && "rotate-90",
                      )}
                      aria-hidden="true"
                    />
                    {group.mode === "world" ? (
                      <Globe className="size-3.5 shrink-0 text-accent-2" aria-hidden="true" />
                    ) : (
                      <UserRound className="size-3.5 shrink-0" aria-hidden="true" />
                    )}
                    <span className="truncate">{group.label}</span>
                  </button>
                  {!collapsed ? (
                    <ul className="flex flex-col gap-0.5">
                      {group.roots.map((node) => (
                        <ChatTreeItem
                          key={node.chat.id}
                          node={node}
                          depth={0}
                          groupLabel={group.label}
                          renamingId={renamingId}
                          renameDraft={renameDraft}
                          renamePending={renameMutation.isPending}
                          onRenameDraftChange={setRenameDraft}
                          onStartRename={startRename}
                          onCommitRename={commitRename}
                          onCancelRename={() => setRenamingId(null)}
                          onRequestDelete={setDeleteTarget}
                        />
                      ))}
                    </ul>
                  ) : null}
                </section>
              );
            })}
          </div>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {roots.map((node) => (
              <ChatTreeItem
                key={node.chat.id}
                node={node}
                depth={0}
                renamingId={renamingId}
                renameDraft={renameDraft}
                renamePending={renameMutation.isPending}
                onRenameDraftChange={setRenameDraft}
                onStartRename={startRename}
                onCommitRename={commitRename}
                onCancelRename={() => setRenamingId(null)}
                onRequestDelete={setDeleteTarget}
              />
            ))}
          </ul>
        )}
      </div>

      <Dialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !deleteMutation.isPending) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogTitle>{t("newChat.confirmDeleteTitle")}</DialogTitle>
          <DialogDescription>
            {t("newChat.confirmDeleteDesc", {
              title:
                deleteTarget?.title ||
                deleteTarget?.world_name ||
                deleteTarget?.character_name ||
                "",
            })}
          </DialogDescription>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              disabled={deleteMutation.isPending}
              onClick={() => setDeleteTarget(null)}
            >
              {t("newChat.renameCancel")}
            </Button>
            <Button
              type="button"
              variant="danger"
              loading={deleteMutation.isPending}
              onClick={confirmDelete}
            >
              {deleteMutation.isPending ? t("newChat.deleting") : t("newChat.confirmDeleteAction")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </nav>
  );
}
