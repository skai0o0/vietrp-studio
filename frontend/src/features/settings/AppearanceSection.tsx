import { useThemeStore, type ThemeId } from "@/app/theme";
import { Button } from "@/components/ui/button";
import { t, type MessageKey } from "@/i18n";

const THEME_OPTIONS: { id: ThemeId; labelKey: MessageKey }[] = [
  { id: "oled-neon", labelKey: "theme.oledNeon" },
  { id: "e-ink", labelKey: "theme.eInk" },
];

export function AppearanceSection() {
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  return (
    <section aria-labelledby="settings-appearance" className="grid gap-3">
      <div>
        <h2 id="settings-appearance" className="text-lg font-semibold">
          {t("settings.appearance.title")}
        </h2>
        <p className="text-sm text-muted">{t("settings.appearance.description")}</p>
      </div>
      <div role="group" aria-labelledby="settings-appearance" className="flex flex-wrap gap-2">
        {THEME_OPTIONS.map((option) => (
          <Button
            key={option.id}
            variant={theme === option.id ? "default" : "outline"}
            aria-pressed={theme === option.id}
            onClick={() => setTheme(option.id)}
          >
            {t(option.labelKey)}
          </Button>
        ))}
      </div>
    </section>
  );
}
