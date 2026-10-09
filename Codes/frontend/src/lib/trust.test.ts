import { describe, expect, it } from "vitest";
import { allLocales } from "@/i18n/testLocales";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { agentMultilingual, frac, hoursSinceReading, ladderLevels, ML_METRICS, recentPrick, transfer } from "./trust";
import { mockAgentMultilingual } from "@/mocks/reports";

const realReport = (() => {
  try {
    return JSON.parse(readFileSync(join(__dirname, "../../../backend/reports/agent_multilingual.json"), "utf8")) as unknown;
  } catch {
    return null;
  }
})();

describe("trust readers never crash and never invent numbers", () => {
  it("handles missing reports", () => {
    expect(ladderLevels(null)).toEqual([]);
    expect(recentPrick(undefined)).toBeNull();
    expect(recentPrick({ levels: [] })).toBeNull();
    expect(hoursSinceReading({})).toEqual([]);
    expect(agentMultilingual(null)).toBeNull();
    expect(agentMultilingual("x")).toBeNull();
    expect(transfer(null).rows).toEqual([]);
  });

  it("reads sensor_ladder.recent_prick_value", () => {
    const r = recentPrick({
      recent_prick_value: { definition: "d", n_forecasts: 10, n_patients: 3, rmse_with_prick: { "30": 10, "60": 15 }, rmse_without: { "60": 25, "30": 20 }, rmse60_difference_ci: [-10, -14, -6] },
    });
    expect(r?.rows).toEqual([
      { h: 30, withPrick: 10, without: 20 },
      { h: 60, withPrick: 15, without: 25 },
    ]);
    expect(r?.diff60).toEqual({ est: -10, lo: -14, hi: -6 });
    expect(r?.nPatients).toBe(3);
  });

  it("reads by_hours_since_reading bins, including the open last bin", () => {
    const b = hoursSinceReading({
      by_hours_since_reading: [
        { hours_since_reading: "0-1.5", n: 5, rmse60: 20, coverage90_60: 0.9, width90_60: 60 },
        { hours_since_reading: "8-+", n: 7, rmse60: 30, coverage90_60: 0.88, width90_60: 90 },
        { hours_since_reading: "4-8", n: 0, rmse60: null, coverage90_60: null, width90_60: null },
      ],
    });
    expect(b.map((x) => [x.lo, x.hi])).toEqual([
      [0, 1.5],
      [8, null],
    ]);
    expect(b[1].width60).toBe(90);
  });

  it("reads people vs recordings on transfer rows", () => {
    const t = transfer({ rows: [{ test: "ShanghaiT2DM", train: "x (in-domain)", n_people: 100, n_recordings: 109, n_patients: 109 }] });
    expect(t.rows[0].nPeople).toBe(100);
    expect(t.rows[0].nRecordings).toBe(109);
    expect(t.rows[0].inDomain).toBe(true);
  });

  it("keeps a rate only together with its denominator", () => {
    expect(frac({ n: 174, k: 108, rate: 0.621 })).toEqual({ n: 174, k: 108, rate: 0.621 });
    expect(frac({ n: 4, k: 1 })).toEqual({ n: 4, k: 1, rate: 0.25 });
    expect(frac({ rate: 0.9 })).toBeNull();
    expect(frac({ n: 0, k: 0, rate: 0 })).toBeNull();
  });

  it("reads an agent_multilingual report: every metric with k / n, weakest category first", () => {
    const r = agentMultilingual({
      split: "heldout",
      mode: "live",
      languages: ["en-US", "ja-JP"],
      models: { chat: "nvidia/model-x", provider: "p", guardrails: true },
      n_runs: 10,
      n_cases: 5,
      metrics: { pass: { n: 10, k: 6, rate: 0.6 }, numbers_ok: { n: 10, k: 10, rate: 1 }, inappropriate_refusal: { n: 4, k: 0, rate: 0 }, weird: { n: 1, k: 1, rate: 1 }, justified_refusal: { rate: 0.5 } },
      per_language: { "ja-JP": { pass: { n: 5, k: 2, rate: 0.4 }, locale_ok: { n: 5, k: 5, rate: 1 } }, "en-US": { pass: { n: 5, k: 4, rate: 0.8 } } },
      per_category: { normal: { n: 4, k: 3, rate: 0.75 }, injection: { n: 4, k: 1, rate: 0.25 }, broken: { rate: 1 } },
      latency_ms: { p50: 3272, p95: 7625 },
      cost_usd: null,
      scoring: "deterministic checks only",
      limitations: ["Synthetic persona."],
    });
    expect(r).not.toBeNull();
    expect(Object.keys(r!.metrics)).toEqual(["pass", "numbers_ok", "inappropriate_refusal"]);
    expect(r!.metrics.pass).toEqual({ n: 10, k: 6, rate: 0.6 });
    expect(r!.perLanguage.map((x) => [x.lang, x.pass?.k, x.localeOk?.k ?? null])).toEqual([
      ["en-US", 4, null],
      ["ja-JP", 2, 5],
    ]);
    expect(r!.perCategory.map((c) => c.key)).toEqual(["injection", "normal"]);
    expect(r).toMatchObject({ model: "nvidia/model-x", guardrails: true, split: "heldout", mode: "live", nRuns: 10, nCases: 5, costUsd: null, latency: { p50: 3272, p95: 7625 }, limitations: ["Synthetic persona."] });
  });

  it.runIf(!!realReport)("reads the real held-out report, including its weak results", () => {
    const r = agentMultilingual(realReport)!;
    expect(r.split).toBe("heldout");
    expect(r.mode).toBe("live");
    expect(r.guardrails).toBe(true);
    for (const k of ML_METRICS) {
      const f = r.metrics[k];
      expect(f, k).toBeDefined();
      expect(f!.k).toBeLessThanOrEqual(f!.n);
    }
    expect(r.metrics.pass!.rate).toBeLessThan(1);
    expect(r.perLanguage.map((x) => x.lang)).toEqual(["en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"]);
    expect(r.perCategory[0].frac.rate).toBeLessThanOrEqual(r.perCategory[r.perCategory.length - 1].frac.rate);
    expect(r.limitations.length).toBeGreaterThan(0);
  });

  it("the offline mock report reads as mock, never as live", () => {
    const r = agentMultilingual(mockAgentMultilingual())!;
    expect(r.mode).toBe("mock");
    expect(r.model).toMatch(/mock/);
    expect(r.limitations.join(" ")).toMatch(/mock/i);
    for (const k of ML_METRICS) expect(r.metrics[k], k).toBeDefined();
    expect(r.perLanguage).toHaveLength(6);
  });
});

describe("dynamic Trust labels are translated in every locale", () => {
  type Tree = { [k: string]: string | Tree };
  const get = (tree: Tree, key: string) => key.split(".").reduce<string | Tree | undefined>((n, p) => (typeof n === "object" && n ? n[p] : undefined), tree);
  const keys = [
    ...ML_METRICS.map((k) => `trust.ml.metric.${k}`),
    ...ML_METRICS.filter((k) => k !== "pass").map((k) => `trust.ml.hint.${k}`),
    ...Object.keys((mockAgentMultilingual().per_category ?? {}) as object).map((k) => `trust.ml.cat.${k}`),
    ...(realReport && typeof realReport === "object" ? Object.keys((realReport as { per_category?: object }).per_category ?? {}) : []).map((k) => `trust.ml.cat.${k}`),
    ...["summary", "agent_multilingual"].map((k) => `trust.limitSource.${k}`),
    ...["live", "fixture", "template", "rules", "other"].map((k) => `voice.source.${k}`),
  ];
  for (const [name, data] of Object.entries(allLocales())) {
    it(name, () => {
      for (const k of keys) expect(typeof get(data as Tree, k), `${name}: ${k}`).toBe("string");
    });
  }
});
