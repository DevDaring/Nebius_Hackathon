// Readers for the real evaluation reports (backend/reports/*.json, served by GET /api/reports/{name}).
// Every reader is defensive: missing keys give empty results or nulls, never invented numbers.
// The shapes follow the backend eval modules; alternative shapes are tolerated where cheap
// (e.g. levels as an object instead of a list).

import { isObj, readStrings, type Obj } from "./reports";

export const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

export const HORIZONS = [30, 60, 90, 120] as const;
export const LEVEL_ORDER = ["full", "4", "2", "1", "0"];

/** {"30": x, "60": y} -> [{h:30,v:x}, ...] sorted by horizon. */
export function byHorizon(v: unknown): { h: number; v: number }[] {
  if (!isObj(v)) return [];
  return Object.entries(v)
    .map(([h, x]) => ({ h: Number(h), v: num(x) }))
    .filter((p): p is { h: number; v: number } => Number.isFinite(p.h) && p.v !== null)
    .sort((a, b) => a.h - b.h);
}

const at = (v: unknown, h: number): number | null => (isObj(v) ? num(v[String(h)]) : num(v));

/** [point, lo, hi] arrays as written by the bootstrap helpers. */
export function ci(v: unknown): { est: number; lo: number; hi: number } | null {
  const a = arr(v).map(num);
  if (a.length >= 3 && a[0] !== null && a[1] !== null && a[2] !== null) return { est: a[0], lo: a[1], hi: a[2] };
  return null;
}
const ci2 = (v: unknown): { lo: number; hi: number } | null => {
  const a = arr(v).map(num);
  return a.length >= 2 && a[0] !== null && a[1] !== null ? { lo: a[0], hi: a[1] } : null;
};

export interface Metrics {
  nPatients: number | null;
  nForecasts: number | null;
  rmse: { h: number; v: number }[];
  rmse60: number | null;
  rmse60Ci: { est: number; lo: number; hi: number } | null;
  mard60: number | null;
  coverage: { h: number; v: number }[];
  width: { h: number; v: number }[];
  aurocHigh: number | null;
  aurocHighCi: { est: number; lo: number; hi: number } | null;
  auprcHigh: number | null;
  eceHigh: number | null;
  aurocLow: number | null;
  prevalenceLow: number | null;
  abstainRate: number | null;
  reconRmse: number | null;
  clarke: Record<string, number> | null;
}

export function metrics(o: unknown): Metrics {
  const r: Obj = isObj(o) ? o : {};
  const rec = isObj(r.reconstruction) ? r.reconstruction : {};
  const clarke = isObj(rec.clarke) ? Object.fromEntries(Object.entries(rec.clarke).filter(([, v]) => num(v) !== null)) : null;
  return {
    nPatients: num(r.n_patients),
    nForecasts: num(r.n_forecasts),
    rmse: byHorizon(r.rmse),
    rmse60: at(r.rmse, 60),
    rmse60Ci: ci(r.rmse60_ci),
    mard60: num(r.mard_60),
    coverage: byHorizon(r.coverage90),
    width: byHorizon(r.width90),
    aurocHigh: num(r.auroc_high),
    aurocHighCi: ci(r.auroc_high_ci),
    auprcHigh: num(r.auprc_high),
    eceHigh: num(r.ece_high),
    aurocLow: num(r.auroc_low),
    prevalenceLow: num(r.prevalence_low),
    abstainRate: num(r.abstain_rate),
    reconRmse: num(rec.rmse),
    clarke: clarke as Record<string, number> | null,
  };
}

export interface LowEvents {
  positiveWindows: number | null;
  prevalence: number | null;
  patientsWithLows: number | null;
  validated: boolean;
  note: string | null;
}

export interface LadderLevel extends Metrics {
  level: string;
  label: string;
  low: LowEvents;
  rmse60Abstained: number | null;
  rmse60Confident: number | null;
}

