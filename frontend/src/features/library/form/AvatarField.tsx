import { ImagePlus, Trash2 } from "lucide-react";
import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { libraryErrorMessage } from "../lib/errors";
import { useFormState } from "./FormContext";
import { ApiError } from "@/lib/apiClient";

interface AvatarFieldProps {
  label: string;
  url: string | null;
  /** Upload a new image, or `null` to remove the current one. */
  onChange: (file: Blob | null) => void;
  pending: boolean;
  error: unknown;
}

/** Image upload for an already-saved item (avatar or cover). */
export function AvatarField({ label, url, onChange, pending, error }: AvatarFieldProps) {
  const { readOnly } = useFormState();
  const inputRef = useRef<HTMLInputElement>(null);
  const message = error instanceof ApiError ? libraryErrorMessage(error.code) : null;

  return (
    <div className="flex items-center gap-4">
      <div className="size-20 shrink-0 overflow-hidden rounded-lg border border-border bg-surface-2">
        {url ? <img src={url} alt={label} className="size-full object-cover" /> : null}
      </div>
      {readOnly ? null : (
        <div className="flex min-w-0 flex-col items-start gap-2">
          <input
            ref={inputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            aria-label={label}
            tabIndex={-1}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) onChange(file);
            }}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={pending}
              onClick={() => inputRef.current?.click()}
            >
              <ImagePlus aria-hidden="true" />
              {url ? t("library.image.replace") : t("library.image.upload")}
            </Button>
            {url ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={pending}
                onClick={() => onChange(null)}
              >
                <Trash2 aria-hidden="true" />
                {t("library.image.remove")}
              </Button>
            ) : null}
          </div>
          <p className="text-xs text-muted">{t("library.image.hint")}</p>
          {message ? (
            <p role="alert" className="text-xs text-danger">
              {message}
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}
