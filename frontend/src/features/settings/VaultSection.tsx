import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DISPLAY_NAME_MAX_LENGTH } from "@/features/vault/CreateVaultDialog";
import { useRenameVault, useVaultMe } from "@/features/vault/hooks";
import { LockTextButton } from "@/features/vault/LockButton";
import { errorMessage, t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";

function RenameForm({ initial }: { initial: string }) {
  const [name, setName] = useState(initial);
  const rename = useRenameVault();
  const trimmed = name.trim();

  function submit(event: FormEvent): void {
    event.preventDefault();
    if (!trimmed || rename.isPending) return;
    rename.mutate(trimmed, { onSuccess: () => toast.success(t("settings.vault.saved")) });
  }

  return (
    <form onSubmit={submit} className="grid gap-2">
      <Label htmlFor="settings-display-name">{t("settings.vault.displayName")}</Label>
      <div className="flex flex-wrap gap-2">
        <Input
          id="settings-display-name"
          className="min-w-0 flex-1"
          value={name}
          maxLength={DISPLAY_NAME_MAX_LENGTH}
          autoComplete="nickname"
          onChange={(event) => setName(event.target.value)}
        />
        <Button type="submit" disabled={!trimmed || trimmed === initial || rename.isPending}>
          {t("settings.vault.save")}
        </Button>
      </div>
      {rename.error ? (
        <p role="alert" className="text-sm text-danger">
          {errorMessage(rename.error instanceof ApiError ? rename.error.code : null)}
        </p>
      ) : null}
    </form>
  );
}

export function VaultSection() {
  const { data } = useVaultMe();
  return (
    <section aria-labelledby="settings-vault" className="grid gap-3">
      <h2 id="settings-vault" className="text-lg font-semibold">
        {t("settings.vault.title")}
      </h2>
      {data ? <RenameForm key={data.id} initial={data.display_name} /> : null}
      <div className="grid justify-items-start gap-2">
        <p className="text-sm text-muted">{t("settings.vault.lockDescription")}</p>
        <LockTextButton />
      </div>
    </section>
  );
}
