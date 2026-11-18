import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { chatApi } from "../api";

/** Wait for typing to pause before asking the server to count the prompt again. */
const PREVIEW_DEBOUNCE_MS = 500;

export function usePromptPreview(chatId: string, text: string, speaker?: string) {
  const [debounced, setDebounced] = useState(text);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(text), PREVIEW_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [text]);
  return useQuery({
    queryKey: ["chats", "prompt-preview", chatId, debounced, speaker ?? ""],
    queryFn: () => chatApi.promptPreview(chatId, debounced, speaker),
    staleTime: 10_000,
    placeholderData: (previous) => previous,
  });
}
