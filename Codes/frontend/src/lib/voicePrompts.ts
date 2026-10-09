import type { Lang, VoiceSample } from "@/api/types";

/**
 * Built-in sample questions, used only when GET /api/demo/voice_samples returns nothing for a
 * language. Two per language: a meal question without an amount (the assistant asks one clarifying
 * question) and a walk what-if. Every dish is in the food table in all six languages.
 * Prompts are written in each language itself, so they stay the same whatever the UI language is.
 */
export const BUILTIN_PROMPTS: Record<Lang, string[]> = {
  "en-US": ["What happens to my glucose if I have rice and lentils for dinner?", "What if I walk 15 minutes after dinner?"],
  "es-ES": ["¿Qué pasa con mi glucosa si ceno arroz con lentejas?", "¿Y si camino 15 minutos después de cenar?"],
  "fr-FR": ["Que devient ma glycémie si je mange du riz et des lentilles ce soir ?", "Et si je marche 15 minutes après le dîner ?"],
  "de-DE": ["Was passiert mit meinem Blutzucker, wenn ich heute Abend Reis mit Linsen esse?", "Was wäre, wenn ich nach dem Abendessen 15 Minuten spazieren gehe?"],
  "it-IT": ["Cosa succede alla mia glicemia se stasera mangio riso e lenticchie?", "E se cammino 15 minuti dopo cena?"],
  "ja-JP": ["今夜ご飯とレンズ豆を食べたら血糖値はどうなりますか？", "夕食後に15分歩いたらどうなりますか？"],
};

/** Samples for one language: the backend's ones when present, else the built-in prompts. */
export function samplesFor(lang: Lang, fromBackend: VoiceSample[] | undefined): (VoiceSample & { builtin?: boolean })[] {
  const recorded = (fromBackend ?? []).filter((s) => s.lang === lang && s.prompt);
  if (recorded.length) return recorded;
  return (BUILTIN_PROMPTS[lang] ?? BUILTIN_PROMPTS["en-US"]).map((prompt) => ({ lang, prompt, builtin: true }));
}
