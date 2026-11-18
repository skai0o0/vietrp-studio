import { Eye, EyeOff } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage, t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import { cn } from "@/lib/cn";
import { CreateVaultDialog } from "./CreateVaultDialog";
import { useUnlock } from "./hooks";
import { isPassphraseStrong } from "./passphrase";
import { retryAfterNote } from "./retryAfter";

function strengthText(passphrase: string, strong: boolean): string {
  if (!passphrase) return t("vault.strength.hint");
  return strong ? t("vault.strength.ok") : t("vault.strength.weak");
}

export function UnlockScreen() {
  const [passphrase, setPassphrase] = useState("");
  const [visible, setVisible] = useState(false);
  const [confirmCreate, setConfirmCreate] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const unlock = useUnlock();
  const strong = isPassphraseStrong(passphrase);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function submit(event: FormEvent): void {
    event.preventDefault();
    if (!passphrase || unlock.isPending) return;
    unlock.mutate(passphrase, {
      onSuccess: (result) => {
        if (!result.exists) setConfirmCreate(true);
      },
    });
  }

  function cancelCreate(): void {
    setConfirmCreate(false);
    inputRef.current?.focus();
  }

  const error = unlock.error;
  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <section
        aria-labelledby="unlock-title"
        className="w-full max-w-md rounded-lg border border-border bg-surface p-6 shadow-glow"
      >
        <p className="text-sm font-semibold text-accent">{t("app.name")}</p>
        <h1 id="unlock-title" className="mt-1 text-2xl font-semibold">
          {t("vault.unlock.title")}
        </h1>
        <p className="mt-3 text-sm text-muted">{t("vault.unlock.intro")}</p>
        <p className="mt-2 text-sm text-fg">{t("vault.unlock.warning")}</p>

        <form onSubmit={submit} className="mt-5 grid gap-3">
          <Label htmlFor="vault-passphrase">{t("vault.unlock.passphrase")}</Label>
          <div className="relative">
            <Input
              ref={inputRef}
              id="vault-passphrase"
              name="passphrase"
              type={visible ? "text" : "password"}
              autoComplete="current-password"
              autoCapitalize="none"
              spellCheck={false}
              className="pr-11"
              value={passphrase}
              aria-describedby="vault-passphrase-hint"
              onChange={(event) => setPassphrase(event.target.value)}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute right-0 top-0"
              aria-label={visible ? t("vault.unlock.hide") : t("vault.unlock.show")}
              aria-pressed={visible}
              onClick={() => setVisible((v) => !v)}
            >
              {visible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
            </Button>
          </div>
          <p
            id="vault-passphrase-hint"
            className={cn("text-xs", passphrase && !strong ? "text-danger" : "text-muted")}
          >
            {strengthText(passphrase, strong)}
          </p>
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {errorMessage(error instanceof ApiError ? error.code : null)}
              {retryAfterNote(error)}
            </p>
          ) : null}
          <Button type="submit" disabled={!passphrase || unlock.isPending}>
            {unlock.isPending ? t("vault.unlock.submitting") : t("vault.unlock.submit")}
          </Button>
        </form>
      </section>
      <CreateVaultDialog open={confirmCreate} passphrase={passphrase} onCancel={cancelCreate} />
    </main>
  );
}
