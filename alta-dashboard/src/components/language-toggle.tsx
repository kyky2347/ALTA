import { Check, ChevronDown, Languages } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuItemIndicator,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { LOCALES, type Locale } from "@/lib/locale";
import "./operator-settings.css";

export function LanguageToggle() {
  const { locale, t, setLocale } = useI18n();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="language-button"
          aria-label={t("language")}
        >
          <Languages data-icon="inline-start" />
          <span>{LOCALES.find((item) => item.id === locale)?.label}</span>
          <ChevronDown data-icon="inline-end" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        className="language-menu"
        align="end"
        sideOffset={8}
        aria-label={t("language")}
      >
        <DropdownMenuGroup>
          <DropdownMenuRadioGroup
            value={locale}
            onValueChange={(value) => setLocale(value as Locale)}
          >
            {LOCALES.map((item) => (
              <DropdownMenuRadioItem
                className="language-option"
                key={item.id}
                value={item.id}
                lang={item.id}
              >
                {item.label}
                <DropdownMenuItemIndicator>
                  <Check aria-hidden="true" />
                </DropdownMenuItemIndicator>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
