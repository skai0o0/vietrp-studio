import { useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useState } from "react";
import { usePageChrome } from "@/app/pageChrome";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCharacter, usePersonas } from "@/features/library/hooks";
import { t } from "@/i18n";
import { useCreateChat } from "../hooks";
import { NewWorldChat } from "../newWorldChat/NewWorldChat";
import { CharacterPicker } from "./CharacterPicker";
import { GreetingSwiper } from "./GreetingSwiper";
import { PersonaPicker } from "./PersonaPicker";
import { RecentChats } from "./RecentChats";

type ChatMode = "single" | "world";

function SingleChatForm({ initialCharacterId }: { initialCharacterId: string | null }) {
  const navigate = useNavigate();
  const personas = usePersonas();
  const [personaId, setPersonaId] = useState<string | null>(null);
  const [characterId, setCharacterId] = useState<string | null>(initialCharacterId);
  const [greetingIndex, setGreetingIndex] = useState(0);
  const character = useCharacter(characterId ?? undefined);
  const create = useCreateChat();

  const card = character.data;
  const blocked = Boolean(card && (card.needs_age || card.data.age == null));
  const canCreate = Boolean(card) && !blocked && !create.isPending;

  function submit(): void {
    if (!characterId) return;
    create.mutate(
      { character_id: characterId, persona_id: personaId, greeting_index: greetingIndex },
      {
        onSuccess: (chat) => void navigate(`/chat/${chat.id}`),
        onError: () => toast.error(t("newChat.createFailed")),
      },
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PersonaPicker value={personaId} onChange={setPersonaId} />
      <CharacterPicker
        value={characterId}
        onChange={(id) => {
          setCharacterId(id);
          setGreetingIndex(0);
        }}
      />
      {blocked && card ? (
        <div
          role="alert"
          data-testid="needs-age-block"
          className="rounded-lg border-2 border-danger bg-surface p-3 text-sm"
        >
          <p>{t("newChat.needsAge")}</p>
          <Link
            className="mt-2 inline-block font-medium text-accent underline"
            to={`/characters/${card.id}`}
          >
            {t("newChat.fixInEditor")}
          </Link>
        </div>
      ) : null}
      <GreetingSwiper
        greetings={card && !blocked ? (card.data.greetings ?? []) : null}
        index={greetingIndex}
        onIndex={setGreetingIndex}
        characterName={card?.name ?? ""}
        userName={personas.data?.find((x) => x.id === personaId)?.data.name ?? null}
      />
      <div>
        <Button type="button" disabled={!canCreate} onClick={submit}>
          {create.isPending ? t("newChat.creating") : t("newChat.create")}
        </Button>
      </div>
    </div>
  );
}

/** New chat page: mode switch between single chat and world chat. */
export default function NewChatPage() {
  const [params, setParams] = useSearchParams();
  const worldParam = params.get("world");
  const mode: ChatMode = params.get("mode") === "world" || Boolean(worldParam) ? "world" : "single";

  const left = useMemo(() => <RecentChats />, []);
  usePageChrome({ left });

  function selectMode(nextMode: string): void {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (nextMode === "world") {
          next.set("mode", "world");
        } else {
          next.delete("mode");
          next.delete("world");
        }
        return next;
      },
      { replace: true },
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-4 pb-24 md:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{t("newChat.title")}</h1>
        <Tabs value={mode} onValueChange={selectMode}>
          <TabsList aria-label={t("worldChat.modeLabel")}>
            <TabsTrigger value="single">{t("worldChat.modeSingle")}</TabsTrigger>
            <TabsTrigger value="world">{t("worldChat.modeWorld")}</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      {mode === "world" ? (
        <NewWorldChat initialWorldId={worldParam} />
      ) : (
        <SingleChatForm initialCharacterId={params.get("character")} />
      )}
    </div>
  );
}
