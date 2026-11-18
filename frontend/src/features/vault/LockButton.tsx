import { Lock } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { useLock } from "./hooks";

/** Icon-only lock button for the IconRail footer. */
export function LockButton() {
  const lock = useLock();
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("vault.lock")}
          disabled={lock.isPending}
          onClick={() => lock.mutate()}
        >
          <Lock aria-hidden="true" />
        </Button>
      </TooltipTrigger>
      <TooltipContent side="right">{t("vault.lock")}</TooltipContent>
    </Tooltip>
  );
}

/** Labelled lock button (settings page, the only lock control on mobile). */
export function LockTextButton(props: Pick<ButtonProps, "variant">) {
  const lock = useLock();
  return (
    <Button
      variant={props.variant ?? "outline"}
      disabled={lock.isPending}
      onClick={() => lock.mutate()}
    >
      <Lock aria-hidden="true" />
      {t("vault.lock")}
    </Button>
  );
}
