import { t } from "@/i18n";
import { TextAreaField } from "../form/fields";
import { Section } from "../form/Section";
import { StringListEditor } from "../form/StringListEditor";
import type { CardDraft } from "./cardDraft";

interface SectionProps {
  draft: CardDraft;
  patch: (change: Partial<CardDraft>) => void;
}

/** Appearance, personality, backstory, goals. */
export function DescriptionSection({ draft, patch }: SectionProps) {
  return (
    <Section
      title={t("library.character.description")}
      description={t("library.character.descriptionHint")}
    >
      <TextAreaField
        label={t("library.character.appearance")}
        path="appearance"
        value={draft.appearance}
        onChange={(appearance) => patch({ appearance })}
      />
      <TextAreaField
        label={t("library.character.personality")}
        path="personality"
        value={draft.personality}
        onChange={(personality) => patch({ personality })}
      />
      <TextAreaField
        label={t("library.character.backstory")}
        path="backstory"
        value={draft.backstory}
        onChange={(backstory) => patch({ backstory })}
      />
      <TextAreaField
        label={t("library.character.goals")}
        path="goals"
        value={draft.goals}
        onChange={(goals) => patch({ goals })}
      />
    </Section>
  );
}

export function LimitsSection({ draft, patch }: SectionProps) {
  return (
    <Section title={t("library.character.limits")} description={t("library.character.limitsHint")}>
      <StringListEditor
        label={t("library.character.limits")}
        path="limits"
        items={draft.limits}
        addLabel={t("library.character.addLimit")}
        itemLabel={(n) => t("library.character.limitItem", { n })}
        onChange={(limits) => patch({ limits })}
      />
    </Section>
  );
}

export function SpeechSection({ draft, patch }: SectionProps) {
  const { speech } = draft;
  return (
    <Section title={t("library.character.speech")}>
      <TextAreaField
        label={t("library.character.speechStyle")}
        path="speech.style"
        rows={3}
        value={speech.style}
        onChange={(style) => patch({ speech: { ...speech, style } })}
      />
      <StringListEditor
        label={t("library.character.catchphrases")}
        path="speech.catchphrases"
        items={speech.catchphrases}
        addLabel={t("library.character.addCatchphrase")}
        itemLabel={(n) => t("library.character.catchphraseItem", { n })}
        onChange={(catchphrases) => patch({ speech: { ...speech, catchphrases } })}
      />
      <StringListEditor
        label={t("library.character.examples")}
        path="speech.examples"
        hint={t("library.character.examplesHint")}
        multiline
        items={speech.examples}
        addLabel={t("library.character.addExample")}
        itemLabel={(n) => t("library.character.exampleItem", { n })}
        onChange={(examples) => patch({ speech: { ...speech, examples } })}
      />
    </Section>
  );
}

export function GreetingsSection({ draft, patch }: SectionProps) {
  return (
    <Section
      title={t("library.character.greetings")}
      description={t("library.character.greetingsHint")}
    >
      <StringListEditor
        label={t("library.character.greetings")}
        path="greetings"
        multiline
        rows={5}
        items={draft.greetings}
        addLabel={t("library.character.addGreeting")}
        itemLabel={(n) => t("library.character.greetingItem", { n })}
        onChange={(greetings) => patch({ greetings })}
      />
    </Section>
  );
}
