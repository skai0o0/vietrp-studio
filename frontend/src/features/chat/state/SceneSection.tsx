import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import type { CastMemberSummary, CharacterSceneState, SceneState } from "@/types/chat";
import { ManualBadge } from "./ManualBadge";
import { normalizeSceneState } from "./stateHelpers";

interface SceneSectionProps {
  scene: SceneState | undefined;
  presentIds: readonly string[];
  cast: readonly CastMemberSummary[];
  isManual: boolean;
  pending: boolean;
  embedded?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
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
  embedded = false,
  onDirtyChange,
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
  const [selectedCharId, setSelectedCharId] = useState<string | null>(null);

  function updateDraft(updater: (prev: Required<SceneState>) => Required<SceneState>): void {
    setOverride((prev) => {
      const current = prev && prev.key === sceneKey ? prev.value : normalized;
      return { key: sceneKey, value: updater(current) };
    });
  }

  const dirty = JSON.stringify(draft) !== sceneKey;
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  const visibleCharIds = Array.from(new Set(presentIds));
  const activeCharId =
    selectedCharId && visibleCharIds.includes(selectedCharId)
      ? selectedCharId
      : (visibleCharIds[0] ?? null);

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

  const Container = embedded ? "div" : "section";

  return (
    <Container
      {...(!embedded ? { "aria-labelledby": "state-scene-heading" } : {})}
      className={cn(
        "flex flex-col gap-4",
        !embedded && "rounded-lg border border-border bg-surface p-3",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        {!embedded ? (
          <h3 id="state-scene-heading" className="text-sm font-semibold">
            {t("stateEditor.scene.title")}
          </h3>
        ) : (
          <span className="text-xs font-medium text-muted">{t("stateEditor.scene.envTitle")}</span>
        )}
        <ManualBadge visible={isManual} />
      </div>

      <div className="flex flex-col gap-2">
        {!embedded ? (
          <h4 className="text-xs font-semibold uppercase text-muted">
            {t("stateEditor.scene.envTitle")}
          </h4>
        ) : null}
        {Object.entries(draft.env).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2">
            <Label htmlFor={`scene-env-${k}`} className="w-24 shrink-0 truncate text-xs">
              {k}
            </Label>
            <Input
              id={`scene-env-${k}`}
              value={v}
              onChange={(e) => setEnvValue(k, e.target.value)}
              className="h-9 min-w-0 flex-1 text-xs md:h-9"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="shrink-0"
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
            className="h-9 min-w-0 flex-1 text-xs md:h-9"
          />
          <Input
            aria-label={t("stateEditor.scene.envValuePlaceholder")}
            placeholder={t("stateEditor.scene.envValuePlaceholder")}
            value={newEnvVal}
            onChange={(e) => setNewEnvVal(e.target.value)}
            className="h-9 min-w-0 flex-1 text-xs md:h-9"
          />
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            className="shrink-0"
            aria-label={t("stateEditor.scene.addEnv")}
            onClick={addEnv}
          >
            <Plus aria-hidden="true" />
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2 border-t border-border-subtle pt-3">
        <h4 className="text-xs font-semibold uppercase text-muted">
          {t("stateEditor.scene.charsTitle")}
        </h4>
        {visibleCharIds.length === 0 ? (
          <p className="text-xs text-muted">{t("stateEditor.scene.noPresentChars")}</p>
        ) : (
          <>
            <div
              role="group"
              aria-label={t("stateEditor.scene.selectCharacter")}
              className="flex flex-wrap gap-1.5"
            >
              {visibleCharIds.map((charId) => {
                const active = charId === activeCharId;
                return (
                  <button
                    key={charId}
                    type="button"
                    aria-pressed={active}
                    data-eink-active={active || undefined}
                    onClick={() => setSelectedCharId(charId)}
                    className={cn(
                      "min-h-8 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors duration-fast ease-ui",
                      active
                        ? "border-accent bg-surface-2 text-fg"
                        : "border-border bg-field text-muted hover:border-border-strong hover:text-fg",
                    )}
                  >
                    {charLabel(charId)}
                  </button>
                );
              })}
            </div>
            {activeCharId ? (
              <div
                key={activeCharId}
                data-testid={`scene-char-${activeCharId}`}
                className="flex flex-col gap-2 pt-1"
              >
                {CHAR_FIELDS.map(({ key, labelKey }) => (
                  <div key={key} className="flex flex-col gap-1">
                    <Label htmlFor={`scene-${activeCharId}-${key}`} className="text-xs text-muted">
                      {t(labelKey)}
                    </Label>
                    <Input
                      id={`scene-${activeCharId}-${key}`}
                      value={(draft.chars[activeCharId] ?? {})[key] ?? ""}
                      onChange={(e) => setCharField(activeCharId, key, e.target.value)}
                      className="h-9 text-xs md:h-9"
                    />
                  </div>
                ))}
              </div>
            ) : null}
          </>
        )}
      </div>

      <div className="flex flex-col gap-2 border-t border-border-subtle pt-3">
        <h4 className="text-xs font-semibold uppercase text-muted">
          {t("stateEditor.scene.itemsTitle")}
        </h4>
        {draft.items.length === 0 ? (
          <p className="text-xs text-muted">{t("stateEditor.scene.itemsEmpty")}</p>
        ) : (
          <ul className="flex flex-col divide-y divide-border-subtle">
            {draft.items.map((item, idx) => (
              <li
                key={`${item}-${idx}`}
                className="flex items-center justify-between gap-2 py-1.5 text-xs"
              >
                <span className="min-w-0 break-words">{item}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0"
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
            className="h-9 min-w-0 flex-1 text-xs md:h-9"
          />
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            className="shrink-0"
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
    </Container>
  );
}
