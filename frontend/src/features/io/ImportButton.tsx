import { Upload } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import type { ImportResult } from "@/types/library";
import { ImportDialog } from "./ImportDialog";

export interface ImportButtonProps {
  onImported?: (result: ImportResult) => void;
}

export function ImportButton({ onImported }: ImportButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Upload aria-hidden />
        {t("io.import.button")}
      </Button>
      {open ? <ImportDialog onClose={() => setOpen(false)} onImported={onImported} /> : null}
    </>
  );
}
