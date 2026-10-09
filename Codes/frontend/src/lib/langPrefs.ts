import { DEFAULT_LANG, isLang, type Lang } from "@/api/types";

/** A stored or requested language code: one of the six supported codes passes through; anything else becomes English. */
export function normalizeLang(stored: unknown): Lang {
  return isLang(stored) ? stored : DEFAULT_LANG;
}

/** True for any English UI language (labels the backend sends only in English need no lang="en" marker). */
export const isEnglish = (lang: string | null | undefined) => (lang ?? "").toLowerCase().startsWith("en");
