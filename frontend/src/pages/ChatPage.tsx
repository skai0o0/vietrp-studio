import { useParams } from "react-router-dom";
import { ChatView } from "@/features/chat/components/ChatView";
import { ChatChrome } from "@/features/chat/settings/ChatChrome";
import { t } from "@/i18n";

export default function ChatPage() {
  const { chatId } = useParams<{ chatId: string }>();
  if (!chatId)
    return <p className="p-6 text-center text-sm text-muted">{t("chat.page.invalid")}</p>;
  return (
    <>
      <ChatChrome chatId={chatId} />
      <ChatView chatId={chatId} key={chatId} />
    </>
  );
}
