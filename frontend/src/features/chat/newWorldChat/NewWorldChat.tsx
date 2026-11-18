import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { usePersonas, useWorld } from "@/features/library/hooks";
import { t } from "@/i18n";
import { useCreateChat } from "../hooks";
import { PersonaPicker } from "../newChat/PersonaPicker";
import { CastPicker } from "./CastPicker";
import { OpeningSwiper } from "./OpeningSwiper";
import { WorldPicker } from "./WorldPicker";

interface NewWorldChatProps {
  initialWorldId?: string | null;
}

/** New world-chat flow: world -> opening -> cast -> persona -> create. */
export function NewWorldChat({ initialWorldId = null }: NewWorldChatProps) {
  const navigate = useNavigate();
  const personas = usePersonas();
  const [worldId, setWorldId] = useState<string | null>(initialWorldId);
  const [openingIndex, setOpeningIndex] = useState(0);
  const [castIds, setCastIds] = useState<string[]>([]);
  const [personaId, setPersonaId] = useState<string | null>(null);

  const world = useWorld(worldId ?? undefined);
  const create = useCreateChat();

  const openings = world.data?.data.openings ?? [];
  const safeIndex = openings.length > 0 ? Math.min(openingIndex, openings.length - 1) : 0;
  const selectedOpening = openings[safeIndex];
  const userName = personas.data?.find((x) => x.id === personaId)?.data.name ?? null;
  const canCreate = Boolean(world.data) && castIds.length > 0 && !create.isPending;

  function toggleCast(id: string): void {
    setCastIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function submit(): void {
    if (!worldId || !canCreate) return;
    create.mutate(
      {
        mode: "world",
        world_id: worldId,
        opening_id: selectedOpening?.id ?? null,
        cast_ids: castIds,
        persona_id: personaId,
      },
      {
        onSuccess: (chat) => void navigate(`/chat/${chat.id}`),
        onError: () => toast.error(t("newChat.createFailed")),
      },
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <WorldPicker
        value={worldId}
        onChange={(id) => {
          setWorldId(id);
          setOpeningIndex(0);
        }}
      />
      <OpeningSwiper
        world={world.data}
        isLoading={world.isLoading}
        isError={world.isError}
        index={safeIndex}
        onIndex={setOpeningIndex}
        userName={userName}
      />
      <CastPicker selectedIds={castIds} onToggle={toggleCast} />
      <PersonaPicker value={personaId} onChange={setPersonaId} />
      <div className="flex flex-col items-start gap-2">
        <Button type="button" disabled={!canCreate} onClick={submit}>
          {create.isPending ? t("newChat.creating") : t("worldChat.create")}
        </Button>
        {world.data && castIds.length === 0 ? (
          <p className="text-xs text-muted">{t("worldChat.pickCastHint")}</p>
        ) : null}
      </div>
    </div>
  );
}
