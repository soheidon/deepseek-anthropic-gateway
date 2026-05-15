import { createContext, useState, useEffect, type ReactNode } from "react";
import type { Lang } from "./translations";

function readLang(): Lang {
  try {
    const stored = localStorage.getItem("lang");
    if (stored === "ja" || stored === "en") return stored;
  } catch {
    // localStorage unavailable (private browsing, etc.)
  }
  return "ja";
}

export const LanguageContext = createContext<{
  lang: Lang;
  setLang: (lang: Lang) => void;
}>({
  lang: "ja",
  setLang: () => {},
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readLang);

  useEffect(() => {
    try {
      localStorage.setItem("lang", lang);
    } catch {
      // ignore
    }
  }, [lang]);

  return (
    <LanguageContext.Provider value={{ lang, setLang: setLangState }}>
      {children}
    </LanguageContext.Provider>
  );
}
