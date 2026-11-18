import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage, t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import { useCreateVault } from "./hooks";
import { retryAfterNote } from "./retryAfter";

export const DISPLAY_NAME_MAX_LENGTH = 40; // WP-D contract: display_name is 1-40 chars

interface CreateVaultDialogProps {
  open: boolean;
  passphrase: string;
  onCancel: () => void;
}

export function CreateVaultDialog({ open, passphrase, onCancel }: CreateVaultDialogProps) {
  const [displayName, setDisplayName] = useState("");
  const create = useCreateVault();
  const trimmed = displayName.trim();

  function submit(event: FormEvent): void {
    event.preventDefault();
    if (!trimmed || create.isPending) return;
    create.mutate({ passphrase, displayName: trimmed });
  }

  const error = create.error;
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{t("vault.create.title")}</DialogTitle>
            <DialogDescription>{t("vault.create.description")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="vault-display-name">{t("vault.create.displayName")}</Label>
            <Input
              id="vault-display-name"
              value={displayName}
              maxLength={DISPLAY_NAME_MAX_LENGTH}
              autoComplete="nickname"
              onChange={(event) => setDisplayName(event.target.value)}
            />
            <p className="text-xs text-muted">{t("vault.create.displayNameHint")}</p>
          </div>
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {errorMessage(error instanceof ApiError ? error.code : null)}
              {retryAfterNote(error)}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCancel}>
              {t("vault.create.cancel")}
            </Button>
            <Button type="submit" disabled={!trimmed || create.isPending}>
              {create.isPending ? t("vault.create.creating") : t("vault.create.confirm")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