/** sensor_ladder.json levels (falls back to summary.json's ladder). */
export function ladderLevels(sensorLadder: unknown, summary?: unknown): LadderLevel[] {
  const pickLevels = (rep: unknown): Obj[] => {
    if (!isObj(rep)) return [];
    const v = rep.levels ?? rep.ladder;
    if (Array.isArray(v)) return v.filter(isObj);
    if (isObj(v)) return Object.entries(v).filter(([, x]) => isObj(x)).map(([k, x]) => ({ level: k, ...(x as Obj) }));
    return [];
  };
  let rows = pickLevels(sensorLadder);
  if (!rows.length) rows = pickLevels(summary);
  const out = rows.map((r) => {
    const m = metrics(r);
    // summary.json stores coverage90/width90 as the 60-min scalar.
    if (!m.coverage.length && num(r.coverage90) !== null) m.coverage = [{ h: 60, v: num(r.coverage90) as number }];
    if (!m.width.length && num(r.width90) !== null) m.width = [{ h: 60, v: num(r.width90) as number }];
    if (m.reconRmse === null) m.reconRmse = num(r.recon_rmse);
    const le = isObj(r.low_events) ? r.low_events : null;
    const av = isObj(r.abstain_vs_not) ? r.abstain_vs_not : {};
    return {
      ...m,
      level: String(r.level ?? ""),
      label: str(r.label) ?? String(r.level ?? ""),
      low: {
        positiveWindows: le ? num(le.positive_windows) : null,
        prevalence: le ? num(le.prevalence) : m.prevalenceLow,
        patientsWithLows: le ? num(le.patients_with_lows) : null,
        validated: le ? le.validated === true : false,
        note: le ? str(le.note) : null,
      },
      rmse60Abstained: num(av.rmse60_abstained),
      rmse60Confident: num(av.rmse60_confident),
    };
  });
  return out.filter((l) => l.level).sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level));
}

/* ---------------- reliability ---------------- */
export interface Bin {
  p: number;
  o: number;
  n: number;
}
const bins = (v: unknown): Bin[] =>
  arr(v)
    .filter(isObj)
    .map((b) => ({ p: num(b.mean_pred ?? b.p_pred ?? b.pred), o: num(b.observed ?? b.p_obs ?? b.obs), n: num(b.n ?? b.count) ?? 0 }))
    .filter((b): b is Bin => b.p !== null && b.o !== null);

export interface Reliability {
  level: string;
  high: Bin[];
  highRaw: Bin[];
  low: Bin[];
  eceHigh: number | null;
  eceHighRaw: number | null;
  eceLow: number | null;
}

export function reliability(report: unknown): Reliability[] {
  if (!isObj(report) || !isObj(report.levels)) return [];
  return Object.entries(report.levels)
    .filter(([, v]) => isObj(v))
    .map(([level, v]) => {
      const o = v as Obj;
      return {
        level,
        high: bins(o.high),
        highRaw: bins(o.high_uncalibrated),
        low: bins(o.low),
        eceHigh: num(o.ece_high),
        eceHighRaw: num(o.ece_high_uncalibrated),
        eceLow: num(o.ece_low),
      };
    })
    .sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level));
}

/* ---------------- baselines ---------------- */
export const METHOD_ORDER = ["persistence", "population_time_of_day", "personal_average", "lightgbm_sparse_only", "mechanistic_only", "full_hybrid"];

export interface BaselineTable {
  levels: { level: string; label: string }[];
  methods: string[];
  cell: (method: string, level: string) => Metrics | null;
  notes: string | null;
}

export function baselines(report: unknown): BaselineTable {
  const rows = isObj(report) ? arr(report.rows).filter(isObj) : [];
  const levels = rows.map((r) => ({ level: String(r.level ?? ""), label: str(r.label) ?? String(r.level ?? "") })).filter((l) => l.level);
  const map = new Map<string, Map<string, Metrics>>();
  const methods: string[] = [];
  for (const r of rows) {
    if (!isObj(r.methods)) continue;
    for (const [m, v] of Object.entries(r.methods)) {
      if (!isObj(v)) continue;
      if (!methods.includes(m)) methods.push(m);
      if (!map.has(m)) map.set(m, new Map());
      map.get(m)!.set(String(r.level), metrics(v));
    }
  }
  methods.sort((a, b) => (METHOD_ORDER.indexOf(a) + 1 || 99) - (METHOD_ORDER.indexOf(b) + 1 || 99));
  return { levels, methods, cell: (m, l) => map.get(m)?.get(l) ?? null, notes: isObj(report) ? str(report.notes) : null };
}

