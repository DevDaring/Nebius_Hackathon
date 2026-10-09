import { describe, expect, it } from "vitest";
import { EN, TRANSLATED, flatten, localeTree, type Tree } from "./testLocales";

const placeholders = (s: string) => (s.match(/\{\{\s*\w+\s*\}\}/g) ?? []).map((p) => p.replace(/\s/g, "")).sort();

const base = flatten(EN);

describe("en-US source", () => {
  it("has no empty strings", () => {
    for (const [k, v] of Object.entries(base)) expect(v.trim().length, `en-US:${k}`).toBeGreaterThan(0);
  });
});

describe("i18n key parity with en-US", () => {
  for (const name of TRANSLATED) {
    const data = localeTree(name);
    it(`${name} exists`, () => expect(data, `${name}.json is missing`).not.toBeNull());
    if (!data) continue;
    const flat = flatten(data as Tree);
    it(`${name} has exactly the English keys`, () => {
      const missing = Object.keys(base).filter((k) => !(k in flat));
      const extra = Object.keys(flat).filter((k) => !(k in base));
      expect({ missing, extra }).toEqual({ missing: [], extra: [] });
    });
    it(`${name} keeps every placeholder`, () => {
      for (const [k, v] of Object.entries(base)) {
        if (!(k in flat)) continue; // reported by the key test above
        expect(placeholders(flat[k]), `${name}:${k}`).toEqual(placeholders(v));
      }
    });
    it(`${name} has no empty strings`, () => {
      for (const [k, v] of Object.entries(flat)) expect(v.trim().length, `${name}:${k}`).toBeGreaterThan(0);
    });
  }
});

/**
 * Emergency guidance is location-neutral: the UI language says nothing about where the user is, so
 * no locale may hard-code a country's emergency number (108, 112, 911, 999, 000, 15, 118, 119, 110…)
 * in the disclaimer or in any safety / emergency string.
 */
describe("emergency text names no country-specific number", () => {
  const EMERGENCY_NUMBER = /(?<![\d.,])(?:108|112|911|999|000|061|113|118|119|110|15|17|18)(?![\d.,])/;
  const isEmergencyKey = (k: string) => /^(footer\.disclaimer|safety\.|voice\.emergency)|emergency|call108|callLocal/i.test(k);
  for (const name of ["en-US", ...TRANSLATED]) {
    const data = name === "en-US" ? EN : localeTree(name);
    if (!data) continue;
    it(name, () => {
      const flat = flatten(data as Tree);
      const keys = Object.keys(flat).filter(isEmergencyKey);
      expect(keys).toContain("footer.disclaimer");
      for (const k of keys) expect(flat[k], `${name}:${k}`).not.toMatch(EMERGENCY_NUMBER);
    });
  }
});
