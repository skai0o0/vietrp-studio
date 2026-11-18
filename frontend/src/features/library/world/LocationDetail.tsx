import { ArrowDown, ArrowUp, CornerDownRight, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { useFormState } from "../form/FormContext";
import { SelectField, TextAreaField, TextField } from "../form/fields";
import { IconButton } from "../form/IconButton";
import {
  allowedLevels,
  canMoveSibling,
  levelsBelow,
  moveSibling,
  parentChoices,
  pathLabel,
  reparent,
  updateLocation,
  type Level,
  type Loc,
} from "./treeOps";

interface LocationDetailProps {
  locations: Loc[];
  location: Loc;
  onChange: (locations: Loc[]) => void;
  onAddChild: () => void;
  onAddSibling: () => void;
  onDelete: () => void;
}

/** Edit panel for the selected location: rename, level, parent, move up/down, add, delete. */
export function LocationDetail(props: LocationDetailProps) {
  const { locations, location, onChange, onAddChild, onAddSibling, onDelete } = props;
  const { readOnly } = useFormState();
  const index = locations.findIndex((l) => l.id === location.id);
  const levels = allowedLevels(locations, location.id);
  const canAddChild = levelsBelow(location.level).length > 0;

  const parentOptions = parentChoices(locations, location.id)
    .filter((p): p is Loc => p !== null)
    .map((p) => ({ value: p.id, label: pathLabel(locations, p.id) }));

  function patch(change: Partial<Loc>): void {
    onChange(updateLocation(locations, location.id, change));
  }

  return (
    <section
      aria-label={t("library.world.locationPanel", { name: location.name || location.id })}
      className="flex flex-col gap-4 rounded-md border border-border bg-bg p-3 md:p-4"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label={t("library.world.locationName")}
          path={`locations.${index}.name`}
          value={location.name}
          onChange={(name) => patch({ name })}
        />
        <SelectField
          label={t("library.world.locationLevel")}
          path={`locations.${index}.level`}
          hint={t("library.world.levelHint")}
          value={location.level}
          options={levels.map((level) => ({
            value: level,
            label: t(`library.world.levels.${level}`),
          }))}
          onChange={(level) => patch({ level: level as Level })}
        />
      </div>
      <SelectField
        label={t("library.world.locationParent")}
        path={`locations.${index}.parent_id`}
        value={location.parent_id ?? ""}
        emptyLabel={t("library.world.parentRoot")}
        options={parentOptions}
        onChange={(value) =>
          onChange(reparent(locations, location.id, value === "" ? null : value))
        }
      />
      <TextAreaField
        label={t("library.world.locationDescription")}
        path={`locations.${index}.description`}
        altPath={`locations.${location.id}.description`}
        rows={3}
        value={location.description ?? ""}
        onChange={(description) => patch({ description })}
      />
      {readOnly ? null : (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!canAddChild}
            onClick={onAddChild}
          >
            <CornerDownRight aria-hidden="true" />
            {t("library.world.addChild")}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onAddSibling}>
            <Plus aria-hidden="true" />
            {t("library.world.addSibling")}
          </Button>
          <IconButton
            icon={ArrowUp}
            label={t("library.world.moveUp")}
            variant="outline"
            disabled={!canMoveSibling(locations, location.id, -1)}
            onClick={() => onChange(moveSibling(locations, location.id, -1))}
          />
          <IconButton
            icon={ArrowDown}
            label={t("library.world.moveDown")}
            variant="outline"
            disabled={!canMoveSibling(locations, location.id, 1)}
            onClick={() => onChange(moveSibling(locations, location.id, 1))}
          />
          <Button type="button" variant="outline" size="sm" onClick={onDelete}>
            <Trash2 aria-hidden="true" />
            {t("library.world.deleteLocation")}
          </Button>
        </div>
      )}
    </section>
  );
}
