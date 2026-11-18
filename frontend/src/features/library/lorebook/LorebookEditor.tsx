import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ExportMenu } from "@/features/io";
import { t } from "@/i18n";
import type { LorebookOut, Visibility } from "@/types/library";
import { EditorActions } from "../form/EditorActions";
import { EditorHeader, LoadStatus, SaveErrorBanner } from "../form/EditorChrome";
import { NumberField, TextAreaField, TextField, ToggleField } from "../form/fields";
import { FormStateProvider } from "../form/FormContext";
import { Section } from "../form/Section";
import {
  useCreateLorebook,
  useDeleteLorebook,
  useDuplicateLorebook,
  useLorebook,
  useUpdateLorebook,
} from "../hooks";
import { libraryErrorMessage, parseApiError } from "../lib/errors";
import { NEW_ID, VisibilityBadge } from "../list/badges";
import { EntriesTable } from "./EntriesTable";
import {
  draftToLorebook,
  emptyLorebookDraft,
  lorebookToDraft,
  type LorebookDraft,
} from "./lorebookDraft";

const BACK = "/library/lorebooks";

export function LorebookEditor({ id }: { id: string }) {
  const isNew = id === NEW_ID;
  const query = useLorebook(isNew ? undefined : id);
  if (!isNew && !query.data) {
    return (
      <LoadStatus
        isPending={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        backTo={BACK}
        backLabel={t("library.lorebook.back")}
      />
    );
  }
  return <LorebookForm key={id} book={query.data ?? null} />;
}

function LorebookForm({ book }: { book: LorebookOut | null }) {
  const navigate = useNavigate();
  const isNew = book === null;
  const readOnly = book !== null && !book.is_owner;

  const [draft, setDraft] = useState<LorebookDraft>(() =>
    book ? lorebookToDraft(book.data) : emptyLorebookDraft(),
  );
  const [visibility, setVisibility] = useState<Visibility>(book?.visibility ?? "private");
  const [saveError, setSaveError] = useState<unknown>(null);

  const create = useCreateLorebook();
  const update = useUpdateLorebook(book?.id ?? "");
  const remove = useDeleteLorebook();
  const duplicate = useDuplicateLorebook();

  const parsed = useMemo(() => (saveError ? parseApiError(saveError) : null), [saveError]);
  const formState = useMemo(
    () => ({ readOnly, errors: parsed?.fields ?? {}, warnings: {} }),
    [readOnly, parsed],
  );

  function patch(change: Partial<LorebookDraft>): void {
    setDraft((current) => ({ ...current, ...change }));
    setSaveError(null);
  }

  function save(): void {
    const payload = { data: draftToLorebook(draft), visibility };
    const options = { onError: (error: unknown) => setSaveError(error) };
    if (book) {
      update.mutate(payload, {
        ...options,
        onSuccess: () => toast.success(t("library.actions.saved")),
      });
    } else {
      create.mutate(payload, {
        ...options,
        onSuccess: ({ lorebook }) => {
          toast.success(t("library.actions.saved"));
          void navigate(`${BACK}/${lorebook.id}`, { replace: true });
        },
      });
    }
  }

  function addToLibrary(): void {
    if (!book) return;
    duplicate.mutate(book.id, {
      onSuccess: ({ lorebook }) => {
        toast.success(t("library.actions.duplicated"));
        void navigate(`${BACK}/${lorebook.id}`);
      },
      onError: (error) => toast.error(libraryErrorMessage(parseApiError(error).code)),
    });
  }

  function deleteBook(): void {
    if (!book) return;
    remove.mutate(book.id, {
      onSuccess: () => {
        toast.success(t("library.actions.deleted"));
        void navigate(BACK);
      },
    });
  }

  const title = draft.name.trim() || t("library.lorebook.newTitle");

  return (
    <FormStateProvider value={formState}>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 pb-24 md:px-8">
        <EditorHeader
          title={title}
          backTo={BACK}
          backLabel={t("library.lorebook.back")}
          badges={book ? <VisibilityBadge visibility={visibility} /> : null}
          actions={
            <EditorActions
              readOnly={readOnly}
              isNew={isNew}
              saving={create.isPending || update.isPending}
              onSave={save}
              onDuplicate={book ? addToLibrary : undefined}
              duplicating={duplicate.isPending}
              onDelete={deleteBook}
              deleting={remove.isPending}
              deleteError={remove.error}
              deleteTitle={t("library.lorebook.deleteTitle", { name: title })}
              deleteDescription={t("library.lorebook.deleteDescription")}
              exportMenu={book ? <ExportMenu kind="lorebook" id={book.id} /> : null}
            />
          }
        />
        {readOnly && book ? (
          <p className="rounded-lg border border-border bg-surface p-3 text-sm text-muted">
            {t("library.readOnly", { author: book.author })}
          </p>
        ) : null}
        <SaveErrorBanner error={saveError} />
        <Section title={t("library.lorebook.settings")}>
          <TextField
            label={t("library.lorebook.name")}
            path="name"
            value={draft.name}
            onChange={(name) => patch({ name })}
          />
          <TextAreaField
            label={t("library.lorebook.description")}
            path="description"
            rows={3}
            value={draft.description}
            onChange={(description) => patch({ description })}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label={t("library.lorebook.scanDepth")}
              path="scan_depth"
              hint={t("library.lorebook.scanDepthHint")}
              value={draft.scan_depth}
              onChange={(scan_depth) => patch({ scan_depth })}
            />
            <NumberField
              label={t("library.lorebook.tokenBudget")}
              path="token_budget"
              hint={t("library.lorebook.tokenBudgetHint")}
              value={draft.token_budget}
              onChange={(token_budget) => patch({ token_budget })}
            />
          </div>
          <ToggleField
            label={t("library.fields.public")}
            hint={t("library.fields.publicHint")}
            checked={visibility === "public"}
            onChange={(checked) => {
              setVisibility(checked ? "public" : "private");
              setSaveError(null);
            }}
          />
        </Section>
        <Section
          title={t("library.lorebook.entries")}
          description={t("library.lorebook.entriesHint")}
        >
          <EntriesTable entries={draft.entries} onChange={(entries) => patch({ entries })} />
        </Section>
      </div>
    </FormStateProvider>
  );
}
