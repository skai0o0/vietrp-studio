import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { t } from "@/i18n";
import type { Persona, PersonaOut } from "@/types/library";
import { AvatarField } from "../form/AvatarField";
import { EditorActions } from "../form/EditorActions";
import { EditorHeader, LoadStatus, SaveErrorBanner } from "../form/EditorChrome";
import { NumberField, TextAreaField, TextField } from "../form/fields";
import { FormStateProvider } from "../form/FormContext";
import { ChipsInput } from "../form/ChipsInput";
import { Section } from "../form/Section";
import {
  useCreatePersona,
  useDeletePersona,
  usePersona,
  useSetPersonaAvatar,
  useUpdatePersona,
} from "../hooks";
import { parseApiError } from "../lib/errors";
import { NEW_ID } from "../list/badges";

const BACK = "/library/personas";

interface PersonaDraft {
  name: string;
  aliases: string[];
  age: number | null;
  gender: string;
  pronouns: string;
  appearance: string;
  personality: string;
  background: string;
  notes: string;
}

function emptyDraft(): PersonaDraft {
  return {
    name: "",
    aliases: [],
    age: null,
    gender: "",
    pronouns: "",
    appearance: "",
    personality: "",
    background: "",
    notes: "",
  };
}

function toDraft(persona: Persona): PersonaDraft {
  return {
    name: persona.name,
    aliases: [...(persona.aliases ?? [])],
    age: persona.age ?? null,
    gender: persona.gender ?? "",
    pronouns: persona.pronouns ?? "",
    appearance: persona.appearance ?? "",
    personality: persona.personality ?? "",
    background: persona.background ?? "",
    notes: persona.notes ?? "",
  };
}

function toPersona(draft: PersonaDraft): Persona {
  return { format: "vietrp-persona", spec_version: "1.0", ...draft };
}

export function PersonaEditor({ id }: { id: string }) {
  const isNew = id === NEW_ID;
  const query = usePersona(isNew ? undefined : id);
  if (!isNew && !query.data) {
    return (
      <LoadStatus
        isPending={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        backTo={BACK}
        backLabel={t("library.persona.back")}
      />
    );
  }
  return <PersonaForm key={id} persona={query.data ?? null} />;
}

function PersonaForm({ persona }: { persona: PersonaOut | null }) {
  const navigate = useNavigate();
  const isNew = persona === null;
  const [draft, setDraft] = useState<PersonaDraft>(() =>
    persona ? toDraft(persona.data) : emptyDraft(),
  );
  const [saveError, setSaveError] = useState<unknown>(null);

  const create = useCreatePersona();
  const update = useUpdatePersona(persona?.id ?? "");
  const remove = useDeletePersona();
  const avatar = useSetPersonaAvatar(persona?.id ?? "");

  const parsed = useMemo(() => (saveError ? parseApiError(saveError) : null), [saveError]);
  const formState = useMemo(
    () => ({ readOnly: false, errors: parsed?.fields ?? {}, warnings: {} }),
    [parsed],
  );

  function patch(change: Partial<PersonaDraft>): void {
    setDraft((current) => ({ ...current, ...change }));
    setSaveError(null);
  }

  function save(): void {
    const data = toPersona(draft);
    const options = { onError: (error: unknown) => setSaveError(error) };
    if (persona) {
      update.mutate(data, {
        ...options,
        onSuccess: () => toast.success(t("library.actions.saved")),
      });
    } else {
      create.mutate(data, {
        ...options,
        onSuccess: ({ persona: created }) => {
          toast.success(t("library.actions.saved"));
          void navigate(`${BACK}/${created.id}`, { replace: true });
        },
      });
    }
  }

  function deletePersona(): void {
    if (!persona) return;
    remove.mutate(persona.id, {
      onSuccess: () => {
        toast.success(t("library.actions.deleted"));
        void navigate(BACK);
      },
    });
  }

  const title = draft.name.trim() || t("library.persona.newTitle");

  return (
    <FormStateProvider value={formState}>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 pb-24 md:px-8">
        <EditorHeader
          title={title}
          backTo={BACK}
          backLabel={t("library.persona.back")}
          actions={
            <EditorActions
              readOnly={false}
              isNew={isNew}
              saving={create.isPending || update.isPending}
              onSave={save}
              onDelete={deletePersona}
              deleting={remove.isPending}
              deleteError={remove.error}
              deleteTitle={t("library.persona.deleteTitle", { name: title })}
              deleteDescription={t("library.persona.deleteDescription")}
            />
          }
        />
        <SaveErrorBanner error={saveError} />
        <Section title={t("library.persona.basics")} description={t("library.persona.intro")}>
          {persona ? (
            <AvatarField
              label={t("library.persona.avatar")}
              url={persona.avatar_url}
              pending={avatar.isPending}
              error={avatar.error}
              onChange={(file) => avatar.mutate(file)}
            />
          ) : (
            <p className="text-xs text-muted">{t("library.image.saveFirst")}</p>
          )}
          <div className="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <TextField
              label={t("library.persona.name")}
              path="name"
              value={draft.name}
              onChange={(name) => patch({ name })}
            />
            <NumberField
              label={t("library.persona.age")}
              path="age"
              value={draft.age}
              onChange={(age) => patch({ age })}
            />
          </div>
          <ChipsInput
            label={t("library.persona.aliases")}
            path="aliases"
            values={draft.aliases}
            onChange={(aliases) => patch({ aliases })}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label={t("library.persona.gender")}
              path="gender"
              value={draft.gender}
              onChange={(gender) => patch({ gender })}
            />
            <TextField
              label={t("library.persona.pronouns")}
              path="pronouns"
              hint={t("library.persona.pronounsHint")}
              value={draft.pronouns}
              onChange={(pronouns) => patch({ pronouns })}
            />
          </div>
        </Section>
        <Section title={t("library.persona.details")}>
          <TextAreaField
            label={t("library.persona.appearance")}
            path="appearance"
            value={draft.appearance}
            onChange={(appearance) => patch({ appearance })}
          />
          <TextAreaField
            label={t("library.persona.personality")}
            path="personality"
            value={draft.personality}
            onChange={(personality) => patch({ personality })}
          />
          <TextAreaField
            label={t("library.persona.background")}
            path="background"
            value={draft.background}
            onChange={(background) => patch({ background })}
          />
          <TextAreaField
            label={t("library.persona.notes")}
            path="notes"
            value={draft.notes}
            onChange={(notes) => patch({ notes })}
          />
        </Section>
      </div>
    </FormStateProvider>
  );
}
