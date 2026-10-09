// Test helper: the locale dictionaries as plain trees. A translation file that is still being written
// is simply absent here (the parity test reports it); the app itself falls back to English.
import en from "./locales/en-US.json";

export type Tree = { [k: string]: string | Tree };

export const TRANSLATED = ["es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"] as const;
export type TranslatedLang = (typeof TRANSLATED)[number];

const files = import.meta.glob<Tree>("./locales/*.json", { eager: true, import: "default" });

export const EN = en as Tree;

export function localeTree(lang: string): Tree | null {
  return files[`./locales/${lang}.json`] ?? null;
}

/** en-US plus every translated locale file that exists. */
export function allLocales(): Record<string, Tree> {
  const out: Record<string, Tree> = { "en-US": EN };
  for (const l of TRANSLATED) {
    const tr = localeTree(l);
    if (tr) out[l] = tr;
  }
  return out;
}

export function flatten(obj: Tree, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out[key] = v;
    else Object.assign(out, flatten(v, key));
  }
  return out;
}

export const getKey = (tree: Tree, key: string): unknown => key.split(".").reduce<unknown>((n, p) => (n && typeof n === "object" ? (n as Tree)[p] : undefined), tree);
