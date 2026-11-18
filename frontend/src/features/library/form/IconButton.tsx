import type { LucideIcon } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/button";
import { cn } from "@/lib/cn";

interface IconButtonProps extends Omit<ButtonProps, "children" | "size"> {
  icon: LucideIcon;
  /** Required accessible name (from vi.ts). */
  label: string;
}

/** Compact icon-only button; the label doubles as the tooltip. */
export function IconButton({
  icon: Icon,
  label,
  className,
  variant = "ghost",
  ...props
}: IconButtonProps) {
  return (
    <Button
      type="button"
      variant={variant}
      aria-label={label}
      title={label}
      className={cn("size-9 shrink-0 p-0", className)}
      {...props}
    >
      <Icon aria-hidden="true" />
    </Button>
  );
}
