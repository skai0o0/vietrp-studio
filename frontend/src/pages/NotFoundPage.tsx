import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { PlaceholderPage } from "./PlaceholderPage";

export default function NotFoundPage() {
  return (
    <PlaceholderPage titleKey="pages.notFound.title" emptyKey="pages.notFound.empty">
      <Button asChild variant="outline">
        <Link to="/">{t("pages.notFound.back")}</Link>
      </Button>
    </PlaceholderPage>
  );
}
