import { useMemo } from "react";
import { usePageChrome } from "@/app/pageChrome";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { t } from "@/i18n";
import { useChat } from "../hooks";
import { RecentChats } from "../newChat/RecentChats";
import { LiveStateEditor } from "../state/LiveStateEditor";
import { ChatSettingsPanel } from "./ChatSettingsPanel";

function WorldRightSidebar({ chatId }: { chatId: string }) {
  const chat = useChat(chatId);
  if (!chat.data) return null;

  return (
    <Tabs defaultValue="state" className="flex flex-col">
      <div className="sticky top-0 z-10 border-b border-border bg-surface py-2 pl-3 pr-12 lg:px-3">
        <TabsList aria-label={t("chatSettings.tabs.label")} className="grid w-full grid-cols-2">
          <TabsTrigger value="state">{t("chatSettings.tabs.state")}</TabsTrigger>
          <TabsTrigger value="settings">{t("chatSettings.tabs.settings")}</TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="state" className="mt-0">
        <LiveStateEditor chat={chat.data} />
      </TabsContent>
      <TabsContent value="settings" className="mt-0">
        <ChatSettingsPanel chatId={chatId} />
      </TabsContent>
    </Tabs>
  );
}

/** Renders nothing; fills the left (recent chats) and right (state/settings) sidebars for a chat page. */
export function ChatChrome({ chatId }: { chatId: string }) {
  const chat = useChat(chatId);
  const isWorld = chat.data?.mode === "world";
  const left = useMemo(() => <RecentChats />, []);
  const right = useMemo(
    () => (isWorld ? <WorldRightSidebar chatId={chatId} /> : <ChatSettingsPanel chatId={chatId} />),
    [chatId, isWorld],
  );
  usePageChrome({ left, right });
  return null;
}
