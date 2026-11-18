import { Toaster as Sonner, type ToasterProps } from "sonner";
import { useThemeStore } from "@/app/theme";

export function Toaster(props: ToasterProps) {
  const theme = useThemeStore((state) => state.theme);
  return (
    <Sonner
      theme={theme === "e-ink" ? "light" : "dark"}
      toastOptions={{
        classNames: {
          toast: "!border !border-border !bg-surface !text-fg !shadow-none",
          description: "!text-muted",
        },
      }}
      {...props}
    />
  );
}
