import { fixed } from "./format";
// Pure helpers for the glass-body view: how simulated organ flows map to glow, colour and time.
// Kept free of React and three.js so they are unit-tested and shared by the 3-D and the 2-D views.
import type { BodyVariant, BodyView, MealInput, OrganKey, Scenario } from "@/api/types";

export const STEP_MIN = 5;
export const N_STEPS = 48; // 4 h after now, every 5 min (49 points with "now")
export const TARGET = { lo: 70, hi: 180 } as const;

/** Display order (also the order of the organ list and the text view). */
export const ORGAN_KEYS: OrganKey[] = ["stomach", "intestine", "gut_to_blood", "liver", "pancreas", "insulin", "insulin_uptake", "exercise_uptake", "unexplained"];

/** Selectable things in the body: the nine simulated flows plus blood (the validated forecast). */
export type BodyPart = OrganKey | "blood";

/**
 * Smallest denominator per organ, in the organ's own unit. Without a floor a near-zero flow
 * (e.g. muscles at rest, ~0.1 mg/dL per min) would be scaled up to a full glow.
 */
export const SCALE_FLOOR: Record<OrganKey, number> = {
  stomach: 20,
  intestine: 20,
  gut_to_blood: 1,
  liver: 0.5,
  pancreas: 0.5,
  insulin: 5,
  insulin_uptake: 1,
  exercise_uptake: 0.4,
  unexplained: 0.5,
};

export const clamp01 = (v: number) => (Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0);

/** Linear-interpolated percentile (p in 0..100). */
export function percentile(values: number[], p: number): number {
  const v = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) return 0;
  const pos = (Math.min(100, Math.max(0, p)) / 100) * (v.length - 1);
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return v[lo] + (v[hi] - v[lo]) * (pos - lo);
}

/**
 * Robust scale per organ: the 95th percentile of that organ's |q90| (and |q10| for the signed
 * flows) across the baseline and the scenario, never below SCALE_FLOOR. Baseline and scenario
 * share one scale so their glows are comparable.
 */
export function organScales(view: Pick<BodyView, "baseline" | "scenario">): Record<OrganKey, number> {
  const out = {} as Record<OrganKey, number>;
  const variants = [view.baseline, view.scenario].filter(Boolean) as BodyVariant[];
  for (const k of ORGAN_KEYS) {
    const vals: number[] = [];
    for (const v of variants) {
      const s = v.fluxes[k];
      if (!s) continue;
      for (const x of s.q90) vals.push(Math.abs(x));
      if (k === "liver" || k === "unexplained") for (const x of s.q10) vals.push(Math.abs(x));
    }
    out[k] = Math.max(SCALE_FLOOR[k], percentile(vals, 95));
  }
  return out;
}

/** Glow intensity 0..1 of one value: |value| / scale, clamped (the liver's sign is shown by colour). */
export const intensity = (value: number, scale: number) => (scale > 0 ? clamp01(Math.abs(value) / scale) : 0);

/** Value of a series at a fractional time index (linear interpolation, clamped to the ends). */
export function at(series: number[] | undefined, tf: number): number {
  if (!series || !series.length) return 0;
  const x = Math.min(series.length - 1, Math.max(0, tf));
  const i = Math.floor(x);
  const f = x - i;
  const a = series[i];
  const b = series[Math.min(series.length - 1, i + 1)];
  return a + (b - a) * f;
}

/** q50 of every organ at a (fractional) time index, crossfaded between baseline (mix 0) and scenario (mix 1). */
export function organValues(view: Pick<BodyView, "baseline" | "scenario">, tf: number, mix = 0): Record<OrganKey, number> {
  const out = {} as Record<OrganKey, number>;
  const m = view.scenario ? clamp01(mix) : 0;
  for (const k of ORGAN_KEYS) {
    const a = at(view.baseline.fluxes[k]?.q50, tf);
    const b = view.scenario ? at(view.scenario.fluxes[k]?.q50, tf) : a;
    out[k] = a + (b - a) * m;
  }
  return out;
}

export function organIntensities(values: Record<OrganKey, number>, scales: Record<OrganKey, number>): Record<OrganKey, number> {
  const out = {} as Record<OrganKey, number>;
  for (const k of ORGAN_KEYS) out[k] = intensity(values[k], scales[k]);
  return out;
}

/** Large muscles: mainly "muscles working" (exercise), with a softer glow from insulin-driven uptake. */
export const muscleIntensity = (n: Record<OrganKey, number>) => clamp01(Math.max(n.exercise_uptake, 0.45 * n.insulin_uptake));

/** Faint aura for what the physiology model cannot explain: |unexplained| plus the learned correction. */
export function auraIntensity(unexplained: number, learnedCorrection: number, scale: number): number {
  // learned correction is in mg/dL (a level, not a rate): 25 mg/dL counts as a full aura.
  return clamp01(0.6 * intensity(unexplained, scale) + 0.6 * clamp01(Math.abs(learnedCorrection) / 25));
}

export type LiverDirection = "releasing" | "takingUp" | "steady";
/** Positive liver flow = releasing glucose into the blood, negative = taking it up. */
export function liverDirection(v: number): LiverDirection {
  if (!Number.isFinite(v) || Math.abs(v) < 0.02) return "steady";
  return v > 0 ? "releasing" : "takingUp";
}

/** Organs ranked by how active they are now (most active first). */
export function topActive(n: Record<OrganKey, number>, count: number, exclude: OrganKey[] = []): OrganKey[] {
  return ORGAN_KEYS.filter((k) => !exclude.includes(k))
    .sort((a, b) => n[b] - n[a] || ORGAN_KEYS.indexOf(a) - ORGAN_KEYS.indexOf(b))
    .slice(0, count);
}

