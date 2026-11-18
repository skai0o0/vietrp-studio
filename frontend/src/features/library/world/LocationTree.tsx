import { GripVertical, Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { ConfirmDialog } from "../form/ConfirmDialog";
import { useFormState } from "../form/FormContext";
import { LocationDetail } from "./LocationDetail";
import {
  addChild,
  addRoot,
  addSibling,
  canReparent,
  deleteSubtree,
  flattenTree,
  levelsBelow,
  reparent,
  subtreeIds,
  type Level,
  type Loc,
} from "./treeOps";

interface LocationTreeProps {
  locations: Loc[];
  /** `removed` lists the ids dropped by a subtree delete, so callers can fix references. */
  onChange: (locations: Loc[], removed?: ReadonlySet<string>) => void;
  /** Number of openings that start in each location id (shown in the delete confirmation). */
  openingCountFor: (ids: ReadonlySet<string>) => number;
}

const DEFAULT_ROOT_LEVEL: Level = "country";

export function LocationTree({ locations, onChange, openingCountFor }: LocationTreeProps) {
  const { readOnly } = useFormState();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rootLevel, setRootLevel] = useState<Level>(DEFAULT_ROOT_LEVEL);
  const [dragId, setDragId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const rows = flattenTree(locations);
  const selected = locations.find((l) => l.id === selectedId) ?? null;
  const newName = t("library.world.newLocation");

  function apply(result: { locations: Loc[]; id: string } | null): void {
    if (!result) {
      setNotice(t("library.world.cannotAddChild"));
      return;
    }
    setNotice(null);
    onChange(result.locations);
    setSelectedId(result.id);
  }

  function drop(targetId: string): void {
    const moving = dragId;
    setDragId(null);
    if (!moving || moving === targetId) return;
    if (!canReparent(locations, moving, targetId)) {
      setNotice(t("library.world.dropNotAllowed"));
      return;
    }
    setNotice(null);
    onChange(reparent(locations, moving, targetId));
  }

  function doDelete(): void {
    if (!confirmDelete) return;
    const { locations: next, removed } = deleteSubtree(locations, confirmDelete);
    onChange(next, removed);
    setConfirmDelete(null);
    setSelectedId(null);
  }

  const removing = confirmDelete ? subtreeIds(locations, confirmDelete) : new Set<string>();
  const affectedOpenings = confirmDelete ? openingCountFor(removing) : 0;
  const deleteName = locations.find((l) => l.id === confirmDelete)?.name ?? "";

  return (
    <div className="flex flex-col gap-4">
      {readOnly ? null : (
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="root-level">{t("library.world.rootLevel")}</Label>
            <select
              id="root-level"
              value={rootLevel}
              className="h-10 rounded-md border border-border bg-surface px-3 text-sm text-fg"
              onChange={(event) => setRootLevel(event.target.value as Level)}
            >
              {levelsBelow(null).map((level) => (
                <option key={level} value={level}>
                  {t(`library.world.levels.${level}`)}
                </option>
              ))}
            </select>
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={() => apply(addRoot(locations, rootLevel, newName))}
          >
            <Plus aria-hidden="true" />
            {t("library.world.addRoot")}
          </Button>
        </div>
      )}
      {notice ? (
        <p role="status" className="text-sm text-muted">
          {notice}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("library.world.noLocations")}</p>
      ) : (
        <ul aria-label={t("library.world.treeLabel")} className="flex flex-col gap-1">
          {rows.map(({ loc, depth }) => {
            const active = loc.id === selectedId;
            return (
              <li
                key={loc.id}
                style={{ paddingLeft: `${depth * 1.25}rem` }}
                draggable={!readOnly}
                onDragStart={(event) => {
                  setDragId(loc.id);
                  event.dataTransfer.setData("text/plain", loc.id);
                  event.dataTransfer.effectAllowed = "move";
                }}
                onDragOver={(event) => {
                  if (dragId) event.preventDefault();
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  drop(loc.id);
                }}
                onDragEnd={() => setDragId(null)}
              >
                <div
                  className={cn(
                    "flex items-center gap-1 rounded-md border border-transparent",
                    active && "border-accent bg-surface-2",
                    dragId === loc.id && "opacity-50",
                  )}
                >
                  {readOnly ? null : (
                    <GripVertical className="size-4 shrink-0 text-muted" aria-hidden="true" />
                  )}
                  <button
                    type="button"
                    aria-current={active ? "true" : undefined}
                    className="flex min-h-10 min-w-0 flex-1 items-center gap-2 rounded-md px-2 text-left text-sm hover:bg-surface-2"
                    onClick={() => setSelectedId(loc.id)}
                  >
                    <span className="min-w-0 flex-1 truncate font-medium">
                      {loc.name || loc.id}
                    </span>
                    <span className="shrink-0 text-xs text-muted">
                      {t(`library.world.levels.${loc.level}`)}
                    </span>
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {selected ? (
        <LocationDetail
          key={selected.id}
          locations={locations}
          location={selected}
          onChange={onChange}
          onAddChild={() => apply(addChild(locations, selected.id, newName))}
          onAddSibling={() => apply(addSibling(locations, selected.id, newName))}
          onDelete={() => setConfirmDelete(selected.id)}
        />
      ) : rows.length > 0 ? (
        <p className="text-sm text-muted">{t("library.world.selectHint")}</p>
      ) : null}
      {confirmDelete ? (
        <ConfirmDialog
          title={t("library.world.deleteTitle", { name: deleteName })}
          description={t("library.world.deleteDescription", {
            count: removing.size,
            openings: affectedOpenings,
          })}
          confirmLabel={t("library.world.deleteConfirm")}
          onConfirm={doDelete}
          onClose={() => setConfirmDelete(null)}
        />
      ) : null}
    </div>
  );
}
