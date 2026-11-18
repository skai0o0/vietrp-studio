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
import { ImportBatchList, type BatchItem } from "./ImportBatchList";
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
  const [batch, setBatch] = useState<BatchItem[] | null>(null);
  const [batchRunning, setBatchRunning] = useState(false);

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

  function patchItem(index: number, change: Partial<BatchItem>): void {
    setBatch(
      (items) => items?.map((item, i) => (i === index ? { ...item, ...change } : item)) ?? null,
    );
  }

  /** Several files: upload one after another so each gets its own result or error. */
  async function uploadMany(files: File[]): Promise<void> {
    setBatch(
      files.map((file, i) => ({ key: `${i}-${file.name}`, name: file.name, status: "waiting" })),
    );
    setBatchRunning(true);
    for (const [index, file] of files.entries()) {
      patchItem(index, { status: "uploading" });
      try {
        const data = await importFile.mutateAsync(file);
        patchItem(index, { status: "done", result: data });
        onImported?.(data);
      } catch (err) {
        patchItem(index, { status: "error", errorCode: err instanceof ApiError ? err.code : null });
      }
    }
    setBatchRunning(false);
  }

  function handleFiles(list: FileList | null | undefined): void {
    const files = Array.from(list ?? []);
    if (files.length > 1) void uploadMany(files);
    else upload(files[0]);
  }

  function onDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragging(false);
    handleFiles(event.dataTransfer.files);
  }

  function reset(): void {
    importFile.reset();
    setResult(null);
    setBatch(null);
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

        {batch ? (
          <ImportBatchList
            items={batch}
            running={batchRunning}
            onAnother={reset}
            onNavigate={onClose}
          />
        ) : result ? (
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
                multiple
                className="sr-only"
                tabIndex={-1}
                aria-hidden
                data-testid="import-input"
                onChange={(event) => {
                  handleFiles(event.target.files);
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
