import * as React from "react";
import { cn } from "@/lib/cn";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex w-full rounded-md border border-border bg-field px-3 py-2 text-base text-fg transition-colors duration-fast ease-ui placeholder:text-muted hover:border-border-strong focus-visible:border-focus aria-[invalid=true]:border-2 aria-[invalid=true]:border-danger read-only:border-dashed read-only:bg-surface-2 read-only:text-muted disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";

export { Textarea };