/* ---------------- next-best-prick ---------------- */
export interface NbpArm extends Metrics {
  name: string;
}
export interface PairedDiff {
  key: string;
  mean: number;
  lo: number;
  hi: number;
  improved: number | null;
  n: number | null;
}
export function nbp(report: unknown): { arms: NbpArm[]; diffs: PairedDiff[]; protocol: string | null } {
  if (!isObj(report)) return { arms: [], diffs: [], protocol: null };
  const arms = isObj(report.arms) ? Object.entries(report.arms).filter(([, v]) => isObj(v)).map(([name, v]) => ({ name, ...metrics(v) })) : [];
  const diffs: PairedDiff[] = [];
  if (isObj(report.paired_differences)) {
    for (const [key, v] of Object.entries(report.paired_differences)) {
      if (!isObj(v)) continue;
      const mean = num(v.mean_recon_rmse_change ?? v.mean ?? v.difference);
      const c = ci2(v.ci95);
      if (mean === null || !c) continue;
      diffs.push({ key, mean, lo: c.lo, hi: c.hi, improved: num(v.patients_improved), n: num(v.n_patients) });
    }
  }
  return { arms, diffs, protocol: str(report.protocol) };
}

/* ---------------- transfer ---------------- */
export interface TransferRow extends Metrics {
  /** Distinct people (one person can contribute several recordings, e.g. ShanghaiT2DM). */
  nPeople: number | null;
  nRecordings: number | null;
  test: string;
  train: string;
  setting: string;
  inDomain: boolean;
}
export function transfer(report: unknown): { rows: TransferRow[]; gaps: { key: string; v: number }[]; insulin: { key: string; m: Metrics }[]; protocol: string | null } {
  if (!isObj(report)) return { rows: [], gaps: [], insulin: [], protocol: null };
  const rows = arr(report.rows)
    .filter(isObj)
    .map((r) => ({
      ...metrics(r),
      nPeople: num(r.n_people),
      nRecordings: num(r.n_recordings),
      test: str(r.test) ?? "",
      train: str(r.train) ?? "",
      setting: str(r.setting) ?? "",
      inDomain: /in-domain/i.test(String(r.train ?? "")),
    }));
  const gaps = isObj(report.gap_rmse60)
    ? Object.entries(report.gap_rmse60)
        .map(([key, v]) => ({ key, v: num(v) }))
        .filter((g): g is { key: string; v: number } => g.v !== null)
    : [];
  const insulin = isObj(report.shanghai_by_insulin) ? Object.entries(report.shanghai_by_insulin).filter(([, v]) => isObj(v)).map(([key, v]) => ({ key, m: metrics(v) })) : [];
  return { rows, gaps, insulin, protocol: str(report.protocol) };
}

/* ---------------- subgroups ---------------- */
export interface SubgroupRow {
  dimension: string;
  group: string;
  n: number | null;
  rmse60: number | null;
  coverage60: number | null;
  auroc: number | null;
  ece: number | null;
  flagged: boolean;
}
export function subgroups(report: unknown): { rows: SubgroupRow[]; overall: { rmse60: number | null; coverage60: number | null; ece: number | null } | null; rule: string | null; title: string | null } {
  if (!isObj(report)) return { rows: [], overall: null, rule: null, title: null };
  const rows = arr(report.rows)
    .filter(isObj)
    .map((r) => ({
      dimension: str(r.dimension) ?? "",
      group: str(r.group) ?? "",
      n: num(r.n_patients),
      rmse60: num(r.rmse60),
      coverage60: num(r.coverage90_60),
      auroc: num(r.auroc_high),
      ece: num(r.ece_high),
      flagged: r.flagged === true,
    }));
  const o = isObj(report.overall) ? report.overall : null;
  return {
    rows,
    overall: o ? { rmse60: num(o.rmse60), coverage60: num(o.coverage90_60), ece: num(o.ece_high) } : null,
    rule: str(report.flag_rule),
    title: str(report.title),
  };
}

