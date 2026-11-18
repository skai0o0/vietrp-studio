import { MessageCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { buttonVariants } from "@/components/ui/button";
import { CardJudgePanel } from "@/features/create";
import { ExportMenu } from "@/features/io";
import { t } from "@/i18n";
import type { Visibility, WorldOut } from "@/types/library";
import { ChipsInput } from "../form/ChipsInput";
import { AvatarField } from "../form/AvatarField";
import { EditorActions } from "../form/EditorActions";
import { EditorHeader, LoadStatus, SaveErrorBanner } from "../form/EditorChrome";
import { TextAreaField, TextField, ToggleField } from "../form/fields";
import { FormStateProvider } from "../form/FormContext";
import { LorebookPicker } from "../form/LorebookPicker";
import { Section } from "../form/Section";
import {
  useCreateWorld,
  useDeleteWorld,
  useDuplicateWorld,
  useJudgeWorld,
  useSetWorldCover,
  useUpdateWorld,
  useWorld,
} from "../hooks";
import { libraryErrorMessage, parseApiError } from "../lib/errors";
import { groupWarnings } from "../lib/warnings";
import { NEW_ID, VisibilityBadge } from "../list/badges";
import { LocationTree } from "./LocationTree";
import { OpeningsSection } from "./OpeningsSection";
import { draftToWorld, emptyWorldDraft, worldToDraft, type WorldDraft } from "./worldDraft";

const BACK = "/library/worlds";

export function WorldEditor({ id }: { id: string }) {
  const isNew = id === NEW_ID;
  const query = useWorld(isNew ? undefined : id);
  if (!isNew && !query.data) {
    return (
      <LoadStatus
        isPending={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        backTo={BACK}
        backLabel={t("library.world.back")}
      />
    );
  }
  return <WorldForm key={id} world={query.data ?? null} />;
}

function WorldForm({ world }: { world: WorldOut | null }) {
  const navigate = useNavigate();
  const isNew = world === null;
  const readOnly = world !== null && !world.is_owner;

  const [draft, setDraft] = useState<WorldDraft>(() =>
    world ? worldToDraft(world.data) : emptyWorldDraft(),
  );
  const [visibility, setVisibility] = useState<Visibility>(world?.visibility ?? "private");
  const [saveError, setSaveError] = useState<unknown>(null);

  const create = useCreateWorld();
  const update = useUpdateWorld(world?.id ?? "");
  const remove = useDeleteWorld();
  const duplicate = useDuplicateWorld();
  const cover = useSetWorldCover(world?.id ?? "");
  const judge = useJudgeWorld(world?.id ?? "");

  const parsed = useMemo(() => (saveError ? parseApiError(saveError) : null), [saveError]);
  const warnings = useMemo(() => groupWarnings(world?.warnings ?? []), [world?.warnings]);
  const formState = useMemo(
    () => ({ readOnly, errors: parsed?.fields ?? {}, warnings }),
    [readOnly, parsed, warnings],
  );

  function patch(change: Partial<WorldDraft>): void {
    setDraft((current) => ({ ...current, ...change }));
    setSaveError(null);
  }

  /** A removed location leaves its openings without a start; the user must pick a new one. */
  function changeLocations(
    locations: WorldDraft["locations"],
    removed?: ReadonlySet<string>,
  ): void {
    setDraft((current) => ({
      ...current,
      locations,
      openings: removed
        ? current.openings.map((o) => (removed.has(o.location_id) ? { ...o, location_id: "" } : o))
        : current.openings,
    }));
    setSaveError(null);
  }

  function save(): void {
    const payload = { data: draftToWorld(draft), visibility };
    const options = { onError: (error: unknown) => setSaveError(error) };
    if (world) {
      update.mutate(payload, {
        ...options,
        onSuccess: () => toast.success(t("library.actions.saved")),
      });
    } else {
      create.mutate(payload, {
        ...options,
        onSuccess: ({ world: created }) => {
          toast.success(t("library.actions.saved"));
          void navigate(`/worlds/${created.id}`, { replace: true });
        },
      });
    }
  }

  function addToLibrary(): void {
    if (!world) return;
    duplicate.mutate(world.id, {
      onSuccess: ({ world: copy }) => {
        toast.success(t("library.actions.duplicated"));
        void navigate(`/worlds/${copy.id}`);
      },
      onError: (error) => toast.error(libraryErrorMessage(parseApiError(error).code)),
    });
  }

  function deleteWorld(): void {
    if (!world) return;
    remove.mutate(world.id, {
      onSuccess: () => {
        toast.success(t("library.actions.deleted"));
        void navigate(BACK);
      },
    });
  }

  function runJudge(): void {
    if (!world) return;
    judge.mutate(undefined, {
      onSuccess: () => toast.success(t("library.judge.done")),
    });
  }

  const title = draft.name.trim() || t("library.world.newTitle");

  return (
    <FormStateProvider value={formState}>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 pb-24 md:px-8">
        <EditorHeader
          title={title}
          backTo={BACK}
          backLabel={t("library.world.back")}
          badges={world ? <VisibilityBadge visibility={visibility} /> : null}
          actions={
            <>
              {world ? (
                <Link
                  to={`/create/chat?mode=world&world=${encodeURIComponent(world.id)}`}
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                >
                  <MessageCircle aria-hidden="true" />
                  {t("newChat.startChat")}
                </Link>
              ) : null}
              <EditorActions
                readOnly={readOnly}
                isNew={isNew}
                saving={create.isPending || update.isPending}
                onSave={save}
                onDuplicate={world ? addToLibrary : undefined}
                duplicating={duplicate.isPending}
                onDelete={deleteWorld}
                deleting={remove.isPending}
                deleteError={remove.error}
                deleteTitle={t("library.world.deleteWorldTitle", { name: title })}
                deleteDescription={t("library.world.deleteWorldDescription")}
                exportMenu={world ? <ExportMenu kind="world" id={world.id} /> : null}
              />
            </>
          }
        />
        {readOnly && world ? (
          <p className="rounded-lg border border-border bg-surface p-3 text-sm text-muted">
            {t("library.readOnly", { author: world.author })}
          </p>
        ) : null}
        <SaveErrorBanner error={saveError} />
        <Section title={t("library.world.basics")}>
          {world ? (
            <AvatarField
              label={t("library.world.cover")}
              url={world.cover_url}
              pending={cover.isPending}
              error={cover.error}
              onChange={(file) => cover.mutate(file)}
            />
          ) : (
            <p className="text-xs text-muted">{t("library.image.saveFirst")}</p>
          )}
          <TextField
            label={t("library.world.name")}
            path="name"
            value={draft.name}
            onChange={(name) => patch({ name })}
          />
          <TextAreaField
            label={t("library.world.rules")}
            path="rules"
            hint={t("library.world.rulesHint")}
            rows={6}
            value={draft.rules}
            onChange={(rules) => patch({ rules })}
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
            onChange={(checked) => {
              setVisibility(checked ? "public" : "private");
              setSaveError(null);
            }}
          />
        </Section>
        {world && (!readOnly || world.judge_score) ? (
          <CardJudgePanel
            result={world.judge_score ?? null}
            onJudge={!readOnly ? runJudge : undefined}
            pending={judge.isPending}
            error={judge.error}
            hintNote={!readOnly ? t("library.judge.savedHint") : undefined}
          />
        ) : null}
        <Section
          title={t("library.world.locations")}
          description={t("library.world.locationsHint")}
        >
          <LocationTree
            locations={draft.locations}
            onChange={changeLocations}
            openingCountFor={(ids) => draft.openings.filter((o) => ids.has(o.location_id)).length}
          />
        </Section>
        <OpeningsSection
          openings={draft.openings}
          locations={draft.locations}
          onChange={(openings) => patch({ openings })}
        />
        <Section
          title={t("library.lorebooks.title")}
          description={t("library.lorebooks.worldHint")}
        >
          <LorebookPicker
            selected={draft.lorebook_ids}
            onChange={(lorebook_ids) => patch({ lorebook_ids })}
          />
        </Section>
      </div>
    </FormStateProvider>
  );
}
