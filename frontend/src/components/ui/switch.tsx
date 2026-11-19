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
      "relative inline-flex h-6 w-11 shrink-0 cursor-pointer touch-manipulation items-center rounded-full border border-border bg-surface-2 p-0.5 transition-colors duration-panel ease-ui before:absolute before:-inset-x-1 before:-inset-y-2.5 before:content-[''] hover:border-border-strong data-[state=checked]:border-accent data-[state=checked]:bg-accent disabled:cursor-not-allowed disabled:opacity-45",
      className,
    )}
    {...props}
  >
    <SwitchPrimitive.Thumb className="pointer-events-none block size-[18px] translate-x-0 rounded-full bg-fg transition-transform duration-panel ease-ui motion-reduce:transition-none data-[state=checked]:translate-x-5 data-[state=checked]:bg-accent-fg" />
  </SwitchPrimitive.Root>
));
Switch.displayName = "Switch";

export { Switch };
