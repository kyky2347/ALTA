import { Languages } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useI18n } from "@/lib/i18n";

export function LanguageToggle() {
  const { locale, t, toggleLocale } = useI18n();
  const label = locale === "en" ? t("switchToChinese") : t("switchToEnglish");

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="language-button"
          aria-label={label}
          onClick={toggleLocale}
        >
          <Languages data-icon="inline-start" />
          <span aria-hidden="true">{locale === "en" ? "中文" : "EN"}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
