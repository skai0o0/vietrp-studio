import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { ChipsInput } from "../form/ChipsInput";
import { useFormState } from "../form/FormContext";
import { SelectField, TextAreaField, TextField } from "../form/fields";
import { IconButton } from "../form/IconButton";
import { Section } from "../form/Section";
import { moveItem, removeAt, replaceAt, uniqueSlug } from "../lib/arrays";
import { flattenTree, pathLabel, type Loc } from "./treeOps";
import type { OpeningDraft } from "./worldDraft";

const TENSION_LEVELS = [0, 1, 2, 3, 4] as const; // matches Opening.tension ge=0 le=4 on the server

interface OpeningsSectionProps {
  openings: OpeningDraft[];
  locations: Loc[];
  onChange: (openings: OpeningDraft[]) => void;
}

export function OpeningsSection({ openings, locations, onChange }: OpeningsSectionProps) {
  const { readOnly } = useFormState();
  const locationOptions = flattenTree(locations).map(({ loc }) => ({
    value: loc.id,
    label: pathLabel(locations, loc.id),
  }));

  function add(): void {
    const id = uniqueSlug(
      "opening",
      openings.map((o) => o.id),
    );
    onChange([
      ...openings,
      {
        id,
        title: "",
        message: "",
        time: "",
        location_id: locationOptions[0]?.value ?? "",
        present_ids: [],
        tension: 0,
        player_role: "",
      },
    ]);
  }

  return (
    <Section title={t("library.world.openings")} description={t("library.world.openingsHint")}>
      {openings.length === 0 && readOnly ? (
        <p className="text-sm text-muted">{t("library.list.none")}</p>
      ) : null}
      <ul className="flex flex-col gap-4">
        {openings.map((opening, index) => {
          const name = t("library.world.openingItem", { n: index + 1 });
          const patch = (change: Partial<OpeningDraft>): void =>
            onChange(replaceAt(openings, index, { ...opening, ...change }));
          return (
            <li
              key={opening.id}
              className="flex flex-col gap-3 rounded-md border border-border bg-bg p-3 md:p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-medium">{opening.title.trim() || name}</h3>
                {readOnly ? null : (
                  <div className="flex gap-0.5">
                    <IconButton
                      icon={ArrowUp}
                      label={t("library.list.moveUp", { name })}
                      disabled={index === 0}
                      onClick={() => onChange(moveItem(openings, index, index - 1))}
                    />
                    <IconButton
                      icon={ArrowDown}
                      label={t("library.list.moveDown", { name })}
                      disabled={index === openings.length - 1}
                      onClick={() => onChange(moveItem(openings, index, index + 1))}
                    />
                    <IconButton
                      icon={Trash2}
                      label={t("library.list.remove", { name })}
                      onClick={() => onChange(removeAt(openings, index))}
                    />
                  </div>
                )}
              </div>
              <TextField
                label={t("library.world.openingTitle")}
                path={`openings.${index}.title`}
                value={opening.title}
                onChange={(title) => patch({ title })}
              />
              <TextAreaField
                label={t("library.world.openingMessage")}
                path={`openings.${index}.message`}
                rows={5}
                value={opening.message}
                onChange={(message) => patch({ message })}
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <TextField
                  label={t("library.world.openingTime")}
                  path={`openings.${index}.time`}
                  value={opening.time}
                  onChange={(time) => patch({ time })}
                />
                <SelectField
                  label={t("library.world.openingLocation")}
                  path={`openings.${index}.location_id`}
                  emptyLabel={t("library.world.pickLocation")}
                  value={opening.location_id}
                  options={locationOptions}
                  onChange={(location_id) => patch({ location_id })}
                />
              </div>
              <ChipsInput
                label={t("library.world.openingPresent")}
                path={`openings.${index}.present_ids`}
                hint={t("library.world.openingPresentHint")}
                values={opening.present_ids}
                onChange={(present_ids) => patch({ present_ids })}
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <SelectField
                  label={t("library.world.openingTension")}
                  path={`openings.${index}.tension`}
                  value={String(opening.tension)}
                  options={TENSION_LEVELS.map((n) => ({
                    value: String(n),
                    label: t(`library.world.tension.t${n}`),
                  }))}
                  onChange={(value) => patch({ tension: Number(value) })}
                />
                <TextField
                  label={t("library.world.openingPlayerRole")}
                  path={`openings.${index}.player_role`}
                  hint={t("library.world.openingPlayerRoleHint")}
                  value={opening.player_role}
                  onChange={(player_role) => patch({ player_role })}
                />
              </div>
            </li>
          );
        })}
      </ul>
      {readOnly ? null : (
        <Button type="button" variant="outline" size="sm" className="self-start" onClick={add}>
          <Plus aria-hidden="true" />
          {t("library.world.addOpening")}
        </Button>
      )}
    </Section>
  );
}