/* ---------------- error grid ---------------- */
export const ZONES = ["A", "B", "C", "D", "E"];
export interface GridLevel {
  level: string;
  label: string;
  virtual: Record<string, number>;
  forecast: Record<string, number>;
}
const zonesOf = (v: unknown): Record<string, number> => {
  if (!isObj(v)) return {};
  const out: Record<string, number> = {};
  for (const z of ZONES) {
    const x = num(v[z]);
    if (x !== null) out[z] = x;
  }
  // Percent (sum ~100) or fraction (sum ~1): normalise to percent.
  const sum = Object.values(out).reduce((a, b) => a + b, 0);
  if (sum > 0 && sum <= 1.5) for (const z of Object.keys(out)) out[z] *= 100;
  return out;
};
export function errorGrid(report: unknown): { levels: GridLevel[]; note: string | null } {
  if (!isObj(report) || !isObj(report.levels)) return { levels: [], note: null };
  const levels = Object.entries(report.levels)
    .filter(([, v]) => isObj(v))
    .map(([level, v]) => {
      const o = v as Obj;
      return { level, label: str(o.label) ?? level, virtual: zonesOf(o.virtual_cgm), forecast: zonesOf(o.forecast_60 ?? o.forecast) };
    })
    .sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level));
  return { levels, note: str(report.note) };
}

/* ---------------- calibration length ---------------- */
export function calibrationLength(report: unknown): { rows: (Metrics & { days: number })[]; protocol: string | null } {
  if (!isObj(report)) return { rows: [], protocol: null };
  const rows = arr(report.rows)
    .filter(isObj)
    .map((r) => ({ ...metrics(r), days: num(r.cgm_days) ?? NaN }))
    .filter((r) => Number.isFinite(r.days))
    .sort((a, b) => a.days - b.days);
  return { rows, protocol: str(report.protocol) };
}

/* ---------------- value of a recent finger-prick (sensor_ladder.recent_prick_value) ---------------- */
export interface RecentPrick {
  definition: string | null;
  nForecasts: number | null;
  nPatients: number | null;
  rows: { h: number; withPrick: number | null; without: number | null }[];
  /** RMSE(with) - RMSE(without) at 60 min, [point, lo, hi]; negative = the prick helps. */
  diff60: { est: number; lo: number; hi: number } | null;
}
export function recentPrick(report: unknown): RecentPrick | null {
  if (!isObj(report) || !isObj(report.recent_prick_value)) return null;
  const r = report.recent_prick_value;
  const w = byHorizon(r.rmse_with_prick);
  const wo = byHorizon(r.rmse_without);
  const hs = Array.from(new Set([...w, ...wo].map((p) => p.h))).sort((a, b) => a - b);
  const rows = hs.map((h) => ({ h, withPrick: w.find((p) => p.h === h)?.v ?? null, without: wo.find((p) => p.h === h)?.v ?? null }));
  const diff60 = ci(r.rmse60_difference_ci);
  if (!rows.length && !diff60) return null;
  return { definition: str(r.definition), nForecasts: num(r.n_forecasts), nPatients: num(r.n_patients), rows, diff60 };
}

/* ---------------- living uncertainty (sensor_ladder.by_hours_since_reading) ---------------- */
export interface HoursBin {
  key: string;
  /** Bin edges in hours; hi is null for the open-ended last bin ("8-+"). */
  lo: number | null;
  hi: number | null;
  n: number | null;
  rmse60: number | null;
  coverage60: number | null;
  width60: number | null;
}
export function hoursSinceReading(report: unknown): HoursBin[] {
  if (!isObj(report)) return [];
  return arr(report.by_hours_since_reading)
    .filter(isObj)
    .map((r) => {
      const key = String(r.hours_since_reading ?? r.bin ?? "").trim();
      const m = /^([\d.]+)\s*[-–]\s*([\d.]+|\+)?$/.exec(key);
      const lo = m ? Number(m[1]) : null;
      const hi = m && m[2] && m[2] !== "+" ? Number(m[2]) : null;
      return { key, lo, hi, n: num(r.n), rmse60: num(r.rmse60), coverage60: num(r.coverage90_60), width60: num(r.width90_60) };
    })
    .filter((b) => b.key && (b.rmse60 !== null || b.coverage60 !== null || b.width60 !== null));
}

