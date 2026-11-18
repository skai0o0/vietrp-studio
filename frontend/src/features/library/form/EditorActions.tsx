import { Copy, FolderPlus, Save, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import { libraryErrorMessage } from "../lib/errors";
import { ConfirmDialog } from "./ConfirmDialog";

interface EditorActionsProps {
  readOnly: boolean;
  isNew: boolean;
  saving: boolean;
  onSave: () => void;
  onDuplicate?: () => void;
  duplicating?: boolean;
  onDelete?: () => void;
  deleting?: boolean;
  deleteError?: unknown;
  deleteTitle: string;
  deleteDescription: string;
  exportMenu?: ReactNode;
}

/** Save / duplicate / delete / export row; read-only viewers get "add to my library" instead. */
export function EditorActions(props: EditorActionsProps) {
  const {
    readOnly,
    isNew,
    saving,
    onSave,
    onDuplicate,
    duplicating = false,
    onDelete,
    deleting = false,
  } = props;
  const [confirming, setConfirming] = useState(false);
  const deleteMessage =
    props.deleteError instanceof ApiError ? libraryErrorMessage(props.deleteError.code) : null;

  if (readOnly) {
    return (
      <>
        {props.exportMenu}
        {onDuplicate ? (
          <Button type="button" disabled={duplicating} onClick={onDuplicate}>
            <FolderPlus aria-hidden="true" />
            {t("library.actions.addToLibrary")}
          </Button>
        ) : null}
      </>
    );
  }

  return (
    <>
      {isNew ? null : props.exportMenu}
      {!isNew && onDuplicate ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={duplicating}
          onClick={onDuplicate}
        >
          <Copy aria-hidden="true" />
          {t("library.actions.duplicate")}
        </Button>
      ) : null}
      {!isNew && onDelete ? (
        <Button type="button" variant="outline" size="sm" onClick={() => setConfirming(true)}>
          <Trash2 aria-hidden="true" />
          {t("library.actions.delete")}
        </Button>
      ) : null}
      <Button type="button" disabled={saving} onClick={onSave}>
        <Save aria-hidden="true" />
        {saving ? t("library.actions.saving") : t("library.actions.save")}
      </Button>
      {confirming && onDelete ? (
        <ConfirmDialog
          title={props.deleteTitle}
          description={props.deleteDescription}
          confirmLabel={t("library.actions.delete")}
          pending={deleting}
          error={deleteMessage}
          onConfirm={onDelete}
          onClose={() => setConfirming(false)}
        />
      ) : null}
    </>
  );
}
