import { describe, expect, it } from "vitest";
import { bodyBloodBand, historyBandAt, intervalKeys, kindAtTime, stateBand } from "./intervals";
import { EN, getKey } from "@/i18n/testLocales";

/** The case from the brief: one estimate (154 mg/dL), two cards, two different intervals. */
const now = "2026-10-08T19:30:00";
const state = {
  now,
  replay: { now, day: 7, offset_min: 0, max_offset_min: 720, label_en: "", mode: "replay" as const },
  estimate: 154,
  band: { lo: 116, hi: 192 }, // conformal present-state band
};
const vcgm = { t: ["2026-10-08T19:25:00", now], q05: [140, 142], q25: [148, 149], q50: [153, 154], q75: [158, 159], q95: [166, 167] };
const view = { t: [now, "2026-10-08T19:35:00", "2026-10-08T19:40:00"] };

describe("interval definitions are kept apart (regression: 116–192 vs 142–167 at 154 mg/dL)", () => {
  it("the stage tile binds the calibrated present-state band", () => {
    const b = stateBand(state);
    expect(b).toMatchObject({ kind: "calibratedNow", lo: 116, hi: 192, calibrated: true, at: now, horizonMin: 0, level: 0.9 });
  });
  it("the chart/body value at now is the raw particle spread, labelled as uncalibrated", () => {
    const h = historyBandAt(vcgm, 1, now);
    expect(h).toMatchObject({ kind: "particleSpread", lo: 142, hi: 167, calibrated: false, horizonMin: 0 });
    const body = bodyBloodBand(view, 0, 142, 167);
    expect(body.kind).toBe("particleSpread");
    expect(body.calibrated).toBe(false);
  });
  it("never merges the two: same time, same estimate, different kinds and labels", () => {
    const a = stateBand(state);
    const b = bodyBloodBand(view, 0, 142, 167);
    expect(a.at).toBe(b.at);
    expect(a.kind).not.toBe(b.kind);
    expect(intervalKeys(a.kind).short).not.toBe(intervalKeys(b.kind).short);
    // the numbers are passed through untouched (no averaging)
    expect([a.lo, a.hi, b.lo, b.hi]).toEqual([116, 192, 142, 167]);
  });
  it("later body steps and future chart points are forecast bands", () => {
    expect(bodyBloodBand(view, 2, 130, 200)).toMatchObject({ kind: "forecastBand", horizonMin: 10, calibrated: true });
    const n = Date.parse(now);
    expect(kindAtTime(n, n)).toBe("particleSpread");
    expect(kindAtTime(n + 5 * 60_000, n)).toBe("forecastBand");
  });
  it("every kind has an English label, short form with both bounds, and an explanation", () => {
    for (const kind of ["calibratedNow", "particleSpread", "forecastBand"] as const) {
      const k = intervalKeys(kind);
      expect(typeof getKey(EN, k.label)).toBe("string");
      expect(typeof getKey(EN, k.explain)).toBe("string");
      const short = getKey(EN, k.short) as string;
      expect(short).toContain("{{lo}}");
      expect(short).toContain("{{hi}}");
    }
  });
});