/* ---------------- multilingual agent evaluation (agent_multilingual.json) ---------------- */
/** A rate with its denominator: k of n runs; rate = k / n as written by the report. */
export interface Frac {
  n: number;
  k: number;
  rate: number;
}
/** {n, k, rate} -> Frac; null when n or k is missing (the rate alone is never shown without its denominator). */
export function frac(v: unknown): Frac | null {
  if (!isObj(v)) return null;
  const n = num(v.n);
  const k = num(v.k);
  if (n === null || k === null || n <= 0) return null;
  return { n, k, rate: num(v.rate) ?? k / n };
}

/** Headline checks of the multilingual agent suite, in display order. */
export const ML_METRICS = [
  "pass",
  "numbers_ok",
  "inappropriate_refusal",
  "justified_refusal",
  "unnecessary_clarification",
  "clarification_when_required",
  "engine_result_invariance_across_languages",
] as const;
export type MlMetric = (typeof ML_METRICS)[number];
/** Checks where a lower rate is the better result. */
export const ML_LOWER_BETTER: readonly MlMetric[] = ["inappropriate_refusal", "unnecessary_clarification"];

export interface AgentMultilingual {
  generatedAt: string | null;
  suite: string | null;
  split: string | null;
  mode: string | null;
  repeats: number | null;
  languages: string[];
  model: string | null;
  provider: string | null;
  /** NeMo Guardrails on (true), off (false) or not stated (null). */
  guardrails: boolean | null;
  nRuns: number | null;
  nCases: number | null;
  metrics: Partial<Record<MlMetric, Frac>>;
  perLanguage: { lang: string; pass: Frac | null; localeOk: Frac | null }[];
  /** Weakest category first. */
  perCategory: { key: string; frac: Frac }[];
  latency: { p50: number | null; p95: number | null };
  tokens: { prompt: number | null; completion: number | null };
  costUsd: number | null;
  scoring: string | null;
  limitations: string[];
}

export function agentMultilingual(report: unknown): AgentMultilingual | null {
  if (!isObj(report)) return null;
  const m = isObj(report.metrics) ? report.metrics : {};
  const metrics: Partial<Record<MlMetric, Frac>> = {};
  for (const k of ML_METRICS) {
    const f = frac(m[k]);
    if (f) metrics[k] = f;
  }
  const languages = arr(report.languages).filter((x): x is string => typeof x === "string");
  const pl = isObj(report.per_language) ? report.per_language : {};
  const order = Array.from(new Set([...languages, ...Object.keys(pl)]));
  const perLanguage = order
    .map((lang) => {
      const v = isObj(pl[lang]) ? (pl[lang] as Obj) : {};
      return { lang, pass: frac(v.pass), localeOk: frac(v.locale_ok) };
    })
    .filter((r) => r.pass || r.localeOk);
  const perCategory = isObj(report.per_category)
    ? Object.entries(report.per_category)
        .map(([key, v]) => ({ key, frac: frac(v) }))
        .filter((c): c is { key: string; frac: Frac } => c.frac !== null)
        .sort((a, b) => a.frac.rate - b.frac.rate || a.key.localeCompare(b.key))
    : [];
  const models = isObj(report.models) ? report.models : {};
  const lat = isObj(report.latency_ms) ? report.latency_ms : {};
  const tok = isObj(report.tokens) ? report.tokens : {};
  return {
    generatedAt: str(report.generated_at),
    suite: str(report.suite),
    split: str(report.split),
    mode: str(report.mode),
    repeats: num(report.repeats),
    languages,
    model: str(models.chat),
    provider: str(models.provider),
    guardrails: typeof models.guardrails === "boolean" ? models.guardrails : null,
    nRuns: num(report.n_runs),
    nCases: num(report.n_cases),
    metrics,
    perLanguage,
    perCategory,
    latency: { p50: num(lat.p50), p95: num(lat.p95) },
    tokens: { prompt: num(tok.prompt), completion: num(tok.completion) },
    costUsd: num(report.cost_usd),
    scoring: str(report.scoring),
    limitations: readStrings(report, "limitations"),
  };
}

/** Collect free-text caveats/notes/protocols from any report, for the limitations list. */
export function textOf(report: unknown, key: string): string | null {
  return isObj(report) ? str(report[key]) : null;
}

/* ---------------- nested-protocol report blocks (rendered only when present) ---------------- */

