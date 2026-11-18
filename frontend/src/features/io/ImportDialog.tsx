import { Upload } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useImportFile } from "@/features/library/hooks";
import { errorMessage, t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import { cn } from "@/lib/cn";
import type { ImportResult } from "@/types/library";
import { ImportResultPanel } from "./ImportResultPanel";

const ACCEPT = ".json,.png,application/json,image/png";

interface ImportDialogProps {
  onClose: () => void;
  onImported?: ((result: ImportResult) => void) | undefined;
}

export function ImportDialog({ onClose, onImported }: ImportDialogProps) {
  const importFile = useImportFile();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);

  function upload(file: File | undefined): void {
    if (!file) return;
    setFileName(file.name);
    importFile.mutate(file, {
      onSuccess: (data) => {
        setResult(data);
        onImported?.(data);
      },
    });
  }

  function onDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragging(false);
    upload(event.dataTransfer.files[0]);
  }

  function reset(): void {
    importFile.reset();
    setResult(null);
    setFileName("");
  }

  const error = importFile.error;
  return (
    <Dialog open onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("io.import.title")}</DialogTitle>
          <DialogDescription>{t("io.import.description")}</DialogDescription>
        </DialogHeader>

        {result ? (
          <ImportResultPanel result={result} onAnother={reset} onNavigate={onClose} />
        ) : (
          <div className="flex flex-col gap-3">
            <div
              data-testid="import-dropzone"
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                "flex flex-col items-center gap-3 rounded-lg border border-dashed border-border bg-surface p-6 text-center",
                dragging && "border-accent bg-accent/10",
              )}
            >
              <Upload className="size-6 text-muted" aria-hidden />
              <p className="text-sm">{t("io.import.drop")}</p>
              <Button
                variant="outline"
                disabled={importFile.isPending}
                onClick={() => inputRef.current?.click()}
              >
                {t("io.import.pick")}
              </Button>
              <p className="text-xs text-muted">{t("io.import.hint")}</p>
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                className="sr-only"
                tabIndex={-1}
                aria-hidden
                data-testid="import-input"
                onChange={(event) => {
                  upload(event.target.files?.[0]);
                  event.target.value = "";
                }}
              />
            </div>
            {importFile.isPending ? (
              <p role="status" className="text-sm text-muted">
                {t("io.import.uploading", { name: fileName })}
              </p>
            ) : null}
            {error ? (
              <p role="alert" className="text-sm text-danger">
                {errorMessage(error instanceof ApiError ? error.code : null)}
              </p>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
