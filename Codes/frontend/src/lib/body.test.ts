import { describe, expect, it } from "vitest";
import type { BodyVariant, OrganKey } from "@/api/types";
import {
  ORGAN_KEYS,
  PALETTE,
  SCALE_FLOOR,
  at,
  auraIntensity,
  biggestChanges,
  clampIndex,
  formatOrganValue,
  glucoseColor,
  glucoseZone,
  indexForMinutes,
  intensity,
  isExploratory,
  lastValidatedIndex,
  liverColor,
  liverDirection,
  mealIndex,
  minutesAt,
  muscleIntensity,
  organIntensities,
  organScales,
  organValues,
  peakDelta,
  percentile,
  playIndex,
  topActive,
} from "./body";

const N = 49;
const flat = (v: number) => Array.from({ length: N }, () => v);
const ramp = (from: number, to: number) => Array.from({ length: N }, (_, i) => from + ((to - from) * i) / (N - 1));
function variant(over: Partial<Record<OrganKey, number[]>> = {}, blood = flat(150)): BodyVariant {
  const fluxes = {} as BodyVariant["fluxes"];
  for (const k of ORGAN_KEYS) {
    const q50 = over[k] ?? flat(0.1);
    fluxes[k] = { q10: q50.map((v) => v - Math.abs(v) * 0.2), q50, q90: q50.map((v) => v + Math.abs(v) * 0.2) };
  }
  return { forecast_id: "f", blood: { q05: blood.map((v) => v - 30), q50: blood, q95: blood.map((v) => v + 30) }, fluxes, learned_correction: flat(0) };
}

describe("percentile", () => {
  it("interpolates and ignores non-finite values", () => {
    expect(percentile([0, 10], 50)).toBe(5);
    expect(percentile([1, 2, 3, 4, 5, NaN], 100)).toBe(5);
    expect(percentile([], 95)).toBe(0);
  });
});

describe("intensity mapping", () => {
  it("divides by the 95th percentile of q90 across baseline + scenario, clamped to 0..1", () => {
    const base = variant({ stomach: ramp(0, 50) });
    const scen = variant({ stomach: ramp(0, 100) });
    const scales = organScales({ baseline: base, scenario: scen });
    // q90 = 1.2 * q50; the 95th percentile of the pooled q90 values is close to the top of the scenario ramp.
    expect(scales.stomach).toBeGreaterThan(90);
    expect(scales.stomach).toBeLessThanOrEqual(120);
    expect(intensity(50, scales.stomach)).toBeGreaterThan(0.4);
    expect(intensity(1000, scales.stomach)).toBe(1);
    expect(intensity(0, scales.stomach)).toBe(0);
  });
  it("never scales a tiny flow up to a full glow (per-organ floor)", () => {
    const scales = organScales({ baseline: variant({ exercise_uptake: flat(0.1) }), scenario: null });
    expect(scales.exercise_uptake).toBe(SCALE_FLOOR.exercise_uptake);
    expect(intensity(0.1, scales.exercise_uptake)).toBeLessThan(0.3);
  });
  it("uses |value| for the liver, so taking up glucose glows as much as releasing it", () => {
    const scales = organScales({ baseline: variant({ liver: ramp(-1.5, 0.5) }), scenario: null });
    expect(scales.liver).toBeGreaterThanOrEqual(1.5);
    expect(intensity(-1, scales.liver)).toBeCloseTo(intensity(1, scales.liver));
    expect(liverDirection(-1)).toBe("takingUp");
    expect(liverDirection(0.4)).toBe("releasing");
    expect(liverDirection(0.001)).toBe("steady");
    expect(liverColor(0.4)).toEqual(PALETTE.teal);
    expect(liverColor(-0.4)).toEqual(PALETTE.marigold);
  });
  it("makes the walk scenario's muscles brighter than the baseline's", () => {
    const base = variant({ exercise_uptake: flat(0.08), insulin_uptake: flat(3.5) });
    const walk = variant({ exercise_uptake: flat(0.55), insulin_uptake: flat(3.2) });
    const view = { baseline: base, scenario: walk };
    const scales = organScales(view);
    const nb = organIntensities(organValues(view, 10, 0), scales);
    const nw = organIntensities(organValues(view, 10, 1), scales);
    expect(muscleIntensity(nw)).toBeGreaterThan(muscleIntensity(nb));
  });
  it("crossfades organ values between baseline and scenario", () => {
    const view = { baseline: variant({ stomach: flat(10) }), scenario: variant({ stomach: flat(30) }) };
    expect(organValues(view, 3, 0).stomach).toBe(10);
    expect(organValues(view, 3, 0.5).stomach).toBe(20);
    expect(organValues(view, 3, 1).stomach).toBe(30);
    expect(organValues({ baseline: view.baseline, scenario: null }, 3, 1).stomach).toBe(10);
  });
  it("interpolates between 5-minute steps and clamps at the ends", () => {
    expect(at([0, 10, 20], 0.5)).toBe(5);
    expect(at([0, 10, 20], -3)).toBe(0);
    expect(at([0, 10, 20], 9)).toBe(20);
    expect(at(undefined, 1)).toBe(0);
  });
  it("ranks the most active organs (4 labels on a phone)", () => {
    const n = Object.fromEntries(ORGAN_KEYS.map((k, i) => [k, i / 10])) as Record<OrganKey, number>;
    expect(topActive(n, 4)).toEqual(["unexplained", "exercise_uptake", "insulin_uptake", "insulin"]);
    expect(topActive(n, 2, ["unexplained"])).toEqual(["exercise_uptake", "insulin_uptake"]);
  });
  it("builds a faint aura from the unexplained drift and the learned correction", () => {
    expect(auraIntensity(0, 0, 0.5)).toBe(0);
    expect(auraIntensity(0, 25, 0.5)).toBeCloseTo(0.6);
    expect(auraIntensity(5, 100, 0.5)).toBe(1);
  });
});

