import * as SheetPrimitive from "@radix-ui/react-dialog";
import { cva, type VariantProps } from "class-variance-authority";
import { X } from "lucide-react";
import * as React from "react";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";

const Sheet = SheetPrimitive.Root;
const SheetTrigger = SheetPrimitive.Trigger;
const SheetClose = SheetPrimitive.Close;
const SheetTitle = SheetPrimitive.Title;
const SheetDescription = SheetPrimitive.Description;

const SheetOverlay = React.forwardRef<
  React.ElementRef<typeof SheetPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof SheetPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <SheetPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-modal bg-scrim data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:duration-exit data-[state=open]:duration-panel motion-reduce:animate-none",
      className,
    )}
    {...props}
  />
));
SheetOverlay.displayName = "SheetOverlay";

const sheetVariants = cva(
  "fixed z-modal flex flex-col border-border bg-surface shadow-dialog data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:duration-[160ms] data-[state=open]:duration-[240ms] motion-reduce:animate-none",
  {
    variants: {
      side: {
        left: "inset-y-0 left-0 h-full w-[85%] max-w-sm border-r pt-safe data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left",
        right:
          "inset-y-0 right-0 h-full w-[85%] max-w-sm border-l pt-safe data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
        bottom:
          "inset-x-0 bottom-0 max-h-[85dvh] rounded-t-lg border-t pb-safe data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
      },
    },
    defaultVariants: { side: "right" },
  },
);

export interface SheetContentProps
  extends
    React.ComponentPropsWithoutRef<typeof SheetPrimitive.Content>,
    VariantProps<typeof sheetVariants> {
  closeLabel?: string;
  hideDefaultClose?: boolean;
}

const SheetContent = React.forwardRef<
  React.ElementRef<typeof SheetPrimitive.Content>,
  SheetContentProps
>(({ side = "right", closeLabel, hideDefaultClose = false, className, children, ...props }, ref) => (
  <SheetPrimitive.Portal>
    <SheetOverlay />
    <SheetPrimitive.Content ref={ref} className={cn(sheetVariants({ side }), className)} {...props}>
      {children}
      {!hideDefaultClose ? (
        <SheetPrimitive.Close
          aria-label={closeLabel ?? t("common.close")}
          className={cn(
            "absolute right-3 flex size-10 cursor-pointer items-center justify-center rounded-md text-muted transition-[color,background-color,transform] duration-fast ease-ui hover:bg-hover/10 hover:text-fg active:scale-[0.96] motion-reduce:active:scale-100 md:size-9",
            side === "bottom" ? "top-3" : "top-[calc(0.75rem+env(safe-area-inset-top,0px))]",
          )}
        >
          <X className="size-4" aria-hidden="true" />
        </SheetPrimitive.Close>
      ) : null}
    </SheetPrimitive.Content>
  </SheetPrimitive.Portal>
));
SheetContent.displayName = "SheetContent";

/** Sticky header bar placed in-flow so drawer close controls never cover sidebar headings. */
function SheetHeader({
  title,
  closeLabel,
  showHandle = false,
  className,
}: {
  title: React.ReactNode;
  closeLabel?: string;
  showHandle?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("shrink-0 border-b border-border-subtle bg-surface", className)}>
      {showHandle ? (
        <div className="flex justify-center pt-2" aria-hidden="true">
          <span className="h-1 w-10 rounded-full bg-border-strong" />
        </div>
      ) : null}
      <div className="flex items-center justify-between gap-2 px-4 py-2.5">
        <span className="min-w-0 truncate text-sm font-semibold text-fg">{title}</span>
        <SheetPrimitive.Close
          aria-label={closeLabel ?? t("common.close")}
          className="flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted transition-[color,background-color,transform] duration-fast ease-ui hover:bg-hover/10 hover:text-fg active:scale-[0.96] motion-reduce:active:scale-100 md:size-9"
        >
          <X className="size-4" aria-hidden="true" />
        </SheetPrimitive.Close>
      </div>
    </div>
  );
}

export {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetOverlay,
  SheetTitle,
  SheetTrigger,
};
