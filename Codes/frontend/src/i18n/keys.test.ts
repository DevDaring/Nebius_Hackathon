import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { KNOWN_DRIVER_KEYS, driverKey } from "@/lib/drivers";
import { DISCLOSURE_KINDS } from "@/api/types";
import { EN as en, allLocales, type Tree } from "./testLocales";
const has = (tree: Tree, key: string) => {
  let node: string | Tree | undefined = tree;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return false;
    node = node[part];
  }
  return typeof node === "string";
};

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "mocks" ? [] : sources(p);
    return /\.tsx?$/.test(f) && !f.endsWith(".test.ts") ? [p] : [];
  });
}

describe("every literal translation key used in the UI exists", () => {
  const root = join(__dirname, "..");
  const keys = new Set<string>();
  for (const file of sources(root)) {
    const text = readFileSync(file, "utf8");
    for (const m of text.matchAll(/\bt\(\s*"([a-zA-Z0-9_.]+)"/g)) keys.add(m[1]);
  }
  it("finds keys to check", () => expect(keys.size).toBeGreaterThan(100));
  for (const k of keys) {
    // i18next plurals live under key_one / key_other.
    it(`en-US has ${k}`, () => expect(has(en as Tree, k) || has(en as Tree, `${k}_other`)).toBe(true));
  }
});

describe("keys built at run time exist in en-US", () => {
  const dynamic = [
    ...DISCLOSURE_KINDS.map((k) => `chat.disclosure.${k}`),
    "chat.disclosure.other",
    ...["passed", "failed", "not_run", "blocked", "unavailable"].map((k) => `why.answer.state.${k}`),
    ...["today", "tomorrow", "yesterday", "onDate"].map((k) => `time.${k}`),
    ...["calibratedNow", "particleSpread", "forecastBand"].map((k) => `interval.${k}.label`),
    ...["calibratedNow", "particleSpread", "forecastBand"].map((k) => `interval.${k}.explain`),
    "nav.admin",
    ...["summary", "agent_multilingual"].map((k) => `trust.limitSource.${k}`),
    ...["calibratedNow", "particleSpread", "forecastBand"].map((k) => `interval.${k}.short`),
  ];
  for (const k of dynamic) it(k, () => expect(has(en, k), k).toBe(true));
});

describe("forecast driver names from the backend are translated in every locale", () => {
  for (const [name, data] of Object.entries(allLocales())) {
    it(name, () => {
      for (const k of KNOWN_DRIVER_KEYS) expect(has(data as Tree, `drivers.${k}`), `${name}: drivers.${k}`).toBe(true);
    });
  }
  it("label-derived names map onto the same keys", () => {
    expect(driverKey("meal_fat/protein/fibre")).toBe("meal_fat_protein_fibre");
    expect(driverKey("physiology_model's_high-risk_estimate")).toBe("physiology_model_s_high_risk_estimate");
    expect(driverKey("hours_since_your_last_reading")).toBe("hours_since_your_last_reading");
  });
});
