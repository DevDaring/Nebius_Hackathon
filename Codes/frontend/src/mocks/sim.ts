// Offline mock twin. Produces contract-shaped, plausible glucose data for three synthetic
// composite personas. None of these numbers are model output; they exist so the UI can be
// demonstrated without the backend, and the UI marks every mock session with a pill.

import type {
  Band,
  Driver,
  Forecast,
  Ladder,
  MealEvent,
  MealInput,
  NextBestPrick,
  Prob,
  Quantiles,
  Reading,
  TwinState,
} from "@/api/types";

export const STEP_MIN = 5;
const MIN = 60_000;

// ---------- small numeric helpers ----------
export function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function erf(x: number) {
  // Abramowitz-Stegun 7.1.26
  const s = Math.sign(x);
  const ax = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * ax);
  const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-ax * ax);
  return s * y;
}
export const normCdf = (z: number) => 0.5 * (1 + erf(z / Math.SQRT2));
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const r1 = (v: number) => Math.round(v * 10) / 10;

export function fmtLocal(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:00`;
}

// ---------- personas ----------
export interface MealPlan {
  hour: number; // local clock, fractional
  name: string;
  carbs: number;
  fibre: number;
  protein: number;
  fat: number;
}

export interface PersonaModel {
  id: string;
  seed: number;
  fasting: number;
  dawn: number;
  gain: number; // mg/dL per g carb at peak
  tp: number; // minutes to peak
  meals: MealPlan[];
  stepsPerDay: number;
  sleep: { start: string; end: string };
}

export const MODELS: PersonaModel[] = [
  {
    id: "kolkata-shopkeeper",
    seed: 12,
    fasting: 124,
    dawn: 14,
    gain: 1.12,
    tp: 62,
    stepsPerDay: 5200,
    sleep: { start: "23:30", end: "06:30" },
    meals: [
      { hour: 8.5, name: "Muri with tea", carbs: 48, fibre: 3, protein: 6, fat: 8 },
      { hour: 13.75, name: "Rice, dal, macher jhol", carbs: 92, fibre: 7, protein: 26, fat: 14 },
      { hour: 17.5, name: "Tea and biscuits", carbs: 24, fibre: 1, protein: 3, fat: 6 },
      { hour: 21.0, name: "Rice, dal, aloo posto", carbs: 82, fibre: 6, protein: 14, fat: 16 },
    ],
  },
  {
    id: "mysuru-teacher",
    seed: 27,
    fasting: 113,
    dawn: 10,
    gain: 1.02,
    tp: 58,
    stepsPerDay: 7400,
    sleep: { start: "22:30", end: "05:45" },
    meals: [
      { hour: 7.75, name: "Idli, sambar", carbs: 52, fibre: 5, protein: 11, fat: 6 },
      { hour: 13.25, name: "Ragi mudde, sambar, rice", carbs: 86, fibre: 10, protein: 15, fat: 9 },
      { hour: 17.25, name: "Filter coffee, banana", carbs: 30, fibre: 3, protein: 2, fat: 3 },
      { hour: 20.75, name: "Chapati, palya, curd rice", carbs: 70, fibre: 8, protein: 14, fat: 11 },
    ],
  },
  {
    id: "lucknow-retiree",
    seed: 41,
    fasting: 128,
    dawn: 18,
    gain: 1.18,
    tp: 66,
    stepsPerDay: 3900,
    sleep: { start: "22:45", end: "05:30" },
    meals: [
      { hour: 8.0, name: "Paratha, curd", carbs: 55, fibre: 4, protein: 10, fat: 15 },
      { hour: 13.5, name: "Roti, dal, rice, sabzi", carbs: 88, fibre: 9, protein: 18, fat: 13 },
      { hour: 17.75, name: "Tea, namkeen", carbs: 22, fibre: 2, protein: 4, fat: 9 },
      { hour: 20.5, name: "Roti, paneer, dal", carbs: 66, fibre: 8, protein: 22, fat: 18 },
    ],
  },
];

/** Replay clock origin: today at 19:30 local (replay day 7). Fixed per page load so the demo is reproducible. */
export const NOW: Date = (() => {
  const d = new Date();
  d.setHours(19, 30, 0, 0);
  return d;
})();
export const REPLAY_DAY0 = 7;
export const MAX_OFFSET_MIN = 720;

/** Per-persona replay offset in minutes (POST /advance moves it; reset clears it). */
export const replayOffsets = new Map<string, number>();
export const offsetOf = (id: string) => replayOffsets.get(id) ?? 0;
/** The replay "now" for a persona. */
export const nowOf = (id: string) => new Date(NOW.getTime() + offsetOf(id) * MIN);

const HISTORY_H = 36;
const FUTURE_H = 26;

// ---------- the "true" curve ----------
function mealShape(dtMin: number, tp: number) {
  if (dtMin <= 0) return 0;
  const x = dtMin / tp;
  return x * x * Math.exp(2 * (1 - x));
}

function mealResponse(m: { carbs: number; fibre?: number; protein?: number; fat?: number }, dtMin: number, model: PersonaModel) {
  const slow = 1 + 0.012 * (m.fibre ?? 0) + 0.006 * (m.fat ?? 0) + 0.004 * (m.protein ?? 0);
  const blunt = 1 - Math.min(0.25, 0.01 * (m.fibre ?? 0));
  return m.carbs * model.gain * blunt * mealShape(dtMin, model.tp * slow);
}

function circadian(hourOfDay: number, model: PersonaModel) {
  const dawn = model.dawn * Math.exp(-((hourOfDay - 6.5) ** 2) / (2 * 1.4 ** 2));
  const night = -6 * Math.exp(-((hourOfDay - 3) ** 2) / (2 * 1.5 ** 2));
  return dawn + night;
}

export interface Correction {
  at: number; // epoch ms
  delta: number;
}

interface Sim {
  model: PersonaModel;
  t0: number; // epoch ms of first grid point
  n: number;
  nowIdx: number;
  truth: number[]; // includes corrections from assimilated readings
  base: number[]; // truth without corrections
  mealsAt: { at: number; plan: MealPlan }[];
  steps: { t: number; v: number }[];
}

const simCache = new Map<string, Sim>();

/** Every recorded meal of the replay (2 days before origin to 1 day after), fixed per persona. */
const planCache = new Map<string, { at: number; plan: MealPlan }[]>();
function mealPlan(model: PersonaModel): { at: number; plan: MealPlan }[] {
  const hit = planCache.get(model.id);
  if (hit) return hit;
  const rnd = mulberry32(model.seed);
  const out: { at: number; plan: MealPlan }[] = [];
  for (let day = -2; day <= 1; day++) {
    for (const plan of model.meals) {
      const d = new Date(NOW);
      d.setDate(d.getDate() + day);
      const jitter = (rnd() - 0.5) * 40;
      d.setHours(0, Math.round(plan.hour * 60 + jitter), 0, 0);
      out.push({ at: d.getTime(), plan: { ...plan, carbs: Math.round(plan.carbs * (0.85 + rnd() * 0.3)) } });
    }
  }
  planCache.set(model.id, out);
  return out;
}

function baseSim(model: PersonaModel): Sim {
  const offset = offsetOf(model.id);
  const key = `${model.id}:${offset}`;
  const cached = simCache.get(key);
  if (cached) return cached;
  const now = nowOf(model.id).getTime();
  const origin0 = NOW.getTime() - HISTORY_H * 60 * MIN;
  const t0 = now - HISTORY_H * 60 * MIN;
  const n = ((HISTORY_H + FUTURE_H) * 60) / STEP_MIN + 1;
  const nowIdx = (HISTORY_H * 60) / STEP_MIN;

  // Recorded meals up to the replay now (the forecast assumes no new meal unless one is given).
  const mealsAt = mealPlan(model).filter((m) => m.at >= t0 - 4 * 60 * MIN && m.at < now);

  const prnd = mulberry32(model.seed + 1);
  const phases = [prnd() * 6.28, prnd() * 6.28, prnd() * 6.28];
  const base: number[] = [];
  for (let i = 0; i < n; i++) {
    const t = t0 + i * STEP_MIN * MIN;
    const d = new Date(t);
    const hod = d.getHours() + d.getMinutes() / 60;
    let g = model.fasting + circadian(hod, model);
    for (const m of mealsAt) g += mealResponse(m.plan, (t - m.at) / MIN, model);
    const hrs = (t - origin0) / (60 * MIN);
    g += 5 * Math.sin(hrs * 1.3 + phases[0]) + 3 * Math.sin(hrs * 2.9 + phases[1]) + 2 * Math.sin(hrs * 0.4 + phases[2]);
    base.push(g);
  }

  const steps: { t: number; v: number }[] = [];
  const h0 = Math.ceil(t0 / (60 * MIN));
  for (let h = h0; h * 60 * MIN <= now; h++) {
    const t = h * 60 * MIN;
    const r = mulberry32(model.seed * 7919 + h);
    const hod = new Date(t).getHours();
    const awake = hod >= 6 && hod <= 22;
    const walk = hod === 7 || hod === 18 ? 2.4 : 1;
    const v = awake ? Math.round((model.stepsPerDay / 16) * walk * (0.5 + r())) : Math.round(r() * 30);
    steps.push({ t, v });
  }

  const sim: Sim = { model, t0, n, nowIdx, truth: base.slice(), base, mealsAt, steps };
  simCache.set(key, sim);
  return sim;
}

/** The hidden "dataset reference CGM" at the persona's replay now (only revealed on request). */
export function referenceAt(model: PersonaModel): { t: string; value: number } {
  const sim = simWithCorrections(model, false);
  return { t: fmtLocal(nowOf(model.id)), value: Math.round(sim.truth[sim.nowIdx]) };
}

/** Per-persona mutable demo state: readings the user added. */
export const extraReadings = new Map<string, Reading[]>();

function simWithCorrections(model: PersonaModel, withExtras = true): Sim {
  const sim = baseSim(model);
  const extras = withExtras ? (extraReadings.get(model.id) ?? []) : [];
  const truth = sim.base.slice();
  for (const r of extras) {
    const at = new Date(r.t).getTime();
    const idx = Math.round((at - sim.t0) / (STEP_MIN * MIN));
    if (idx < 0 || idx >= sim.n) continue;
    const delta = r.value - sim.base[idx];
    for (let i = 0; i < sim.n; i++) {
      const dt = (i - idx) * STEP_MIN;
      if (dt < -60) continue;
      truth[i] += delta * Math.exp(-Math.abs(dt) / (dt < 0 ? 40 : 150));
    }
  }
  return { ...sim, truth };
}

// ---------- what the twin sees at each ladder level ----------
const PRICK_HOURS: Record<Exclude<Ladder, "full">, number[]> = {
  "4": [8, 10.75, 15.75, 22.5],
  "2": [8, 22.5],
  "1": [8],
  "0": [],
};

function ladderReadings(sim: Sim, ladder: Ladder): Reading[] {
  const rnd = mulberry32(sim.model.seed * 7 + ladder.length);
  const out: Reading[] = [];
  const nowT = nowOf(sim.model.id).getTime();
  if (ladder === "full") {
    for (let i = 0; i <= sim.nowIdx; i++) {
      const t = sim.t0 + i * STEP_MIN * MIN;
      out.push({ t: fmtLocal(new Date(t)), value: Math.round(sim.truth[i] + (rnd() - 0.5) * 6), kind: "cgm" });
    }
  } else {
    for (let day = -2; day <= 1; day++) {
      for (const h of PRICK_HOURS[ladder]) {
        const d = new Date(NOW);
        d.setDate(d.getDate() + day);
        d.setHours(0, Math.round(h * 60), 0, 0);
        const t = d.getTime();
        if (t < sim.t0 || t > nowT) continue;
        const idx = Math.round((t - sim.t0) / (STEP_MIN * MIN));
        const v = sim.truth[idx] * (1 + (rnd() - 0.5) * 0.1);
        out.push({ t: fmtLocal(d), value: Math.round(v), kind: "fingerprick" });
      }
    }
  }
  for (const r of extraReadings.get(sim.model.id) ?? []) {
    const t = new Date(r.t).getTime();
    if (t <= nowT && t >= sim.t0) out.push(r);
  }
  out.sort((a, b) => a.t.localeCompare(b.t));
  return out;
}

const LADDER_SD: Record<Ladder, { s0: number; g: number; prior: number }> = {
  full: { s0: 5, g: 3, prior: 30 },
  "4": { s0: 6.5, g: 5, prior: 30 },
  "2": { s0: 7, g: 5.8, prior: 32 },
  "1": { s0: 7.5, g: 6.6, prior: 34 },
  "0": { s0: 30, g: 0, prior: 34 },
};

function hoursSinceReadingAt(t: number, readingTimes: number[]): number {
  let last = -Infinity;
  for (const rt of readingTimes) if (rt <= t) last = rt;
  return last === -Infinity ? 24 : (t - last) / (60 * MIN);
}

function sdAt(sim: Sim, ladder: Ladder, i: number, readingTimes: number[]): number {
  const p = LADDER_SD[ladder];
  const t = sim.t0 + i * STEP_MIN * MIN;
  const hrs = hoursSinceReadingAt(t, readingTimes);
  let sd = ladder === "0" ? p.prior : Math.min(p.prior, p.s0 + p.g * Math.sqrt(hrs));
  const meal = Math.max(0, sim.base[i] - sim.model.fasting);
  sd += 0.12 * meal;
  return sd;
}

/** Error the twin makes in its reconstruction: small near readings, drifting away from them. */
function errAt(sim: Sim, ladder: Ladder, i: number, readingTimes: number[]): number {
  if (ladder === "full") return 0;
  const t = sim.t0 + i * STEP_MIN * MIN;
  const hrs = hoursSinceReadingAt(t, readingTimes);
  const amp = ladder === "0" ? 22 : 9 + (ladder === "1" ? 6 : 0);
  return amp * Math.min(1, hrs / 5) * Math.sin(t / (MIN * 60 * 7) + sim.model.seed);
}

const Z05 = 1.645;
const Z25 = 0.674;

function quantilesFrom(ts: number[], mu: number[], sd: number[]): Quantiles {
  const q = (z: number) => mu.map((m, i) => Math.max(38, r1(m + z * sd[i])));
  return { t: ts.map((t) => fmtLocal(new Date(t))), q05: q(-Z05), q25: q(-Z25), q50: mu.map(r1), q75: q(Z25), q95: q(Z05) };
}

function prob(mu: number[], sd: number[], over: number | null, under: number | null): Prob {
  let pmax = 0;
  for (let i = 0; i < mu.length; i++) {
    const p = over !== null ? 1 - normCdf((over - mu[i]) / sd[i]) : normCdf(((under as number) - mu[i]) / sd[i]);
    pmax = Math.max(pmax, p);
  }
  const p = clamp(pmax * 1.08 + 0.01, 0.01, 0.98);
  const w = 0.06 + 0.1 * Math.sqrt(p * (1 - p));
  const n = Math.round(p * 10);
  return {
    p: r2(p),
    lo: r2(clamp(p - w, 0, 1)),
    hi: r2(clamp(p + w, 0, 1)),
    freq_text: n <= 0 ? "less than 1 time out of 10" : `about ${n} time${n === 1 ? "" : "s"} out of 10`,
  };
}
const r2 = (v: number) => Math.round(v * 100) / 100;

// ---------- forecasts ----------
export interface ForecastOpts {
  meal?: MealInput;
  walk?: { minutes: number; afterMealMin: number };
  horizonMin?: number;
}

export const forecastDrivers = new Map<string, Driver[]>();
/** Every forecast the mock made, so receipts and ownership checks can find it. */
export const forecastStore = new Map<string, { pid: string; forecast: Forecast }>();
let fcSeq = 1;

export function buildForecast(model: PersonaModel, ladder: Ladder, opts: ForecastOpts = {}): Forecast {
  const NOW = nowOf(model.id);
  const sim = simWithCorrections(model);
  const readings = ladderReadings(sim, ladder);
  const rts = readings.map((r) => new Date(r.t).getTime());
  const horizon = opts.horizonMin ?? 240;
  const steps = horizon / STEP_MIN;
  const sdNow = sdAt(sim, ladder, sim.nowIdx, rts);
  const errNow = errAt(sim, ladder, sim.nowIdx, rts);
  const growth = ladder === "full" ? 7 : ladder === "0" ? 4 : 9;
  const meal = opts.meal;
  const mealAt = meal ? (meal.minutes_from_now ?? 15) : 0;

  const ts: number[] = [];
  const mu: number[] = [];
  const sd: number[] = [];
  let mealContribution2h = 0;
  let walkContribution2h = 0;
  for (let k = 0; k <= steps; k++) {
    const i = sim.nowIdx + k;
    const t = NOW.getTime() + k * STEP_MIN * MIN;
    let m = sim.truth[Math.min(i, sim.n - 1)] + errNow * Math.exp(-k / 36);
    let s = Math.sqrt(sdNow ** 2 + ((k * STEP_MIN) / 60) ** 2 * growth ** 2);
    if (meal) {
      const resp = mealResponse(meal, k * STEP_MIN - mealAt, model);
      m += resp;
      s += 0.14 * resp + (meal.carbs_sd ?? 0) * model.gain * mealShape(k * STEP_MIN - mealAt, model.tp);
      if (k * STEP_MIN === 120) mealContribution2h = resp;
    }
    if (opts.walk && opts.walk.minutes > 0) {
      const center = mealAt + opts.walk.afterMealMin + opts.walk.minutes / 2 + 25;
      const eff = -opts.walk.minutes * 1.5 * Math.exp(-((k * STEP_MIN - center) ** 2) / (2 * 45 ** 2));
      m += eff;
      if (k * STEP_MIN === 120) walkContribution2h = eff;
    }
    ts.push(t);
    mu.push(m);
    sd.push(s);
  }

  const twoH = Math.min(mu.length, 120 / STEP_MIN + 1);
  const pHigh = prob(mu.slice(0, twoH), sd.slice(0, twoH), 180, null);
  const pLow = prob(mu.slice(0, twoH), sd.slice(0, twoH), null, 70);
  let peakIdx = 0;
  mu.forEach((v, i) => {
    if (v > mu[peakIdx]) peakIdx = i;
  });

  const lastMeal = sim.mealsAt[sim.mealsAt.length - 1];
  const lastMealEffect = lastMeal ? mealResponse(lastMeal.plan, (NOW.getTime() + 120 * MIN - lastMeal.at) / MIN, model) : 0;
  const hod = (NOW.getHours() + 2) % 24;
  const hrsSince = hoursSinceReadingAt(NOW.getTime(), rts);
  const drivers: Driver[] = [
    meal
      ? { name: "planned_meal_carbs", label_en: `${meal.name ?? "Planned meal"} carbs (${Math.round(meal.carbs)} g)`, contribution: r1(mealContribution2h), source: "physiology" }
      : { name: "recent_meal", label_en: `Last meal${lastMeal ? ` (${lastMeal.plan.name})` : ""}`, contribution: r1(lastMealEffect), source: "physiology" },
    { name: "circadian", label_en: "Time of day (evening insulin sensitivity)", contribution: r1(circadian(hod, model) + 3), source: "physiology" },
    opts.walk && opts.walk.minutes > 0
      ? { name: "walk_after_meal", label_en: `${opts.walk.minutes}-minute walk`, contribution: r1(walkContribution2h), source: "physiology" }
      : { name: "low_activity_today", label_en: "Fewer steps than usual today", contribution: r1(4 + (model.seed % 5)), source: "learned" },
    { name: "short_sleep", label_en: "Short sleep last night", contribution: r1(2.5 + (model.seed % 3)), source: "learned" },
    { name: "time_since_reading", label_en: `${Math.round(hrsSince)} h since last reading`, contribution: r1(-(errNow * 0.4)), source: "learned" },
  ];
  drivers.sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));

  const id = `mock-fc-${model.id}-${ladder}-${fcSeq++}`;
  forecastDrivers.set(id, drivers);
  if (forecastStore.size > 400) forecastStore.clear();
  const abstain = ladder === "0" && extraReadingsCount(model.id) === 0
    ? { flag: true, reason: "No glucose reading yet at this sensor level: the twin is running on population averages." }
    : { flag: false, reason: null };
  const out: Forecast = {
    forecast_id: id,
    origin: fmtLocal(NOW),
    horizon_min: horizon,
    traj: { ...quantilesFrom(ts, mu, sd), validated_horizon_min: 120 },
    // Offline mode has no evaluation reports, so no held-out reliability is attached (never faked).
    p_high: { p: pHigh.p, freq_text: pHigh.freq_text, validated: true, reliability: null },
    p_low: { p: pLow.p, freq_text: pLow.freq_text, validated: false },
    p_low_validated: false,
    peak: { t: fmtLocal(new Date(ts[peakIdx])), value: Math.round(mu[peakIdx]) },
    conformal_level: 0.9,
    abstain,
    drivers,
    provenance: {
      model_version: "offline-mock",
      hybrid_trained_on: "none (offline mock: no model)",
      inputs_revision: 0,
      prior_inputs: {},
      observations_used: readings.length,
      replay_now: fmtLocal(NOW),
    },
  };
  forecastStore.set(id, { pid: model.id, forecast: out });
  return out;
}

const extraReadingsCount = (id: string) => (extraReadings.get(id) ?? []).length;

// ---------- next best prick ----------
function inSleep(d: Date, sleep: { start: string; end: string }) {
  const toMin = (s: string) => {
    const [h, m] = s.split(":").map(Number);
    return h * 60 + m;
  };
  const m = d.getHours() * 60 + d.getMinutes();
  const a = toMin(sleep.start);
  const b = toMin(sleep.end);
  return a > b ? m >= a || m < b : m >= a && m < b;
}

export function buildNbp(model: PersonaModel, ladder: Ladder): NextBestPrick {
  const NOW = nowOf(model.id);
  const sim = simWithCorrections(model);
  const readings = ladderReadings(sim, ladder);
  const rts = readings.map((r) => new Date(r.t).getTime());
  const hrs = hoursSinceReadingAt(NOW.getTime(), rts);
  const ladderScale = ladder === "full" ? 0.08 : ladder === "0" ? 1.15 : 0.55 + Math.min(0.45, hrs / 20);
  // Expected next meals (tomorrow's and tonight's dinner), the main sources of uncertainty.
  const upcoming: number[] = [];
  for (let day = 0; day <= 1; day++) {
    for (const plan of model.meals) {
      const d = new Date(NOW);
      d.setDate(d.getDate() + day);
      d.setHours(0, Math.round(plan.hour * 60), 0, 0);
      if (d.getTime() > NOW.getTime()) upcoming.push(d.getTime() + 60 * MIN);
    }
  }
  const candidates: { t: string; gain_pct: number }[] = [];
  for (let k = 1; k <= 48; k++) {
    const t = NOW.getTime() + k * 30 * MIN;
    const d = new Date(t);
    if (inSleep(d, model.sleep)) continue;
    let post = 0;
    for (const u of upcoming) post = Math.max(post, Math.exp(-(((t - u) / MIN) ** 2) / (2 * 35 ** 2)));
    const decay = Math.exp(-k / 70);
    const g = (14 + 30 * post) * decay * ladderScale + 2;
    candidates.push({ t: fmtLocal(d), gain_pct: r1(clamp(g, 0.5, 60)) });
  }
  const best = candidates.reduce((a, b) => (b.gain_pct > a.gain_pct ? b : a), candidates[0]);
  return {
    time: best.t,
    expected_gain_pct: best.gain_pct,
    reason: "Your dinner peak is the least certain part of the next 12 hours, so a reading then teaches the twin the most.",
    candidates,
  };
}

// ---------- full state ----------
export function buildState(model: PersonaModel, ladder: Ladder): TwinState {
  const NOW = nowOf(model.id);
  const sim = simWithCorrections(model);
  const readings = ladderReadings(sim, ladder);
  const rts = readings.map((r) => new Date(r.t).getTime());
  const ts: number[] = [];
  const mu: number[] = [];
  const sd: number[] = [];
  for (let i = 0; i <= sim.nowIdx; i++) {
    ts.push(sim.t0 + i * STEP_MIN * MIN);
    mu.push(sim.truth[i] + errAt(sim, ladder, i, rts));
    sd.push(sdAt(sim, ladder, i, rts));
  }
  const hrs = hoursSinceReadingAt(NOW.getTime(), rts);
  const sdNow = sd[sd.length - 1];
  const est = mu[mu.length - 1];
  const band: Band = { lo: Math.round(est - Z05 * sdNow), hi: Math.round(est + Z05 * sdNow) };
  const score = ladder === "0" && rts.length === 0 ? 0.05 : r2(Math.exp(-hrs / 9));
  const label = hrs < 2 ? "fresh" : hrs < 8 ? "ageing" : "stale";
  const forecast = buildForecast(model, ladder);
  const meals: MealEvent[] = sim.mealsAt.map((m) => ({
    t: fmtLocal(new Date(m.at)),
    name: m.plan.name,
    carbs: m.plan.carbs,
    fibre: m.plan.fibre,
    protein: m.plan.protein,
    fat: m.plan.fat,
  }));
  const offset = offsetOf(model.id);
  const day = REPLAY_DAY0 + Math.floor((19.5 * 60 + offset) / (24 * 60));
  const hhmm = `${String(NOW.getHours()).padStart(2, "0")}:${String(NOW.getMinutes()).padStart(2, "0")}`;
  return {
    now: fmtLocal(NOW),
    replay: { now: fmtLocal(NOW), day, offset_min: offset, max_offset_min: MAX_OFFSET_MIN, label_en: `Replay · day ${day} · ${hhmm}`, mode: "replay" },
    ladder,
    estimate: Math.round(est),
    band,
    freshness: { score, hours_since_reading: r1(rts.length ? hrs : 24), label: rts.length ? label : "stale" },
    last_observation: readings.length ? readings[readings.length - 1] : null,
    abstain: forecast.abstain,
    ess: ladder === "full" ? 0.84 : ladder === "0" ? 0.31 : r2(0.72 - hrs * 0.012),
    history: {
      virtual_cgm: quantilesFrom(ts, mu, sd),
      readings,
      meals,
      steps: { t: sim.steps.map((s) => fmtLocal(new Date(s.t))), v: sim.steps.map((s) => s.v) },
    },
    forecast,
    next_best_prick: buildNbp(model, ladder),
    target: { lo: 70, hi: 180 },
  };
}

export function resetPersona(id: string) {
  extraReadings.delete(id);
  replayOffsets.delete(id);
}

/** Multi-day profile for the doctor's AGP-style chart and summary metrics. */
export function weekStats(model: PersonaModel) {
  const rnd = mulberry32(model.seed * 13);
  const hours: number[][] = Array.from({ length: 24 }, () => []);
  let inRange = 0;
  let total = 0;
  let sum = 0;
  let hypo = 0;
  let hyper = 0;
  for (let day = 0; day < 7; day++) {
    let wasHigh = false;
    let wasLow = false;
    for (let m = 0; m < 24 * 60; m += 15) {
      const hod = m / 60;
      let g = model.fasting + circadian(hod, model) + (rnd() - 0.5) * 10;
      for (const plan of model.meals) {
        const scale = 0.75 + rnd() * 0.02 + (day % 3) * 0.12;
        g += mealResponse({ ...plan, carbs: plan.carbs * scale }, m - plan.hour * 60 - (day % 2) * 15, model);
      }
      if (day === 4 && hod > 3 && hod < 4.2) g -= 62; // one overnight low in the week
      hours[Math.floor(hod)].push(g);
      total++;
      sum += g;
      if (g >= 70 && g <= 180) inRange++;
      if (g > 180 && !wasHigh) hyper++;
      if (g < 70 && !wasLow) hypo++;
      wasHigh = g > 180;
      wasLow = g < 70;
    }
  }
  const q = (arr: number[], p: number) => {
    const s = arr.slice().sort((a, b) => a - b);
    return r1(s[Math.min(s.length - 1, Math.floor(p * s.length))]);
  };
  const d0 = new Date(NOW);
  d0.setHours(0, 0, 0, 0);
  const t = hours.map((_, h) => fmtLocal(new Date(d0.getTime() + h * 60 * MIN)));
  const mean = sum / total;
  return {
    profile: {
      t,
      q05: hours.map((a) => q(a, 0.05)),
      q25: hours.map((a) => q(a, 0.25)),
      q50: hours.map((a) => q(a, 0.5)),
      q75: hours.map((a) => q(a, 0.75)),
      q95: hours.map((a) => q(a, 0.95)),
    } as Quantiles,
    tir: r2(inRange / total),
    mean: Math.round(mean),
    gmi: r1(3.31 + 0.02392 * mean),
    hypo,
    hyper,
  };
}

export function sparkline(model: PersonaModel): number[] {
  const sim = baseSim(model);
  const out: number[] = [];
  for (let h = 48; h > 0; h--) {
    const idx = sim.nowIdx - (h * 60) / STEP_MIN;
    out.push(Math.round(idx >= 0 ? sim.base[idx] : sim.base[(idx + (24 * 60) / STEP_MIN) | 0] ?? model.fasting));
  }
  return out;
}

export function modelById(id: string): PersonaModel {
  const m = MODELS.find((x) => x.id === id);
  if (!m) throw new Error(`Unknown persona ${id}`);
  return m;
}
