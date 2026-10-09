import type { Lang } from "@/api/types";

/** Prefix that marks an English mock reply shown in another UI language (offline mock mode only). */
export function mockLabel(lang: Lang): string {
  return lang === "en-US" ? "" : "[Offline mock · English only] ";
}
