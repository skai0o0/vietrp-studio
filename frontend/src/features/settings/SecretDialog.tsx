import { Eye, EyeOff } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
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
import { usePutSecret } from "./hooks";
import { secretLabel } from "./secretLabel";

interface SecretDialogProps {
  name: string;
  onClose: () => void;
}

/** Set/replace dialog. The value lives only in this component and is cleared on close. */
export function SecretDialog({ name, onClose }: SecretDialogProps) {
  const [value, setValue] = useState("");
  const [visible, setVisible] = useState(false);
  const put = usePutSecret();
  const trimmed = value.trim();

  function submit(event: FormEvent): void {
    event.preventDefault();
    if (!trimmed || put.isPending) return;
    put.mutate(
      { name, value: trimmed },
      {
        onSuccess: () => {
          setValue("");
          toast.success(t("settings.apiKey.saved"));
          onClose();
        },
      },
    );
  }

  const error = put.error;
  return (
    <Dialog open onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>
              {t("settings.apiKey.dialogTitle", { name: secretLabel(name) })}
            </DialogTitle>
            <DialogDescription>{t("settings.apiKey.dialogDescription")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="secret-value">{t("settings.apiKey.value")}</Label>
            <div className="relative">
              <Input
                id="secret-value"
                type={visible ? "text" : "password"}
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                className="pr-11"
                value={value}
                onChange={(event) => setValue(event.target.value)}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute right-0 top-0"
                aria-label={visible ? t("settings.apiKey.hide") : t("settings.apiKey.show")}
                aria-pressed={visible}
                onClick={() => setVisible((v) => !v)}
              >
                {visible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
              </Button>
            </div>
          </div>
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {errorMessage(error instanceof ApiError ? error.code : null)}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("settings.apiKey.cancel")}
            </Button>
            <Button type="submit" disabled={!trimmed || put.isPending}>
              {put.isPending ? t("settings.apiKey.saving") : t("settings.apiKey.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
