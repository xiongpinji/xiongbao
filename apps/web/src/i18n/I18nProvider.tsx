/**
 * I18n Provider：包裹应用根组件，提供翻译上下文。
 *
 * 用法（main.tsx）：
 *   <I18nProvider><App /></I18nProvider>
 */

import { useCallback, useMemo, useState, type ReactNode } from "react";
import {
  I18nContext,
  createTranslator,
  detectLocale,
  type Locale,
} from "./index";

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(detectLocale);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem("xagent_locale", l);
  }, []);

  const t = useMemo(() => createTranslator(locale), [locale]);

  const value = useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
