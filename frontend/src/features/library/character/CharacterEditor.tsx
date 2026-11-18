import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { CardJudgePanel } from "@/features/create";
import { StartChatButton } from "@/features/chat/newChat/StartChatButton";
import { ExportMenu } from "@/features/io";
import { t } from "@/i18n";
import { AvatarField } from "../form/AvatarField";
import { EditorActions } from "../form/EditorActions";
import { EditorHeader, LoadStatus, SaveErrorBanner } from "../form/EditorChrome";
import { FormStateProvider } from "../form/FormContext";
import {
  useCharacter,
  useCreateCharacter,
  useDeleteCharacter,
  useDuplicateCharacter,
  useJudgeCharacter,
  useSetCharacterAvatar,
  useUpdateCharacter,
} from "../hooks";
import { libraryErrorMessage, parseApiError } from "../lib/errors";
import { groupWarnings } from "../lib/warnings";
import { NEW_ID, VisibilityBadge } from "../list/badges";
import type { CharacterOut, Visibility } from "@/types/library";
import { BasicsSection } from "./BasicsSection";
import { BondsSection, ExtrasSection, LorebooksSection } from "./BondsAndExtrasSections";
import { cardToDraft, draftToCard, emptyCardDraft, type CardDraft } from "./cardDraft";
import {
  DescriptionSection,
  GreetingsSection,
  LimitsSection,
  SpeechSection,
} from "./ProfileSections";
import { SecretsSection } from "./SecretsSection";

const BACK = "/library/characters";

export function CharacterEditor({ id }: { id: string }) {
  const isNew = id === NEW_ID;
  const query = useCharacter(isNew ? undefined : id);
  if (!isNew && !query.data) {
    return (
      <LoadStatus
        isPending={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        backTo={BACK}
        backLabel={t("library.character.back")}
      />
    );
  }
  return <CharacterForm key={id} character={query.data ?? null} />;
}

function CharacterForm({ character }: { character: CharacterOut | null }) {
  const navigate = useNavigate();
  const isNew = character === null;
  const readOnly = character !== null && !character.is_owner;

  const [draft, setDraft] = useState<CardDraft>(() =>
    character ? cardToDraft(character.data) : emptyCardDraft(),
  );
  const [visibility, setVisibility] = useState<Visibility>(character?.visibility ?? "private");
  const [saveError, setSaveError] = useState<unknown>(null);

  const create = useCreateCharacter();
  const update = useUpdateCharacter(character?.id ?? "");
  const remove = useDeleteCharacter();
  const duplicate = useDuplicateCharacter();
  const avatar = useSetCharacterAvatar(character?.id ?? "");
  const judge = useJudgeCharacter(character?.id ?? "");

  const parsed = useMemo(() => (saveError ? parseApiError(saveError) : null), [saveError]);
  const warnings = useMemo(() => groupWarnings(character?.warnings ?? []), [character?.warnings]);
  const formState = useMemo(
    () => ({ readOnly, errors: parsed?.fields ?? {}, warnings }),
    [readOnly, parsed, warnings],
  );

  function patch(change: Partial<CardDraft>): void {
    setDraft((current) => ({ ...current, ...change }));
    setSaveError(null);
  }

  function save(): void {
    const payload = { data: draftToCard(draft), visibility };
    const options = { onError: (error: unknown) => setSaveError(error) };
    if (character) {
      update.mutate(payload, {
        ...options,
        onSuccess: () => toast.success(t("library.actions.saved")),
      });
    } else {
      create.mutate(payload, {
        ...options,
        onSuccess: ({ character: created }) => {
          toast.success(t("library.actions.saved"));
          void navigate(`/characters/${created.id}`, { replace: true });
        },
      });
    }
  }

  function addToLibrary(): void {
    if (!character) return;
    duplicate.mutate(character.id, {
      onSuccess: ({ character: copy }) => {
        toast.success(t("library.actions.duplicated"));
        void navigate(`/characters/${copy.id}`);
      },
      onError: (error) => toast.error(libraryErrorMessage(parseApiError(error).code)),
    });
  }

  function deleteCharacter(): void {
    if (!character) return;
    remove.mutate(character.id, {
      onSuccess: () => {
        toast.success(t("library.actions.deleted"));
        void navigate(BACK);
      },
    });
  }

  function runJudge(): void {
    if (!character) return;
    judge.mutate(undefined, {
      onSuccess: () => toast.success(t("library.judge.done")),
    });
  }

  const visibilityError =
    parsed?.code === "nsfw_minor_public" ? libraryErrorMessage(parsed.code) : undefined;
  const title = draft.name.trim() || t("library.character.newTitle");

  return (
    <FormStateProvider value={formState}>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 pb-24 md:px-8">
        <EditorHeader
          title={title}
          backTo={BACK}
          backLabel={t("library.character.back")}
          badges={character ? <VisibilityBadge visibility={visibility} /> : null}
          actions={
            <>
              {character ? <StartChatButton characterId={character.id} /> : null}
              <EditorActions
                readOnly={readOnly}
                isNew={isNew}
                saving={create.isPending || update.isPending}
                onSave={save}
                onDuplicate={character ? addToLibrary : undefined}
                duplicating={duplicate.isPending}
                onDelete={deleteCharacter}
                deleting={remove.isPending}
                deleteError={remove.error}
                deleteTitle={t("library.character.deleteTitle", { name: title })}
                deleteDescription={t("library.character.deleteDescription")}
                exportMenu={character ? <ExportMenu kind="character" id={character.id} /> : null}
              />
            </>
          }
        />
        {readOnly && character ? (
          <p className="rounded-lg border border-border bg-surface p-3 text-sm text-muted">
            {t("library.readOnly", { author: character.author })}
          </p>
        ) : null}
        {draft.age === null && !readOnly ? (
          <p
            role="status"
            data-testid="needs-age"
            className="rounded-lg border-2 border-accent-2 bg-surface p-3 text-sm"
          >
            {t("library.character.needsAgeNotice")}
          </p>
        ) : null}
        <SaveErrorBanner error={saveError} />
        <BasicsSection
          draft={draft}
          patch={patch}
          visibility={visibility}
          onVisibility={(value) => {
            setVisibility(value);
            setSaveError(null);
          }}
          visibilityError={visibilityError}
          avatar={
            character ? (
              <AvatarField
                label={t("library.character.avatar")}
                url={character.avatar_url}
                pending={avatar.isPending}
                error={avatar.error}
                onChange={(file) => avatar.mutate(file)}
              />
            ) : (
              <p className="text-xs text-muted">{t("library.image.saveFirst")}</p>
            )
          }
        />
        {character && (!readOnly || character.judge_score) ? (
          <CardJudgePanel
            result={character.judge_score ?? null}
            onJudge={!readOnly ? runJudge : undefined}
            pending={judge.isPending}
            error={judge.error}
            hintNote={!readOnly ? t("library.judge.savedHint") : undefined}
          />
        ) : null}
        <DescriptionSection draft={draft} patch={patch} />
        <LimitsSection draft={draft} patch={patch} />
        <SecretsSection secrets={draft.secrets} onChange={(secrets) => patch({ secrets })} />
        <SpeechSection draft={draft} patch={patch} />
        <BondsSection draft={draft} patch={patch} />
        <GreetingsSection draft={draft} patch={patch} />
        <LorebooksSection draft={draft} patch={patch} />
        <ExtrasSection draft={draft} patch={patch} />
      </div>
    </FormStateProvider>
  );
}
