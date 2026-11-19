import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex cursor-pointer select-none touch-manipulation items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-[color,background-color,border-color,transform] duration-fast ease-ui active:translate-y-px active:scale-[0.985] motion-reduce:active:translate-y-0 motion-reduce:active:scale-100 disabled:cursor-not-allowed disabled:opacity-45 aria-[pressed=true]:border-accent aria-[pressed=true]:bg-accent/15 aria-[pressed=true]:text-fg [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-accent text-accent-fg hover:brightness-110 active:brightness-95",
        secondary:
          "border border-border bg-surface-2 text-fg hover:border-border-strong hover:bg-hover/10",
        outline:
          "border border-border bg-transparent text-fg hover:border-border-strong hover:bg-hover/10",
        ghost: "text-muted hover:bg-hover/10 hover:text-fg",
        danger: "bg-danger text-danger-fg hover:brightness-110 active:brightness-95",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 px-3",
        icon: "size-10",
        "icon-sm": "size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    const isDisabled = Boolean(disabled || loading);
    return (
      <Comp
        ref={ref}
        data-variant={variant ?? "default"}
        disabled={asChild ? disabled : isDisabled}
        aria-busy={loading || undefined}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      >
        {asChild ? (
          children
        ) : (
          <>
            {loading ? <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" /> : null}
            {children}
          </>
        )}
      </Comp>
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
