import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { VaultGate } from "@/features/vault/VaultGate";
import { queryClient } from "@/lib/queryClient";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>
        <VaultGate>{children}</VaultGate>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