/* ---------------- colour ---------------- */
export type RGB = [number, number, number];
export const PALETTE = {
  marigold: [242, 163, 58] as RGB,
  teal: [43, 179, 163] as RGB,
  coral: [229, 96, 77] as RGB,
  violet: [124, 108, 240] as RGB,
  moon: [237, 235, 255] as RGB,
  paper: [250, 246, 239] as RGB,
};

export const mixRGB = (a: RGB, b: RGB, f: number): RGB => {
  const t = clamp01(f);
  return [Math.round(a[0] + (b[0] - a[0]) * t), Math.round(a[1] + (b[1] - a[1]) * t), Math.round(a[2] + (b[2] - a[2]) * t)];
};
const smooth = (e0: number, e1: number, x: number) => {
  const t = clamp01((x - e0) / (e1 - e0));
  return t * t * (3 - 2 * t);
};

/**
 * Blood colour from glucose relative to the 70-180 target: violet below 70, teal inside, coral
 * above 180, with a smooth 20 mg/dL blend centred on each threshold.
 */
export function glucoseColor(g: number): RGB {
  if (!Number.isFinite(g)) return PALETTE.teal;
  if (g < 125) return mixRGB(PALETTE.violet, PALETTE.teal, smooth(TARGET.lo - 10, TARGET.lo + 10, g));
  return mixRGB(PALETTE.teal, PALETTE.coral, smooth(TARGET.hi - 10, TARGET.hi + 10, g));
}
export type Zone = "low" | "in" | "high";
export const glucoseZone = (g: number): Zone => (g < TARGET.lo ? "low" : g > TARGET.hi ? "high" : "in");

export const rgbHex = (c: RGB) => `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
export const rgbCss = (c: RGB, a = 1) => `rgb(${c[0]} ${c[1]} ${c[2]} / ${a})`;

/** Liver colour by direction: teal glow while releasing glucose, marigold while taking it up. */
export const liverColor = (v: number): RGB => (v >= 0 ? PALETTE.teal : PALETTE.marigold);

/* ---------------- time ---------------- */
export const minutesAt = (i: number) => Math.round(i) * STEP_MIN;
/** Points beyond the validated horizon (120 min) are exploratory. */
export const isExploratory = (i: number, validatedMin = 120) => minutesAt(i) > validatedMin;
/** Last validated index (24 for 120 min). */
export const lastValidatedIndex = (validatedMin = 120, n = N_STEPS) => Math.min(n, Math.floor(validatedMin / STEP_MIN));
export const indexForMinutes = (min: number, n = N_STEPS) => Math.min(n, Math.max(0, Math.round(min / STEP_MIN)));
/** Clamp and round a time index into 0..n. */
export const clampIndex = (i: number, n = N_STEPS) => Math.min(n, Math.max(0, Math.round(Number.isFinite(i) ? i : 0)));

/** Where the dinner sits on the 4-hour timeline (null when no dinner or outside the window). */
export function mealIndex(meal: MealInput | null | undefined, scenario?: Scenario | null, n = N_STEPS): number | null {
  if (!meal) return null;
  const m = (meal.minutes_from_now ?? 30) + (scenario?.shift_min ?? 0);
  if (m < 0 || m > n * STEP_MIN) return null;
  return indexForMinutes(m, n);
}

/** Play-through: the timeline advances `n` steps in `durationMs` (12 s for 4 h by default). */
export function playIndex(elapsedMs: number, startIndex: number, durationMs = 12_000, n = N_STEPS): number {
  return Math.min(n, startIndex + (Math.max(0, elapsedMs) / durationMs) * n);
}

/* ---------------- scenario differences ---------------- */
export interface OrganChange {
  key: OrganKey;
  /** scenario - baseline (q50) at the index where the scaled difference is largest. */
  delta: number;
  index: number;
  /** |delta| / organ scale. */
  rel: number;
}

/** Organs whose simulated flow changes most between the baseline and the scenario. */
export function biggestChanges(view: Pick<BodyView, "baseline" | "scenario">, scales: Record<OrganKey, number>, max = 2, minRel = 0.08): OrganChange[] {
  const s = view.scenario;
  if (!s) return [];
  const out: OrganChange[] = [];
  for (const k of ORGAN_KEYS) {
    if (k === "unexplained") continue;
    const a = view.baseline.fluxes[k]?.q50 ?? [];
    const b = s.fluxes[k]?.q50 ?? [];
    let best: OrganChange | null = null;
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      const d = b[i] - a[i];
      const rel = Math.abs(d) / scales[k];
      if (!best || rel > best.rel) best = { key: k, delta: d, index: i, rel };
    }
    if (best && best.rel >= minRel) out.push(best);
  }
  return out.sort((x, y) => y.rel - x.rel).slice(0, max);
}

/** Difference of the blood-glucose peak (q50) within the validated 2 h, scenario minus baseline. */
export function peakDelta(view: Pick<BodyView, "baseline" | "scenario" | "validated_horizon_min">): number | null {
  if (!view.scenario) return null;
  const n = lastValidatedIndex(view.validated_horizon_min) + 1;
  const peak = (a: number[]) => Math.max(...a.slice(0, n));
  return peak(view.scenario.blood.q50) - peak(view.baseline.blood.q50);
}

/** Number shown for an organ value: grams and insulin as whole numbers, flows with 1-2 decimals. */
export function formatOrganValue(key: OrganKey, v: number): string {
  if (!Number.isFinite(v)) return "—";
  if (Math.abs(v) < 0.005) return "0";
  if (key === "stomach" || key === "intestine" || key === "insulin") return String(Math.round(v));
  const a = Math.abs(v);
  const s = a >= 10 ? fixed(v, 0) : a >= 1 ? fixed(v, 1) : fixed(v, 2);
  return s.replace("-", "−");
}
