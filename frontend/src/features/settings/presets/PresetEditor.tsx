import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDeletePreset, useSavePreset } from "@/features/chat/hooks";
import { t } from "@/i18n";
import type { AgentId, PresetOut } from "@/types/chat";

/** Layers a preset may override (backend `OVERRIDABLE_LAYERS`); NSFW only applies to the writer. */
function layersFor(agent: AgentId): Array<"system" | "nsfw"> {
  return agent === "writer" ? ["system", "nsfw"] : ["system"];
}

interface PresetEditorProps {
  agent: AgentId;
  /** Omit to create a new preset. */
  preset?: PresetOut;
  onNotify: (message: string) => void;
}

export function PresetEditor({ agent, preset, onNotify }: PresetEditorProps) {
  const [name, setName] = useState(preset?.name ?? "");
  const [layers, setLayers] = useState<Record<string, string>>(preset?.layers ?? {});
  const save = useSavePreset();
  const remove = useDeletePreset();
  const idBase = preset?.id ?? "new";

  function submit(): void {
    save.mutate(
      { id: preset?.id, body: { agent, name: name.trim(), layers } },
      {
        onSuccess: () => {
          onNotify(t("presets.saved"));
          if (!preset) {
            setName("");
            setLayers({});
          }
        },
        onError: () => toast.error(t("presets.saveFailed")),
      },
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3">
      <h3 className="text-sm font-semibold">{preset ? preset.name : t("presets.new")}</h3>
      <div className="flex flex-col gap-1">
        <Label htmlFor={`preset-name-${idBase}`}>{t("presets.name")}</Label>
        <Input
          id={`preset-name-${idBase}`}
          value={name}
          placeholder={t("presets.namePlaceholder")}
          onChange={(event) => setName(event.target.value)}
        />
      </div>
      {layersFor(agent).map((layer) => (
        <div key={layer} className="flex flex-col gap-1">
          <Label htmlFor={`preset-${idBase}-${layer}`}>{t(`presets.layers.${layer}`)}</Label>
          <textarea
            id={`preset-${idBase}-${layer}`}
            rows={5}
            value={layers[layer] ?? ""}
            onChange={(event) =>
              setLayers((current) => ({ ...current, [layer]: event.target.value }))
            }
            className="w-full rounded-md border border-border bg-bg px-3 py-2 font-mono text-sm text-fg"
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="self-start"
            onClick={() => setLayers((current) => ({ ...current, [layer]: "" }))}
          >
            {t("presets.reset")}
          </Button>
        </div>
      ))}
      <p className="text-xs text-muted">{t("presets.layerHint")}</p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={save.isPending || name.trim() === ""} onClick={submit}>
          {t("presets.save")}
        </Button>
        {preset ? (
          <Button
            type="button"
            variant="outline"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(preset.id, {
                onSuccess: () => onNotify(t("presets.deleted")),
                onError: () => toast.error(t("presets.saveFailed")),
              })
            }
          >
            {t("presets.delete")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
