import { describe, expect, it } from "vitest";
import i18n from "i18next";
import { EN, localeTree } from "@/i18n/testLocales";
import { dayOffset, fmtMetric, formatClock, formatNumber, formatReplayTime, freqText, outOfTen, pct, signed, swapLabel } from "./format";
import { MMOL_TO_MGDL, checkReading, formatGlucose, formatGlucoseRange, fromMgdl, parseReading, toMgdl } from "./units";

const t = i18n.createInstance();
const fr = localeTree("fr-FR");
await t.init({
  lng: "en-US",
  fallbackLng: "en-US",
  resources: { "en-US": { translation: EN }, ...(fr ? { "fr-FR": { translation: fr } } : {}) },
  interpolation: { escapeValue: false },
});
const en = t.getFixedT("en-US");

describe("frequency text", () => {
  it("rounds to times out of 10", () => {
    expect(outOfTen(0.68)).toBe(7);
    expect(outOfTen(0.04)).toBe(0);
    expect(outOfTen(1.4)).toBe(10);
  });
  it("uses natural English", () => {
    expect(freqText(en, 0.7)).toBe("about 7 times out of 10");
    expect(freqText(en, 0.1)).toBe("about 1 time out of 10");
    expect(freqText(en, 0.02)).toBe("less than 1 time out of 10");
    expect(freqText(en, 0.97)).toBe("almost every time");
  });
  it.runIf(!!fr)("localises with Western digits", () => {
    const s = freqText(t.getFixedT("fr-FR"), 0.7);
    expect(s).toContain("7");
    expect(s).toContain("10");
    expect(s).not.toBe("about 7 times out of 10");
  });
});

describe("number formatting follows the language (Intl)", () => {
  it("percent and sign", () => {
    expect(pct(0.456)).toBe(46);
    expect(signed(12.4)).toBe("+12");
    expect(signed(-3.26, 1)).toBe("−3.3");
    expect(signed(-3.26, 1, "de-DE")).toBe("−3,3");
    expect(signed(0)).toBe("±0");
  });
  it("uses a decimal comma in es/fr/de/it and a point in en/ja", () => {
    for (const l of ["es-ES", "fr-FR", "de-DE", "it-IT"]) expect(formatNumber(7.2, l, 1), l).toBe("7,2");
    for (const l of ["en-US", "ja-JP"]) expect(formatNumber(7.2, l, 1), l).toBe("7.2");
  });
  it("formats metrics defensively", () => {
    expect(fmtMetric(0.912, "coverage90")).toBe("91%");
    expect(fmtMetric(0.85, "auroc_high")).toBe("0.85");
    expect(fmtMetric(0.85, "auroc_high", "fr-FR")).toBe("0,85");
    expect(fmtMetric(18.64, "rmse_60")).toBe("18.6");
    expect(fmtMetric(18.64, "rmse_60", "de-DE")).toBe("18,6");
    expect(fmtMetric(undefined)).toBe("—");
    expect(fmtMetric("CGMacros")).toBe("CGMacros");
  });
});

describe("clock: 12-hour only in en-US, 24-hour elsewhere", () => {
  const evening = "2026-10-08T19:30:00";
  it("en-US", () => expect(formatClock(evening, "en-US")).toMatch(/7:30\s?PM/i));
  it("others", () => {
    for (const l of ["es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"]) expect(formatClock(evening, l), l).toMatch(/19[:.h]30/);
  });
});

describe("times relative to the replay clock (regression: next-day reading shown without a day)", () => {
  const replayNow = "2026-10-08T19:30:00"; // replay clock at 7:30 p.m.
  it("counts calendar days from the replay date, not the wall clock", () => {
    expect(dayOffset("2026-10-08T22:00:00", replayNow)).toBe(0);
    expect(dayOffset("2026-10-09T11:00:00", replayNow)).toBe(1);
    expect(dayOffset("2026-10-07T23:59:00", replayNow)).toBe(-1);
    expect(dayOffset("2026-10-11T08:00:00", replayNow)).toBe(3);
  });
  it("labels an 11:00 a.m. reading after a 7:30 p.m. replay time as tomorrow", () => {
    const s = formatReplayTime(en, "2026-10-09T11:00:00", replayNow, "en-US");
    expect(s).toMatch(/11:00\s?AM tomorrow/i);
  });
  it("labels same-day times as today and far times with weekday + date", () => {
    expect(formatReplayTime(en, "2026-10-08T21:15:00", replayNow, "en-US")).toMatch(/9:15\s?PM today/i);
    const far = formatReplayTime(en, "2026-10-11T08:00:00", replayNow, "en-US");
    expect(far).toMatch(/8:00\s?AM on /);
    expect(far).toMatch(/Oct/);
    expect(far).toMatch(/Sun/);
  });
  it("uses the 24-hour clock with the day label in other languages", () => {
    expect(formatReplayTime(en, "2026-10-09T11:00:00", replayNow, "de-DE")).toMatch(/^11:00 tomorrow$/);
  });
  it("falls back to the plain clock without a replay date", () => {
    expect(formatReplayTime(en, "2026-10-09T11:00:00", null, "en-US")).toMatch(/^11:00\s?AM$/i);
  });
});

describe("glucose units are converted only in lib/units", () => {
  it("round-trips mg/dL and mmol/L", () => {
    expect(toMgdl(5.6, "mmol/L")).toBeCloseTo(5.6 * MMOL_TO_MGDL, 6);
    expect(fromMgdl(toMgdl(7.2, "mmol/L"), "mmol/L")).toBeCloseTo(7.2, 6);
    expect(fromMgdl(154, "mg/dL")).toBe(154);
  });
  it("always shows the unit, localised", () => {
    expect(formatGlucose(154, "mg/dL", "en-US")).toBe("154 mg/dL");
    expect(formatGlucose(154, "mmol/L", "en-US")).toBe("8.5 mmol/L");
    expect(formatGlucose(154, "mmol/L", "fr-FR")).toBe("8,5 mmol/L");
    expect(formatGlucoseRange(116, 192, "mg/dL", "de-DE")).toBe("116–192 mg/dL");
    expect(formatGlucoseRange(116, 192, "mmol/L", "es-ES")).toBe("6,4–10,7 mmol/L");
  });
  it("parses decimal commas and full-width digits, rejects ambiguity", () => {
    expect(parseReading("5,6")).toBe(5.6);
    expect(parseReading("5.6")).toBe(5.6);
    expect(parseReading("１５４")).toBe(154);
    expect(parseReading("1,234.5")).toBeNull();
    expect(parseReading("5,6,7")).toBeNull();
    expect(checkReading("7,2", "mmol/L")).toMatchObject({ ok: true, value: 7.2 });
    expect(checkReading("154", null)).toEqual({ ok: false, reason: "unit" });
  });
});

describe("swapLabel", () => {
  it("uses the backend's localised label, else the English one (flagged)", () => {
    expect(swapLabel({ label: "Cambiar arroz blanco por integral", label_en: "Swap white rice for brown rice" }, "es-ES")).toEqual({ text: "Cambiar arroz blanco por integral", english: false });
    expect(swapLabel({ label: "Swap white rice for brown rice", label_en: "Swap white rice for brown rice" }, "es-ES")).toEqual({ text: "Swap white rice for brown rice", english: true });
    expect(swapLabel({ label_en: "Swap white rice for brown rice" }, "en-US")).toEqual({ text: "Swap white rice for brown rice", english: false });
  });
});
