import { Separator } from "@/components/ui/separator";
import { t } from "@/i18n";
import { ApiKeySection } from "./ApiKeySection";
import { AppearanceSection } from "./AppearanceSection";
import { PresetsSection } from "./presets/PresetsSection";
import { VaultSection } from "./VaultSection";

export default function SettingsPage() {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-4 md:p-8">
      <h1 className="text-2xl font-semibold">{t("pages.settings.title")}</h1>
      <VaultSection />
      <Separator />
      <ApiKeySection />
      <Separator />
      <AppearanceSection />
      <Separator />
      <PresetsSection />
    </div>
  );
}
