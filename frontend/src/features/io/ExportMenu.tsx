import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useExportCharacter, useExportLorebook, useExportWorld } from "@/features/library/hooks";
import { errorMessage, t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import type { ExportFormat, LorebookExportFormat } from "@/types/library";
import {
  resolveOptions,
  type ExportFormatId,
  type ExportKind,
  type ExportOption,
} from "./exportOptions";

export interface ExportMenuProps {
  kind: ExportKind;
  id: string;
  /** Subset of the formats allowed for `kind`; defaults to all of them. */
  formats?: readonly ExportFormatId[];
}

export function ExportMenu({ kind, id, formats }: ExportMenuProps) {
  const character = useExportCharacter();
  const world = useExportWorld();
  const lorebook = useExportLorebook();
  const options = resolveOptions(kind, formats);
  const pending = character.isPending || world.isPending || lorebook.isPending;

  function run(option: ExportOption): void {
    const callbacks = {
      onSuccess: () => toast.success(t("io.export.done")),
      onError: (error: unknown) =>
        toast.error(errorMessage(error instanceof ApiError ? error.code : null)),
    };
    if (kind === "character") {
      character.mutate({ id, format: option.format as ExportFormat, as: option.as }, callbacks);
    } else if (kind === "world") {
      world.mutate(id, callbacks);
    } else {
      lorebook.mutate({ id, format: option.format as LorebookExportFormat }, callbacks);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={pending}
          aria-label={t("io.export.menuLabel")}
        >
          <Download aria-hidden />
          {t("io.export.button")}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{t("io.export.menuLabel")}</DropdownMenuLabel>
        {options.map((option) => (
          <DropdownMenuItem key={option.id} onSelect={() => run(option)}>
            {t(option.labelKey)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
