import type { GlucoseUnit, Lang } from "@/api/types";
import { formatNumber } from "./format";

/**
 * The single place where glucose units are converted. Components never convert ad hoc, and the
 * language model never converts medical values: canonical values are mg/dL everywhere else.
 */

/** mmol/L to mg/dL for glucose (the same factor the backend uses). */
export const MMOL_TO_MGDL = 18.016;

/** Plausible glucometer ranges per unit (anything outside is almost certainly a typo). */
export const UNIT_RANGE: Record<GlucoseUnit, { min: number; max: number; step: number; decimals: number }> = {
  "mg/dL": { min: 20, max: 600, step: 1, decimals: 0 },
  "mmol/L": { min: 1.1, max: 33.3, step: 0.1, decimals: 1 },
};

export function toMgdl(value: number, unit: GlucoseUnit): number {
  return unit === "mmol/L" ? value * MMOL_TO_MGDL : value;
}

/** Canonical mg/dL to a display unit (no rounding: rounding happens in formatGlucose). */
export function fromMgdl(mgdl: number, unit: GlucoseUnit): number {
  return unit === "mmol/L" ? mgdl / MMOL_TO_MGDL : mgdl;
}

/** A glucose value with its unit, always explicit and localised: "154 mg/dL", "8,5 mmol/L". */
export function formatGlucose(mgdl: number, unit: GlucoseUnit, lang: Lang | string): string {
  if (!Number.isFinite(mgdl)) return `— ${unit}`;
  return `${formatNumber(fromMgdl(mgdl, unit), lang, UNIT_RANGE[unit].decimals, { useGrouping: false })} ${unit}`;
}

/** A glucose range with its unit: "116–192 mg/dL", "6,4–10,7 mmol/L". */
export function formatGlucoseRange(lo: number, hi: number, unit: GlucoseUnit, lang: Lang | string): string {
  const d = UNIT_RANGE[unit].decimals;
  const f = (v: number) => formatNumber(fromMgdl(v, unit), lang, d, { useGrouping: false });
  return `${f(lo)}–${f(hi)} ${unit}`;
}

/** Full-width digits and separators (common with Japanese input methods) to ASCII. */
function normaliseDigits(raw: string): string {
  return raw.replace(/[０-９]/g, (c) => String(c.charCodeAt(0) - 0xff10)).replace(/[．。]/g, ".").replace(/，/g, ",");
}

/**
 * Parse what the user typed. Accepts a decimal comma ("5,6"), a decimal point and full-width digits;
 * returns null for anything that is not a single finite number (e.g. "1,234.5" or "5,6,7" are rejected
 * as ambiguous rather than guessed).
 */
export function parseReading(raw: string): number | null {
  const s = normaliseDigits(raw.trim());
  const norm = /^\d+,\d+$/.test(s) ? s.replace(",", ".") : s;
  if (!/^\d+(\.\d+)?$/.test(norm)) return null;
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
}

export type ReadingCheck = { ok: true; value: number; mgdl: number } | { ok: false; reason: "empty" | "unit" | "format" | "range" };

/** Validate a manual reading. Both a value and an explicit unit are required. */
export function checkReading(raw: string, unit: GlucoseUnit | null): ReadingCheck {
  if (!raw.trim()) return { ok: false, reason: "empty" };
  if (!unit) return { ok: false, reason: "unit" };
  const v = parseReading(raw);
  if (v === null) return { ok: false, reason: "format" };
  const r = UNIT_RANGE[unit];
  if (v < r.min || v > r.max) return { ok: false, reason: "range" };
  return { ok: true, value: v, mgdl: toMgdl(v, unit) };
}
