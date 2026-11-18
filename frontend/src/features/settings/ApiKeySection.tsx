import { Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { errorMessage, t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import type { SecretOut } from "@/features/vault/api";
import { DeleteSecretDialog } from "./DeleteSecretDialog";
import { useSecrets } from "./hooks";
import { SecretDialog } from "./SecretDialog";
import { secretLabel } from "./secretLabel";

function SecretRow({
  secret,
  onEdit,
  onDelete,
}: {
  secret: SecretOut;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const label = secretLabel(secret.name);
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-surface-2 p-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{label}</p>
        <p className="text-sm text-muted">
          {secret.is_set ? `••••${secret.hint ?? ""}` : t("settings.apiKey.notSet")}
        </p>
      </div>
      <Button variant="outline" size="sm" onClick={onEdit}>
        {secret.is_set ? t("settings.apiKey.replace") : t("settings.apiKey.set")}
      </Button>
      {secret.is_set ? (
        <Button
          variant="ghost"
          size="icon"
          aria-label={`${t("settings.apiKey.remove")}: ${label}`}
          onClick={onDelete}
        >
          <Trash2 aria-hidden="true" />
        </Button>
      ) : null}
    </li>
  );
}

export function ApiKeySection() {
  const { data, isPending, isError, error, refetch } = useSecrets();
  const [editing, setEditing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  return (
    <section aria-labelledby="settings-api-key" className="grid gap-3">
      <div>
        <h2 id="settings-api-key" className="text-lg font-semibold">
          {t("settings.apiKey.title")}
        </h2>
        <p className="text-sm text-muted">{t("settings.apiKey.description")}</p>
      </div>
      {isPending ? (
        <p role="status" className="text-sm text-muted">
          {t("pages.loading")}
        </p>
      ) : null}
      {isError ? (
        <div className="flex flex-wrap items-center gap-3">
          <p role="alert" className="text-sm text-danger">
            {t("settings.apiKey.loadFailed")}{" "}
            {errorMessage(error instanceof ApiError ? error.code : null)}
          </p>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            {t("common.retry")}
          </Button>
        </div>
      ) : null}
      {data ? (
        <ul className="grid gap-2">
          {data.map((secret) => (
            <SecretRow
              key={secret.name}
              secret={secret}
              onEdit={() => setEditing(secret.name)}
              onDelete={() => setDeleting(secret.name)}
            />
          ))}
        </ul>
      ) : null}
      {editing ? <SecretDialog name={editing} onClose={() => setEditing(null)} /> : null}
      {deleting ? <DeleteSecretDialog name={deleting} onClose={() => setDeleting(null)} /> : null}
    </section>
  );
}
