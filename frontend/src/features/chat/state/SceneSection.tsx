import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import type { CastMemberSummary, CharacterSceneState, SceneState } from "@/types/chat";
import { ManualBadge } from "./ManualBadge";
import { normalizeSceneState } from "./stateHelpers";

interface SceneSectionProps {
  scene: SceneState | undefined;
  presentIds: readonly string[];
  cast: readonly CastMemberSummary[];
  isManual: boolean;
  pending: boolean;
  onSave: (scene: SceneState) => void;
}

const CHAR_FIELDS: Array<{
  key: keyof CharacterSceneState;
  labelKey:
    | "stateEditor.scene.mood"
    | "stateEditor.scene.outfit"
    | "stateEditor.scene.pose"
    | "stateEditor.scene.holding"
    | "stateEditor.scene.condition";
}> = [
  { key: "mood", labelKey: "stateEditor.scene.mood" },
  { key: "outfit", labelKey: "stateEditor.scene.outfit" },
  { key: "pose", labelKey: "stateEditor.scene.pose" },
  { key: "holding", labelKey: "stateEditor.scene.holding" },
  { key: "condition", labelKey: "stateEditor.scene.condition" },
];

export function SceneSection({
  scene,
  presentIds,
  cast,
  isManual,
  pending,
  onSave,
}: SceneSectionProps) {
  const normalized = normalizeSceneState(scene);
  const sceneKey = JSON.stringify(normalized);
  const [override, setOverride] = useState<{ key: string; value: Required<SceneState> } | null>(
    null,
  );
  const draft = override && override.key === sceneKey ? override.value : normalized;

  const [newEnvKey, setNewEnvKey] = useState("");
  const [newEnvVal, setNewEnvVal] = useState("");
  const [newItem, setNewItem] = useState("");

  function updateDraft(updater: (prev: Required<SceneState>) => Required<SceneState>): void {
    setOverride((prev) => {
      const current = prev && prev.key === sceneKey ? prev.value : normalized;
      return { key: sceneKey, value: updater(current) };
    });
  }

  const dirty = JSON.stringify(draft) !== sceneKey;
  const visibleCharIds = Array.from(new Set(presentIds));

  function setEnvValue(key: string, value: string): void {
    updateDraft((prev) => ({ ...prev, env: { ...prev.env, [key]: value } }));
  }

  function removeEnvKey(key: string): void {
    updateDraft((prev) => {
      const next = { ...prev.env };
      delete next[key];
      return { ...prev, env: next };
    });
  }

  function addEnv(): void {
    const k = newEnvKey.trim();
    if (!k) return;
    setEnvValue(k, newEnvVal.trim());
    setNewEnvKey("");
    setNewEnvVal("");
  }

  function setCharField(charId: string, field: keyof CharacterSceneState, value: string): void {
    updateDraft((prev) => ({
      ...prev,
      chars: {
        ...prev.chars,
        [charId]: { ...(prev.chars[charId] ?? {}), [field]: value },
      },
    }));
  }

  function addItem(): void {
    const item = newItem.trim();
    if (!item) return;
    updateDraft((prev) => ({ ...prev, items: [...prev.items, item] }));
    setNewItem("");
  }

  function removeItem(index: number): void {
    updateDraft((prev) => ({ ...prev, items: prev.items.filter((_, i) => i !== index) }));
  }

  function charLabel(id: string): string {
    return cast.find((m) => m.id === id || m.character_id === id)?.name ?? id;
  }

  return (
    <section
      aria-labelledby="state-scene-heading"
      className="flex flex-col gap-4 rounded-lg border border-border bg-bg p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="state-scene-heading" className="text-sm font-semibold">
          {t("stateEditor.scene.title")}
        </h3>
        <ManualBadge visible={isManual} />
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted">
          {t("stateEditor.scene.envTitle")}
        </h4>
        {Object.entries(draft.env).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2">
            <Label htmlFor={`scene-env-${k}`} className="w-24 shrink-0 truncate text-xs">
              {k}
            </Label>
            <Input
              id={`scene-env-${k}`}
              value={v}
              onChange={(e) => setEnvValue(k, e.target.value)}
              className="h-9 min-w-0 flex-1 text-xs"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-9 shrink-0"
              aria-label={t("stateEditor.scene.removeEnv", { key: k })}
              onClick={() => removeEnvKey(k)}
            >
              <Trash2 aria-hidden="true" />
            </Button>
          </div>
        ))}
        <div className="flex flex-wrap gap-2">
          <Input
            aria-label={t("stateEditor.scene.envKeyPlaceholder")}
            placeholder={t("stateEditor.scene.envKeyPlaceholder")}
            value={newEnvKey}
            onChange={(e) => setNewEnvKey(e.target.value)}
            className="h-9 min-w-0 flex-1 text-xs"
          />
          <Input
            aria-label={t("stateEditor.scene.envValuePlaceholder")}
            placeholder={t("stateEditor.scene.envValuePlaceholder")}
            value={newEnvVal}
            onChange={(e) => setNewEnvVal(e.target.value)}
            className="h-9 min-w-0 flex-1 text-xs"
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="size-9 shrink-0"
            aria-label={t("stateEditor.scene.addEnv")}
            onClick={addEnv}
          >
            <Plus aria-hidden="true" />
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted">
          {t("stateEditor.scene.charsTitle")}
        </h4>
        {visibleCharIds.length === 0 ? (
          <p className="text-xs text-muted">{t("stateEditor.scene.noPresentChars")}</p>
        ) : (
          visibleCharIds.map((charId) => {
            const cState = draft.chars[charId] ?? {};
            return (
              <div
                key={charId}
                data-testid={`scene-char-${charId}`}
                className="flex flex-col gap-2 rounded-md border border-border bg-surface p-2.5"
              >
                <p className="text-xs font-semibold">{charLabel(charId)}</p>
                {CHAR_FIELDS.map(({ key, labelKey }) => (
                  <div key={key} className="flex flex-col gap-1">
                    <Label htmlFor={`scene-${charId}-${key}`} className="text-xs text-muted">
                      {t(labelKey)}
                    </Label>
                    <Input
                      id={`scene-${charId}-${key}`}
                      value={cState[key] ?? ""}
                      onChange={(e) => setCharField(charId, key, e.target.value)}
                      className="h-9 text-xs"
                    />
                  </div>
                ))}
              </div>
            );
          })
        )}
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted">
          {t("stateEditor.scene.itemsTitle")}
        </h4>
        {draft.items.length === 0 ? (
          <p className="text-xs text-muted">{t("stateEditor.scene.itemsEmpty")}</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {draft.items.map((item, idx) => (
              <li
                key={`${item}-${idx}`}
                className="flex items-center justify-between gap-2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs"
              >
                <span className="min-w-0 break-words">{item}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 shrink-0"
                  aria-label={t("stateEditor.scene.removeItem", { item })}
                  onClick={() => removeItem(idx)}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex gap-2">
          <Input
            aria-label={t("stateEditor.scene.itemPlaceholder")}
            placeholder={t("stateEditor.scene.itemPlaceholder")}
            value={newItem}
            onChange={(e) => setNewItem(e.target.value)}
            className="h-9 min-w-0 flex-1 text-xs"
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="size-9 shrink-0"
            aria-label={t("stateEditor.scene.addItem")}
            onClick={addItem}
          >
            <Plus aria-hidden="true" />
          </Button>
        </div>
      </div>

      <Button type="button" size="sm" disabled={!dirty || pending} onClick={() => onSave(draft)}>
        {pending ? t("stateEditor.saving") : t("stateEditor.save")}
      </Button>
    </section>
  );
}
