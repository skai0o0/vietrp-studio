import { t } from "@/i18n";
import { TextField } from "../form/fields";
import { KeyValueEditor } from "../form/KeyValueEditor";
import { LorebookPicker } from "../form/LorebookPicker";
import { Section } from "../form/Section";
import type { CardDraft } from "./cardDraft";

interface SectionProps {
  draft: CardDraft;
  patch: (change: Partial<CardDraft>) => void;
}

/** Addressing and relationships. Empty values are filled by the bond agents in chat. */
export function BondsSection({ draft, patch }: SectionProps) {
  const { addressing, relationships } = draft;
  return (
    <Section title={t("library.character.bonds")} description={t("library.character.bondsNote")}>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label={t("library.character.addressingDefault")}
          path="addressing.default"
          value={addressing.default}
          onChange={(value) => patch({ addressing: { ...addressing, default: value } })}
        />
        <TextField
          label={t("library.character.addressingUser")}
          path="addressing.user"
          value={addressing.user}
          onChange={(user) => patch({ addressing: { ...addressing, user } })}
        />
      </div>
      <KeyValueEditor
        label={t("library.character.addressingByCharacter")}
        path="addressing.by_character"
        keyLabel={t("library.character.characterId")}
        valueLabel={t("library.character.addressingValue")}
        addLabel={t("library.character.addBond")}
        value={addressing.by_character}
        onChange={(by_character) => patch({ addressing: { ...addressing, by_character } })}
      />
      <TextField
        label={t("library.character.relationshipUser")}
        path="relationships.user"
        value={relationships.user}
        onChange={(user) => patch({ relationships: { ...relationships, user } })}
      />
      <KeyValueEditor
        label={t("library.character.relationshipByCharacter")}
        path="relationships.by_character"
        keyLabel={t("library.character.characterId")}
        valueLabel={t("library.character.relationshipValue")}
        addLabel={t("library.character.addBond")}
        value={relationships.by_character}
        onChange={(by_character) => patch({ relationships: { ...relationships, by_character } })}
      />
    </Section>
  );
}

export function LorebooksSection({ draft, patch }: SectionProps) {
  return (
    <Section title={t("library.lorebooks.title")} description={t("library.lorebooks.cardHint")}>
      <LorebookPicker
        selected={draft.lorebook_ids}
        onChange={(lorebook_ids) => patch({ lorebook_ids })}
      />
    </Section>
  );
}

export function ExtrasSection({ draft, patch }: SectionProps) {
  return (
    <Section title={t("library.character.extras")} description={t("library.character.extrasHint")}>
      <KeyValueEditor
        label={t("library.character.extras")}
        path="extras"
        keyLabel={t("library.character.extraKey")}
        valueLabel={t("library.character.extraValue")}
        addLabel={t("library.character.addExtra")}
        value={draft.extras}
        onChange={(extras) => patch({ extras })}
      />
    </Section>
  );
}
