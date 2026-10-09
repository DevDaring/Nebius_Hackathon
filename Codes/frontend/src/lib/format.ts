import i18next, { type TFunction } from "i18next";
import type { Lang } from "@/api/types";
import { isEnglish } from "./langPrefs";

/**
 * Every number, date and time shown in the UI goes through Intl with the active language: decimal
 * comma in es-ES, fr-FR, de-DE and it-IT, decimal point in en-US and ja-JP, 24-hour clock everywhere
 * except en-US. Values stay canonical (numbers, ISO strings) until this display boundary.
 */

/** Intl locale with Western digits for every UI language. */
export const intlLocale = (lang: Lang | string) => `${lang || "en-US"}-u-nu-latn`;

/** 12-hour clock only for US English; the other release languages use 24 hours. */
export const uses12h = (lang: Lang | string) => lang === "en-US";
const hourCycle = (lang: Lang | string) => (uses12h(lang) ? "h12" : "h23");

/** Parse contract times. ISO strings without an offset are local replay-clock time. */
export function parseTime(iso: string): Date {
  // Clock-only values ("06:30", used by the daily profile) map onto a fixed reference day.
  const hm = /^(\d{1,2}):(\d{2})$/.exec(iso);
  if (hm) return new Date(2000, 0, 1, Number(hm[1]), Number(hm[2]));
  return new Date(iso);
}

const toDate = (iso: string | Date) => (typeof iso === "string" ? parseTime(iso) : iso);

export function formatClock(iso: string | Date, lang: Lang | string): string {
  const d = toDate(iso);
  if (Number.isNaN(d.getTime())) return typeof iso === "string" ? iso : "";
  return new Intl.DateTimeFormat(intlLocale(lang), { hour: "numeric", minute: "2-digit", hourCycle: hourCycle(lang) }).format(d);
}

export function formatHour(d: Date, lang: Lang | string): string {
  return new Intl.DateTimeFormat(intlLocale(lang), { hour: "numeric", hourCycle: hourCycle(lang) }).format(d);
}

export function formatDateTime(iso: string, lang: Lang | string): string {
  const d = parseTime(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(intlLocale(lang), { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hourCycle: hourCycle(lang) }).format(d);
}

/** Short weekday + date, e.g. "Thu, Oct 9" / "jeu. 9 oct." / "10月9日(木)". */
export function formatDayDate(iso: string | Date, lang: Lang | string): string {
  const d = toDate(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(intlLocale(lang), { weekday: "short", day: "numeric", month: "short" }).format(d);
}

/** Whole calendar days from the replay clock's date to the date of `iso` (0 = same day, 1 = next day). */
export function dayOffset(iso: string | Date, replayNow: string | Date): number {
  const a = toDate(replayNow);
  const b = toDate(iso);
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) return 0;
  const da = Date.UTC(a.getFullYear(), a.getMonth(), a.getDate());
  const db = Date.UTC(b.getFullYear(), b.getMonth(), b.getDate());
  return Math.round((db - da) / 86_400_000);
}

/**
 * A time relative to the replay clock (never the wall clock): "11:00 AM tomorrow", "19:45 today",
 * or "11:00 on Thu, Oct 9" further away. Without a replay date the plain clock time is returned.
 */
export function formatReplayTime(t: TFunction, iso: string, replayNow: string | null | undefined, lang: Lang | string): string {
  const time = formatClock(iso, lang);
  if (!replayNow) return time;
  const off = dayOffset(iso, replayNow);
  if (off === 0) return t("time.today", { time });
  if (off === 1) return t("time.tomorrow", { time });
  if (off === -1) return t("time.yesterday", { time });
  return t("time.onDate", { time, date: formatDayDate(iso, lang) });
}

/** Localised number (decimal comma where the language uses one). `digits` fixes the decimals. */
export function formatNumber(v: number, lang: Lang | string, digits?: number, opts: Intl.NumberFormatOptions = {}): string {
  if (!Number.isFinite(v)) return "—";
  const o: Intl.NumberFormatOptions = digits === undefined ? { maximumFractionDigits: 2, ...opts } : { minimumFractionDigits: digits, maximumFractionDigits: digits, ...opts };
  return new Intl.NumberFormat(intlLocale(lang), o).format(v);
}

/** The active UI language (falls back to en-US before i18next is initialised, e.g. in unit tests). */
export const currentLang = (): string => i18next.language || "en-US";

/** Drop-in for Number.toFixed in display code: same rounding, localised decimal separator, no grouping. */
export const fixed = (v: number, digits: number, lang: Lang | string = currentLang()) => formatNumber(v, lang, digits, { useGrouping: false });

/** Localised integer with grouping ("12,400" / "12.400" / "12 400"). */
export const formatInt = (v: number, lang: Lang | string) => formatNumber(Math.round(v), lang, 0);

/** 0..1 → whole percent. */
export const pct = (p: number) => Math.round(p * 100);

/** Number of times out of 10 for a probability. */
export const outOfTen = (p: number) => Math.round(Math.min(1, Math.max(0, p)) * 10);

/** Probability as a localised natural frequency: "about 7 times out of 10". */
export function freqText(t: TFunction, p: number): string {
  if (!Number.isFinite(p)) return "";
  if (p < 0.05) return t("freq.rare");
  if (p >= 0.95) return t("freq.always");
  return t("freq.n", { count: outOfTen(p) });
}

/** Signed number with a true minus sign, localised: "+12", "−3,3", "±0". */
export const signed = (n: number, digits = 0, lang: Lang | string = currentLang()) => {
  const v = Number(n.toFixed(digits));
  return `${v > 0 ? "+" : v < 0 ? "−" : "±"}${formatNumber(Math.abs(v), lang, digits, { useGrouping: false })}`;
};

export const round1 = (n: number) => Math.round(n * 10) / 10;

/** Format a metric that may be a fraction (0..1) as a percent, else as-is (localised decimals). */
export function fmtMetric(v: unknown, key = "", lang: Lang | string = currentLang()): string {
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    const looksRate = /rate|coverage|auroc|auprc|tir|share|frac|ece|pct|zone/i.test(key);
    if (looksRate && v >= 0 && v <= 1 && !/auroc|auprc|ece/i.test(key)) return `${formatNumber(v * 100, lang, v * 100 < 10 ? 1 : 0)}%`;
    if (Number.isInteger(v)) return String(v);
    return formatNumber(v, lang, Math.abs(v) < 1 ? 2 : 1);
  }
  if (typeof v === "boolean") return v ? "✓" : "—";
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

const MEAL_NAMES = ["breakfast", "lunch", "dinner", "snack"];
/** Localise the generic meal names the backend logs ("Lunch", "Snack", ...); other names pass through. */
export function mealName(t: TFunction, name: string | undefined | null): string {
  const k = (name ?? "").trim().toLowerCase();
  return MEAL_NAMES.includes(k) ? t(`mealNames.${k}`) : (name ?? "");
}

/**
 * Display text for a food swap: the backend's localised `label` when it really is localised,
 * else the English label (flagged so the caller can set lang="en" on it).
 */
export function swapLabel(sw: { label?: string; label_en: string }, lang: string): { text: string; english: boolean } {
  if (sw.label && (isEnglish(lang) || sw.label !== sw.label_en)) return { text: sw.label, english: false };
  return { text: sw.label_en, english: !isEnglish(lang) };
}
