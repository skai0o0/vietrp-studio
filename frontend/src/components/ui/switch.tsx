import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as React from "react";
import { cn } from "@/lib/cn";

const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitive.Root
    ref={ref}
    className={cn(
      "inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border border-border bg-surface-2 transition-colors data-[state=checked]:bg-accent disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  >
    <SwitchPrimitive.Thumb className="pointer-events-none block size-4 translate-x-1 rounded-full bg-fg transition-transform data-[state=checked]:translate-x-6 data-[state=checked]:bg-accent-fg" />
  </SwitchPrimitive.Root>
));
Switch.displayName = "Switch";

export { Switch };