/** People / recordings / forecast windows of a report block (people != recordings in ShanghaiT2DM). */
export function counts(o: unknown): { people: number | null; recordings: number | null; windows: number | null } {
  if (!isObj(o)) return { people: null, recordings: null, windows: null };
  return {
    people: num(o.n_people) ?? num(o.n_patients),
    recordings: num(o.n_recordings),
    windows: num(o.n_forecast_windows) ?? num(o.n_forecasts),
  };
}

export interface WidthRow {
  h: number;
  withPricks: number | null;
  without: number | null;
  diff: number | null;
  ci: { lo: number; hi: number } | null;
  covWith: number | null;
  covWithout: number | null;
}
export interface WidthBlock {
  key: string;
  subset: string | null;
  people: number | null;
  recordings: number | null;
  windows: number | null;
  rows: WidthRow[];
}

/** sensor_ladder.paired_band_width: band width at the same origins with 2 pricks/day vs no glucose. */
export function pairedWidth(sensorLadder: unknown): { definition: string | null; blocks: WidthBlock[] } {
  const pw = isObj(sensorLadder) && isObj(sensorLadder.paired_band_width) ? sensorLadder.paired_band_width : null;
  if (!pw) return { definition: null, blocks: [] };
  const blocks: WidthBlock[] = [];
  for (const [key, b] of Object.entries(pw)) {
    if (!isObj(b) || !isObj(b.by_horizon)) continue;
    const rows = Object.entries(b.by_horizon)
      .filter(([, v]) => isObj(v))
      .map(([h, v]) => {
        const o = v as Obj;
        return {
          h: Number(h),
          withPricks: num(o.mean_width_with_pricks),
          without: num(o.mean_width_without_glucose),
          diff: num(o.paired_difference),
          ci: ci2(o.paired_difference_ci95),
          covWith: num(o.coverage90_with_pricks),
          covWithout: num(o.coverage90_without_glucose),
        };
      })
      .filter((r) => Number.isFinite(r.h))
      .sort((a, b) => a.h - b.h);
    const c = counts(b);
    blocks.push({ key, subset: str(b.subset), people: c.people, recordings: c.recordings, windows: c.windows, rows });
  }
  return { definition: str(pw.definition), blocks };
}

export interface ExploratoryRow {
  level: string;
  h: number;
  rmse: number | null;
  rmseCi: { est: number; lo: number; hi: number } | null;
  coverage: number | null;
  width: number | null;
  people: number | null;
  windows: number | null;
}

/** 180/240-min horizons (exploratory): sensor_ladder levels[].exploratory_horizons, else summary ladder[].exploratory. */
export function exploratoryHorizons(sensorLadder: unknown, summary?: unknown): { note: string | null; validatedMin: number | null; rows: ExploratoryRow[] } {
  const rows: ExploratoryRow[] = [];
  let note: string | null = null;
  let validatedMin: number | null = null;
  const fromLevels = (rep: unknown, key: "levels" | "ladder", field: "exploratory_horizons" | "exploratory") => {
    if (!isObj(rep) || !Array.isArray(rep[key])) return;
    for (const lv of (rep[key] as unknown[]).filter(isObj)) {
      const ex = lv[field];
      if (!isObj(ex)) continue;
      const hz = field === "exploratory_horizons" ? (isObj(ex.horizons) ? ex.horizons : null) : ex;
      if (field === "exploratory_horizons") {
        note = note ?? str(ex.note);
        validatedMin = validatedMin ?? num(ex.validated_horizon_min);
      }
      if (!hz) continue;
      for (const [h, v] of Object.entries(hz)) {
        if (!isObj(v)) continue;
        rows.push({
          level: String(lv.level ?? ""),
          h: Number(h),
          rmse: num(v.rmse),
          rmseCi: ci(v.rmse_ci),
          coverage: num(v.coverage90),
          width: num(v.width90),
          people: num(v.n_people),
          windows: num(v.n_forecast_windows),
        });
      }
    }
  };
  fromLevels(sensorLadder, "levels", "exploratory_horizons");
  if (!rows.length) fromLevels(summary, "ladder", "exploratory");
  if (validatedMin === null && isObj(summary)) validatedMin = num(summary.validated_horizon_min);
  rows.sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level) || a.h - b.h);
  return { note, validatedMin, rows: rows.filter((r) => r.level && Number.isFinite(r.h)) };
}

