import { Toaster as Sonner, type ToasterProps } from "sonner";
import { useThemeStore } from "@/app/theme";

export function Toaster(props: ToasterProps) {
  const theme = useThemeStore((state) => state.theme);
  return (
    <Sonner
      theme={theme === "e-ink" ? "light" : "dark"}
      closeButton
      mobileOffset={{ bottom: "calc(4.5rem + env(safe-area-inset-bottom, 0px))" }}
      toastOptions={{
        classNames: {
          toast: "!border !border-border !bg-surface-3 !text-fg !shadow-popover",
          description: "!text-muted",
          error: "!border-danger !text-danger-text",
          success: "!border-success",
        },
      }}
      {...props}
    />
  );
}