describe("blood colour mapping", () => {
  const close = (a: number[], b: number[]) => a.every((v, i) => Math.abs(v - b[i]) <= 1);
  it("is violet below 70, teal in range and coral above 180", () => {
    expect(close(glucoseColor(45), PALETTE.violet)).toBe(true);
    expect(close(glucoseColor(125), PALETTE.teal)).toBe(true);
    expect(close(glucoseColor(260), PALETTE.coral)).toBe(true);
  });
  it("blends smoothly around the thresholds", () => {
    const mid = glucoseColor(180);
    for (let c = 0; c < 3; c++) expect(mid[c]).toBe(Math.round((PALETTE.teal[c] + PALETTE.coral[c]) / 2));
    const low = glucoseColor(70);
    for (let c = 0; c < 3; c++) expect(low[c]).toBe(Math.round((PALETTE.violet[c] + PALETTE.teal[c]) / 2));
    // monotone towards coral as glucose rises
    expect(glucoseColor(175)[0]).toBeLessThan(glucoseColor(185)[0]);
  });
  it("names the zone", () => {
    expect(glucoseZone(69)).toBe("low");
    expect(glucoseZone(70)).toBe("in");
    expect(glucoseZone(180)).toBe("in");
    expect(glucoseZone(181)).toBe("high");
  });
});

describe("time index and exploratory logic", () => {
  it("maps indices to minutes and back", () => {
    expect(minutesAt(0)).toBe(0);
    expect(minutesAt(24)).toBe(120);
    expect(indexForMinutes(42)).toBe(8);
    expect(indexForMinutes(999)).toBe(48);
    expect(clampIndex(-2)).toBe(0);
    expect(clampIndex(NaN)).toBe(0);
    expect(clampIndex(60)).toBe(48);
  });
  it("marks everything beyond 2 h as exploratory", () => {
    expect(isExploratory(24)).toBe(false);
    expect(isExploratory(25)).toBe(true);
    expect(isExploratory(48)).toBe(true);
    expect(lastValidatedIndex(120)).toBe(24);
  });
  it("places the dinner on the timeline (and moves it with a timing change)", () => {
    expect(mealIndex(null)).toBeNull();
    expect(mealIndex({ carbs: 75, minutes_from_now: 30 })).toBe(6);
    expect(mealIndex({ carbs: 75, minutes_from_now: 30 }, { shift_min: -30 })).toBe(0);
    expect(mealIndex({ carbs: 75, minutes_from_now: 10 }, { shift_min: -30 })).toBeNull();
  });
  it("plays 4 h in 12 s", () => {
    expect(playIndex(0, 0)).toBe(0);
    expect(playIndex(6000, 0)).toBe(24);
    expect(playIndex(20000, 10)).toBe(48);
  });
});

describe("scenario differences", () => {
  it("finds the organs that change most and the peak difference within 2 h", () => {
    const base = variant({ exercise_uptake: flat(0.08), insulin_uptake: flat(3.5) }, ramp(150, 190));
    const walk = variant({ exercise_uptake: flat(0.55), insulin_uptake: flat(3.2) }, ramp(150, 180));
    const view = { baseline: base, scenario: walk, validated_horizon_min: 120 };
    const ch = biggestChanges(view, organScales(view));
    expect(ch[0].key).toBe("exercise_uptake");
    expect(ch[0].delta).toBeCloseTo(0.47);
    const pd = peakDelta(view)!;
    expect(pd).toBeLessThan(0);
    expect(peakDelta({ ...view, scenario: null })).toBeNull();
  });
});

describe("value formatting", () => {
  it("rounds grams, keeps decimals for slow flows and uses a real minus sign", () => {
    expect(formatOrganValue("stomach", 51.7)).toBe("52");
    expect(formatOrganValue("liver", -1.26)).toBe("−1.3");
    expect(formatOrganValue("exercise_uptake", 0.534)).toBe("0.53");
    expect(formatOrganValue("liver", -0.001)).toBe("0");
  });
});