export interface ChangeRow {
  key: string;
  oldV: number | null;
  newV: number | null;
  delta: number | null;
}

/** summary.protocol_change: headline numbers before and after the nested evaluation protocol. */
export function protocolChange(summary: unknown): { description: string | null; oldSource: string | null; note: string | null; rows: ChangeRow[] } | null {
  const pc = isObj(summary) && isObj(summary.protocol_change) ? summary.protocol_change : null;
  if (!pc) return null;
  const flatNums = (o: unknown, prefix = ""): Record<string, number | null> => {
    const out: Record<string, number | null> = {};
    if (!isObj(o)) return out;
    for (const [k, v] of Object.entries(o)) {
      const key = prefix ? `${prefix}.${k}` : k;
      if (isObj(v)) Object.assign(out, flatNums(v, key));
      else out[key] = num(v);
    }
    return out;
  };
  const nw = flatNums(pc.new);
  const od = flatNums(pc.old);
  const dl = flatNums(pc.delta_new_minus_old);
  const keys = Array.from(new Set([...Object.keys(nw), ...Object.keys(od)]));
  return {
    description: str(pc.description),
    oldSource: str(pc.old_source),
    note: str(pc.note),
    rows: keys.map((k) => ({ key: k, oldV: od[k] ?? null, newV: nw[k] ?? null, delta: dl[k] ?? (od[k] != null && nw[k] != null ? (nw[k] as number) - (od[k] as number) : null) })),
  };
}

export interface PairedBaseline {
  method: string;
  hybrid: number | null;
  baseline: number | null;
  diff: number | null;
  ci: { lo: number; hi: number } | null;
  excludesZero: boolean | null;
  people: number | null;
}

/** baselines.paired_vs_full_hybrid_60min: RMSE(hybrid) - RMSE(baseline) on the same windows, CI over people. */
export function pairedBaselines(report: unknown): PairedBaseline[] {
  const pb = isObj(report) && isObj(report.paired_vs_full_hybrid_60min) ? report.paired_vs_full_hybrid_60min : null;
  if (!pb) return [];
  return Object.entries(pb)
    .filter(([, v]) => isObj(v))
    .map(([method, v]) => {
      const o = v as Obj;
      return {
        method,
        hybrid: num(o.rmse60_full_hybrid),
        baseline: num(o.rmse60_baseline),
        diff: num(o.difference),
        ci: ci2(o.difference_ci95),
        excludesZero: typeof o.ci_excludes_zero === "boolean" ? o.ci_excludes_zero : null,
        people: counts(o).people,
      };
    })
    .sort((a, b) => METHOD_ORDER.indexOf(a.method) - METHOD_ORDER.indexOf(b.method));
}

/* ---------------- limitations (one consolidated list) ---------------- */
export interface LimitationGroup {
  source: "summary" | "agent_multilingual";
  items: string[];
}

const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ").replace(/[.\s]+$/, "").trim();

/**
 * A report can state the same qualification twice: a `limitations` / `caveats` list AND a `caveat`
 * paragraph that is those list items joined. Keep each qualification exactly once: the list is
 * preferred; the paragraph is kept only when it says something the list does not. Exact repeats
 * across reports are dropped; nothing else is filtered out.
 */
export function consolidateLimitations(summary: unknown, agent: unknown): LimitationGroup[] {
  const seen = new Set<string>();
  const take = (items: (string | null | undefined)[]) =>
    items.filter((x): x is string => typeof x === "string" && x.trim().length > 0).filter((x) => {
      const k = norm(x);
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
  const fromReport = (r: unknown): string[] => {
    if (!isObj(r)) return [];
    const list = [...readStrings(r, "limitations"), ...readStrings(r, "caveats")];
    const para = str(r.caveat);
    if (!para) return list;
    if (!list.length) return [para];
    // Drop the paragraph when it is only the list items run together.
    let rest = norm(para);
    for (const item of list) rest = rest.replace(norm(item), " ");
    const covered = rest.replace(/[\s.;:,]+/g, "").length === 0;
    return covered ? list : [...list, para];
  };
  const groups: LimitationGroup[] = [
    { source: "summary", items: take(fromReport(summary)) },
    { source: "agent_multilingual", items: take(fromReport(agent)) },
  ];
  return groups.filter((g) => g.items.length > 0);
}
