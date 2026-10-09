import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { DEFAULT_LANG, type Lang } from "@/api/types";
import en from "./locales/en-US.json";
import { useApp } from "@/store/app";

type Bundle = Record<string, unknown>;

/**
 * English (en-US) ships in the main bundle and is the fallback for any missing key. The other
 * five languages are separate chunks loaded on demand. A glob (not five static imports) keeps the
 * build working while a translation file is still being written: a missing file falls back to English.
 */
const LAZY = import.meta.glob<{ default: Bundle }>(["./locales/*.json", "!./locales/en-US.json"]);

function loaderFor(lang: Lang): () => Promise<Bundle> {
  if (lang === DEFAULT_LANG) return async () => en as Bundle;
  const load = LAZY[`./locales/${lang}.json`];
  if (!load) return async () => en as Bundle;
  return () => load().then((m) => m.default);
}

/** Selector labels (each language's own name) plus the English name and a short code for small screens. */
export const LANG_LABELS: Record<Lang, { native: string; english: string; short: string }> = {
  "en-US": { native: "English", english: "English", short: "EN" },
  "es-ES": { native: "Español", english: "Spanish", short: "ES" },
  "fr-FR": { native: "Français", english: "French", short: "FR" },
  "de-DE": { native: "Deutsch", english: "German", short: "DE" },
  "it-IT": { native: "Italiano", english: "Italian", short: "IT" },
  "ja-JP": { native: "日本語", english: "Japanese", short: "日本" },
};

void i18n.use(initReactI18next).init({
  resources: { [DEFAULT_LANG]: { translation: en } },
  partialBundledLanguages: true,
  lng: DEFAULT_LANG,
  fallbackLng: DEFAULT_LANG,
  interpolation: { escapeValue: false },
  returnNull: false,
});

/** Load a language's strings (once) and switch i18next to it. Falls back to English on failure. */
export async function loadLanguage(lang: Lang): Promise<void> {
  try {
    if (!i18n.hasResourceBundle(lang, "translation")) {
      const bundle = await loaderFor(lang)();
      i18n.addResourceBundle(lang, "translation", bundle, true, true);
    }
    // Ignore a stale load if the user switched again meanwhile.
    if (useApp.getState().lang === lang) await i18n.changeLanguage(lang);
  } catch {
    await i18n.changeLanguage(DEFAULT_LANG);
  }
}

function applyDocumentLang(lang: Lang) {
  if (typeof document !== "undefined") document.documentElement.lang = lang;
}
applyDocumentLang(useApp.getState().lang);

/** Resolves once the stored language is ready (main.tsx waits for it before the first render). */
export const i18nReady: Promise<void> = loadLanguage(useApp.getState().lang);

useApp.subscribe((s, prev) => {
  if (s.lang !== prev.lang) {
    void loadLanguage(s.lang);
    applyDocumentLang(s.lang);
  }
});

export default i18n;
