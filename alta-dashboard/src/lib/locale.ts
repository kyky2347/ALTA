export const LOCALES = [
  { id: "en", label: "English" },
  { id: "zh-CN", label: "简体中文" },
  { id: "zh-HK", label: "繁體中文" },
] as const;
export type Locale = (typeof LOCALES)[number]["id"];
export function resolveLocale(
  stored: string | null,
  languages: readonly string[],
): Locale {
  if (LOCALES.some((locale) => locale.id === stored)) return stored as Locale;
  for (const value of languages) {
    if (/^(zh-(?:hk|mo|tw|hant)(?:-|$)|yue(?:-|$))/i.test(value))
      return "zh-HK";
    if (/^zh(?:-|$)/i.test(value)) return "zh-CN";
    if (/^en(?:-|$)/i.test(value)) return "en";
  }
  return "en";
}
