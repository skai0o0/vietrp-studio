import { MessageCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { buttonVariants } from "@/components/ui/button";
import { t } from "@/i18n";

/** "Chat" button for the character detail page; opens the new-chat flow with the card preselected. */
export function StartChatButton({ characterId }: { characterId: string }) {
  return (
    <Link
      to={`/create/chat?character=${encodeURIComponent(characterId)}`}
      className={buttonVariants({ variant: "outline", size: "sm" })}
    >
      <MessageCircle aria-hidden="true" />
      {t("newChat.startChat")}
    </Link>
  );
}
