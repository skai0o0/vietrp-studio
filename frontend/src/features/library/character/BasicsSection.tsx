import { t } from "@/i18n";
import type { Visibility } from "@/types/library";
import { ChipsInput } from "../form/ChipsInput";
import { NumberField, TextField, ToggleField } from "../form/fields";
import { Section } from "../form/Section";
import type { CardDraft } from "./cardDraft";

interface BasicsSectionProps {
  draft: CardDraft;
  patch: (change: Partial<CardDraft>) => void;
  visibility: Visibility;
  onVisibility: (value: Visibility) => void;
  /** Message to show next to the visibility toggle (e.g. nsfw_minor_public). */
  visibilityError?: string | undefined;
  avatar: React.ReactNode;
}

const TAGLINE_MAX = 140; // matches VietrpCard.tagline max_length on the server

export function BasicsSection(props: BasicsSectionProps) {
  const { draft, patch, visibility, onVisibility, visibilityError, avatar } = props;
  return (
    <Section title={t("library.character.basics")}>
      {avatar}
      <div className="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <TextField
          label={t("library.character.name")}
          path="name"
          value={draft.name}
          onChange={(name) => patch({ name })}
        />
        <NumberField
          label={t("library.character.age")}
          path="age"
          hint={t("library.character.ageHint")}
          value={draft.age}
          onChange={(age) => patch({ age })}
        />
      </div>
      <ChipsInput
        label={t("library.character.aliases")}
        path="aliases"
        hint={t("library.character.aliasesHint")}
        values={draft.aliases}
        onChange={(aliases) => patch({ aliases })}
      />
      <TextField
        label={t("library.character.tagline")}
        path="tagline"
        counterMax={TAGLINE_MAX}
        value={draft.tagline}
        onChange={(tagline) => patch({ tagline })}
      />
      <ChipsInput
        label={t("library.fields.tags")}
        path="tags"
        lowercase
        hint={t("library.fields.tagsHint")}
        values={draft.tags}
        onChange={(tags) => patch({ tags })}
      />
      <ToggleField
        label={t("library.fields.public")}
        hint={t("library.fields.publicHint")}
        checked={visibility === "public"}
        onChange={(checked) => onVisibility(checked ? "public" : "private")}
      />
      {visibilityError ? (
        <p role="alert" data-testid="visibility-error" className="text-sm text-danger">
          {visibilityError}
        </p>
      ) : null}
    </Section>
  );
}
