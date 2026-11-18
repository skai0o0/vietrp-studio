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
import { errorMessage, t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import { useDeleteSecret } from "./hooks";
import { secretLabel } from "./secretLabel";

interface DeleteSecretDialogProps {
  name: string;
  onClose: () => void;
}

export function DeleteSecretDialog({ name, onClose }: DeleteSecretDialogProps) {
  const remove = useDeleteSecret();

  function confirm(): void {
    remove.mutate(name, {
      onSuccess: () => {
        toast.success(t("settings.apiKey.deleted"));
        onClose();
      },
    });
  }

  const error = remove.error;
  return (
    <Dialog open onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("settings.apiKey.deleteTitle", { name: secretLabel(name) })}</DialogTitle>
          <DialogDescription>{t("settings.apiKey.deleteDescription")}</DialogDescription>
        </DialogHeader>
        {error ? (
          <p role="alert" className="text-sm text-danger">
            {errorMessage(error instanceof ApiError ? error.code : null)}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("settings.apiKey.cancel")}
          </Button>
          <Button variant="danger" disabled={remove.isPending} onClick={confirm}>
            {t("settings.apiKey.deleteConfirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
