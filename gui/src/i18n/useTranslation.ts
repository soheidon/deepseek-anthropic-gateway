import { useContext } from "react";
import { LanguageContext } from "./LanguageContext";
import { translations, type TranslationKey } from "./translations";

export function useTranslation() {
  const { lang } = useContext(LanguageContext);

  function t(key: TranslationKey, params?: Record<string, string | number>): string {
    let text: string = translations[lang][key];
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        text = text.replace(`{${k}}`, String(v));
      }
    }
    return text;
  }

  return { t, lang };
}
