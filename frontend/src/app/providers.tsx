import { QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import type { ReactNode } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { VaultGate } from "@/features/vault/VaultGate";
import { queryClient } from "@/lib/queryClient";
import { useReducedMotion } from "@/lib/useReducedMotion";

export function Providers({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <MotionConfig reducedMotion={reduced ? "always" : "user"}>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={200}>
          <VaultGate>{children}</VaultGate>
          <Toaster />
        </TooltipProvider>
      </QueryClientProvider>
    </MotionConfig>
  );
}
