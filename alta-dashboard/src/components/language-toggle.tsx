import { Check, ChevronDown, Languages } from "lucide-react";
import { DropdownMenu as Menu } from "radix-ui";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { LOCALES, type Locale } from "@/lib/locale";
import "./operator-settings.css";

export function LanguageToggle() {
  const { locale, t, setLocale } = useI18n();

  return (
    <Menu.Root>
      <Menu.Trigger asChild>
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
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content
          className="language-menu"
          align="end"
          sideOffset={8}
          aria-label={t("language")}
        >
          <Menu.Group>
            <Menu.RadioGroup
              value={locale}
              onValueChange={(value) => setLocale(value as Locale)}
            >
              {LOCALES.map((item) => (
                <Menu.RadioItem
                  className="language-option"
                  key={item.id}
                  value={item.id}
                  lang={item.id}
                >
                  {item.label}
                  <Menu.ItemIndicator>
                    <Check aria-hidden="true" />
                  </Menu.ItemIndicator>
                </Menu.RadioItem>
              ))}
            </Menu.RadioGroup>
          </Menu.Group>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}
