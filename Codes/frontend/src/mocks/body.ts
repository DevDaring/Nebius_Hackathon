// Offline mock of POST /api/twin/{pid}/body: shape-correct, plausible organ flows.
// A tiny two-compartment gut model plus a minimal-model style insulin response, driven by the same
// mock forecast the chart uses, so the blood curve matches the chart in offline mode.
import type { BodyRequest, BodyVariant, BodyView, FluxSeries, Forecast, MealInput, OrganKey, OrganMeta, Scenario } from "@/api/types";

const STEPS = 48;
const DT = 5;

export const MOCK_ORGANS: OrganMeta[] = [
  { key: "stomach", label_en: "Stomach", unit: "g carbs", description_en: "Carbohydrate from the meal still waiting in the stomach (first gut compartment).", status: "simulated" },
  { key: "intestine", label_en: "Intestine", unit: "g carbs", description_en: "Carbohydrate being absorbed in the intestine (second gut compartment).", status: "simulated" },
  { key: "gut_to_blood", label_en: "From gut into blood", unit: "mg/dL per min", description_en: "How fast glucose from food is entering the blood.", status: "simulated" },
  { key: "liver", label_en: "Liver and baseline balance", unit: "mg/dL per min", description_en: "Pulls glucose back toward your usual level: positive = releasing glucose, negative = taking it up.", status: "simulated" },
  { key: "pancreas", label_en: "Pancreas (insulin release)", unit: "µU/mL per min", description_en: "Insulin released in response to glucose above your usual level.", status: "simulated" },
  { key: "insulin", label_en: "Insulin in blood", unit: "µU/mL above usual", description_en: "Insulin above your usual level, which helps muscles and fat take up glucose.", status: "simulated" },
  { key: "insulin_uptake", label_en: "Muscle and fat uptake (insulin)", unit: "mg/dL per min", description_en: "Glucose moved out of the blood with the help of insulin.", status: "simulated" },
  { key: "exercise_uptake", label_en: "Muscles working", unit: "mg/dL per min", description_en: "Extra glucose used by muscles during and after activity such as a walk.", status: "simulated" },
  { key: "unexplained", label_en: "Unexplained trend", unit: "mg/dL per min", description_en: "Recent drift the physiology model cannot explain (stress, illness, unlogged food...).", status: "simulated" },
];

const r = (v: number, d = 3) => Math.round(v * 10 ** d) / 10 ** d;

/** Median with a multiplicative 10-90% spread (wider further ahead). */
function band(q50: number[], spread = 0.35, signed = false): FluxSeries {
  const q10: number[] = [];
  const q90: number[] = [];
  q50.forEach((v, i) => {
    const s = spread * (0.6 + (i / STEPS) * 0.8);
    const w = Math.abs(v) * s + 0.01;
    q10.push(r(signed ? v - w : Math.max(0, v - w)));
    q90.push(r(v + w));
  });
  return { q10, q50: q50.map((v) => r(v)), q90 };
}

function simulate(blood: number[], meal: MealInput | undefined, sc: Scenario | undefined, residualCarbs: number): Record<OrganKey, FluxSeries> {
  const scale = sc?.carb_scale ?? 1;
  const carbs = meal ? meal.carbs * scale * (sc?.swap ? 0.85 : 1) : 0;
  const mealAt = meal ? Math.max(0, (meal.minutes_from_now ?? 30) + (sc?.shift_min ?? 0)) : -1;
  const walkStart = sc?.walk_min ? mealAt + (sc.walk_after_min ?? 10) : -1;
  const walkEnd = walkStart >= 0 ? walkStart + (sc?.walk_min ?? 0) : -1;
  const gb = 120;
  let q1 = residualCarbs * 0.35;
  let q2 = residualCarbs * 0.65;
  let x = 0.012;
  let ins = 5;
  let e = 0.001;
  const out: Record<OrganKey, number[]> = { stomach: [], intestine: [], gut_to_blood: [], liver: [], pancreas: [], insulin: [], insulin_uptake: [], exercise_uptake: [], unexplained: [] };
  for (let k = 0; k <= STEPS; k++) {
    const tm = k * DT;
    const g = blood[k];
    if (meal && tm === Math.round(mealAt / DT) * DT) q1 += carbs;
    const ra = 0.0045 * 1000 * q2 / 190; // mg/dL per min
    const panc = 0.012 * Math.max(g - gb, 0);
    const walking = walkStart >= 0 && tm >= walkStart && tm < walkEnd;
    out.stomach.push(q1);
    out.intestine.push(q2);
    out.gut_to_blood.push(ra);
    out.liver.push(0.008 * (gb - g));
    out.pancreas.push(panc);
    out.insulin.push(ins);
    out.insulin_uptake.push(x * g);
    out.exercise_uptake.push(e * g);
    out.unexplained.push(0.05 * Math.sin(k / 9));
    for (let s = 0; s < DT; s++) {
      const dq1 = -0.035 * q1;
      const dq2 = 0.035 * q1 - 0.02 * q2;
      q1 += dq1;
      q2 += dq2;
      ins += panc - 0.09 * ins + 0.09 * 5;
      x += -0.03 * x + 0.00006 * Math.max(ins - 4, 0);
      e += walking ? 0.0012 : -0.04 * e;
    }
    x = Math.max(0.002, x);
    e = Math.max(0, e);
  }
  const res = {} as Record<OrganKey, FluxSeries>;
  for (const key of Object.keys(out) as OrganKey[]) res[key] = band(out[key], 0.3, key === "liver" || key === "unexplained");
  return res;
}

function variant(fc: Forecast, meal: MealInput | undefined, sc: Scenario | undefined, now: number): BodyVariant {
  const q = fc.traj;
  const n = STEPS + 1;
  const pick = (a: number[]) => Array.from({ length: n }, (_, i) => r(a[Math.min(i, a.length - 1)] ?? now, 1));
  const blood = { q05: pick(q.q05), q50: pick(q.q50), q95: pick(q.q95) };
  blood.q50[0] = r(now, 1);
  const lc = blood.q50.map((_, i) => r(-4 * Math.sin(Math.min(i, 24) / 8), 1));
  lc[0] = 0;
  return { forecast_id: fc.forecast_id, blood, fluxes: simulate(blood.q50, meal, sc, 18), learned_correction: lc };
}

export function buildBody(pid: string, req: BodyRequest, origin: string, base: Forecast, scen: Forecast | null, now: number): BodyView {
  const t0 = new Date(origin).getTime();
  const pad = (v: number) => String(v).padStart(2, "0");
  const fmt = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const t = Array.from({ length: STEPS + 1 }, (_, i) => fmt(new Date(t0 + i * DT * 60_000)));
  return {
    persona_id: pid,
    replay_now: t[0],
    t,
    validated_horizon_min: 120,
    label_en: "Simplified physiology model — not a measurement of your organs",
    validated_en: "Only blood glucose (the forecast) is validated; organ flows are simulated by the model.",
    organs: MOCK_ORGANS,
    baseline: variant(base, req.meal, undefined, now),
    scenario: scen && req.scenario ? variant(scen, req.meal, req.scenario, now) : null,
    scenario_label: req.scenario ? (req.scenario.label ?? "Scenario") : null,
  };
}
