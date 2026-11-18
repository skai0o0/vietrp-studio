import { useMemo, type ReactNode } from "react";
import { useRailFooter } from "@/app/pageChrome";
import { Button } from "@/components/ui/button";
import { errorMessage, t } from "@/i18n";
import { ApiError } from "@/lib/apiClient";
import { useVaultMe } from "./hooks";
import { LockButton } from "./LockButton";
import { UnlockScreen } from "./UnlockScreen";

function UnlockedShell({ children }: { children: ReactNode }) {
  const footer = useMemo(() => <LockButton />, []);
  useRailFooter(footer);
  return <>{children}</>;
}

/** Renders the unlock screen until a vault session exists; otherwise the routed app. */
export function VaultGate({ children }: { children: ReactNode }) {
  const { data, isPending, isError, error, refetch } = useVaultMe();

  if (isPending) {
    return (
      <p role="status" className="flex h-dvh items-center justify-center text-sm text-muted">
        {t("vault.loading")}
      </p>
    );
  }
  if (isError) {
    const code = error instanceof ApiError ? error.code : null;
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-4 p-4 text-center">
        <p role="alert" className="text-sm text-danger">
          {t("vault.loadFailed")} {errorMessage(code)}
        </p>
        <Button variant="outline" onClick={() => void refetch()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }
  if (data === null) return <UnlockScreen />;
  return <UnlockedShell>{children}</UnlockedShell>;
}
