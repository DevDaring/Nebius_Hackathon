// A tiny rule-based stand-in for the backend agent, used only in offline mock mode. It calls the
// mock twin "tools" and fills fixed templates, so every number in a reply comes from a tool output.
// Replies are written in English only; for the other languages they carry a clear "mock, English
// only" prefix instead of an unreviewed translation. No language model is involved.
import type { AgentReply, ChatRequest, Clarification, Disclosure, Ladder, Lang, PendingAction, ToolCall } from "@/api/types";
import { buildForecast, buildNbp, buildState, fmtLocal, modelById, nowOf } from "./sim";
import { assessReading } from "./safety";
import { mockLabel } from "./label";

/** Actions proposed in chat, waiting for POST /agent/confirm. Nothing is logged before that. */
export const pendingActions = new Map<string, PendingAction & { pid: string; ladder: Ladder; lang: Lang }>();
let actionSeq = 1;
let execSeq = 1;

const READING_WORDS = ["sugar", "glucose", "reading", "glucosa", "glycémie", "glycemie", "blutzucker", "glicemia", "血糖"];


/** "my sugar is 150" / "glucosa 5,6 mmol" -> a reading the user reports, if any. */
export function reportedReading(text: string): { value: number; unit: "mg/dL" | "mmol/L" } | null {
  if (!READING_WORDS.some((w) => text.toLowerCase().includes(w))) return null;
  const m = /(\d{1,3}(?:[.,]\d)?)\s*(mmol)?/i.exec(text);
  if (!m) return null;
  const value = Number(m[1].replace(",", "."));
  const unit = m[2] || (value < 35 && /[.,]/.test(m[1])) ? "mmol/L" : "mg/dL";
  if (unit === "mg/dL" && (value < 20 || value > 600)) return null;
  return { value, unit };
}

const has = (text: string, words: string[]) => words.some((w) => text.toLowerCase().includes(w));

function clock(iso: string) {
  const d = new Date(iso);
  const h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, "0");
  return `${((h + 11) % 12) + 1}:${m} ${h < 12 ? "am" : "pm"}`;
}

const T = {
  emergency: "This may be an emergency. Please contact a doctor now or call your local emergency number.",
  dose: "I cannot advise on medicine or insulin doses. Please ask your doctor.",
  dinner: (peak: number, time: string, n: number) =>
    `After your usual dinner, the twin estimates your glucose may peak near ${peak} mg/dL around ${time}. Going above 180 mg/dL happens about ${n} times out of 10 in the model.`,
  nbp: (time: string) => `A reading around ${time} may teach the twin the most. This timing is experimental.`,
  walk: (a: number, b: number) =>
    `In the model, a 15-minute walk after dinner moves the chance of going above 180 mg/dL from about ${a} to about ${b} times out of 10. This is an exploratory simulation, and the ranking is uncertain.`,
  now: (e: number, lo: number, hi: number) => `Right now the twin estimates you are near ${e} mg/dL, most likely between ${lo} and ${hi} mg/dL.`,
  clarifyPortion: "How much rice will you eat? The amount changes the simulation a lot.",
};

/** Words that make a meal amount vague enough to ask one question first (mock only). */
const VAGUE = ["some rice", "a bit of", "a little", "un poco", "un peu", "etwas", "un po'", "少し", "rice"];

function base(lang: Lang, tool_calls: ToolCall[]) {
  return {
    lang,
    tool_calls,
    grounding: { passed: true, numbers: [] as string[], fallback_used: false },
    safety: { blocked: false, emergency: false, reason: null as string | null },
    audio_url: null,
    source: "fixture" as const,
    source_detail: "template",
    execution_id: `mock-${(execSeq++).toString(16).padStart(6, "0")}`,
    schema_version: "1.0",
    clarification: null as Clarification | null,
    disclosures: [] as Disclosure[],
    checks: { numbers: "passed", guardrails_input: "not_run", guardrails_output: "not_run" },
    model: { provider: "offline_mock", model_id: null, live: false },
  };
}

export function mockChat(req: ChatRequest): AgentReply {
  const model = modelById(req.patient_id);
  const lang = req.lang;
  const text = req.text;
  const tool_calls: ToolCall[] = [];
  const b = base(lang, tool_calls);
  const say = (s: string) => `${mockLabel(lang)}${s}`;
  const englishOnly: Disclosure[] = lang === "en-US" ? [] : [{ kind: "fallback", text: "Offline mock: replies are templates in English only." }];

  if (has(text, ["faint", "unconscious", "chest pain", "desmay", "évanoui", "ohnmächtig", "svenuto", "意識"])) {
    return { ...b, reply: say(T.emergency), intent: "emergency", safety: { blocked: true, emergency: true, reason: "symptom_keywords" }, highlight: { view: "none" }, checks: { ...b.checks, numbers: "not_run" } };
  }
  const rr = reportedReading(text);
  if (rr) {
    const mgdl = rr.unit === "mmol/L" ? rr.value * 18.016 : rr.value;
    const safety = assessReading(mgdl, lang);
    const id = `mock-act-${actionSeq++}`;
    const shown = `${rr.value} ${rr.unit}`;
    const action: PendingAction = { id, kind: "log_reading", summary_en: `Log a reading of ${shown}`, payload: { value: rr.value, unit: rr.unit } };
    pendingActions.set(id, { ...action, pid: req.patient_id, ladder: req.ladder, lang });
    const urgent = safety.level !== "ok";
    const ask = `Shall I add a reading of ${shown} to your twin? Nothing changes until you confirm.`;
    return {
      ...b,
      // Safety messages are shown immediately; the reading itself waits for confirmation.
      reply: say(urgent ? `${safety.title}. ${safety.message} ${ask}` : ask),
      intent: "log_reading",
      safety: { blocked: false, emergency: safety.emergency, reason: urgent ? `${safety.level}_reading` : null },
      highlight: { view: "none" },
      claims: [{ slot: "reading", field: "user.text", value: rr.value, rendered: shown }],
      pending_action: action,
      disclosures: englishOnly,
    };
  }
  if (has(text, ["insulin", "dose", "medicine", "tablet", "insulina", "dosis", "médicament", "dosierung", "medikament", "farmaco", "インスリン", "薬"])) {
    return { ...b, reply: say(T.dose), intent: "out_of_scope", safety: { blocked: true, emergency: false, reason: "dose_request" }, highlight: { view: "none" }, checks: { ...b.checks, numbers: "not_run" }, disclosures: englishOnly };
  }
  const skipped = (req.skip_slots ?? []).includes("portion");
  // One short clarification when the amount is vague (skip continues with a wider range).
  if (!skipped && has(text, VAGUE) && !/\d/.test(text)) {
    return {
      ...b,
      reply: say(T.clarifyPortion),
      intent: "clarify",
      highlight: { view: "none" },
      checks: { ...b.checks, numbers: "not_run" },
      clarification: {
        slot: "portion",
        question: say(T.clarifyPortion),
        options: [
          { label: "1 small bowl (about 150 g)", text: "1 small bowl of rice (about 150 g) with dinner" },
          { label: "1 large bowl (about 300 g)", text: "1 large bowl of rice (about 300 g) with dinner" },
        ],
        skip: { label: "Skip: use a wider range", text, skip_slots: ["portion"] },
      },
      disclosures: englishOnly,
    };
  }
  if (has(text, ["walk", "camin", "march", "spazier", "passeggi", "歩"])) {
    const meal = { name: "Usual dinner", carbs: model.meals[3].carbs, fibre: model.meals[3].fibre, protein: model.meals[3].protein, fat: model.meals[3].fat, minutes_from_now: 50 };
    const bf = buildForecast(model, req.ladder, { meal });
    const s = buildForecast(model, req.ladder, { meal, walk: { minutes: 15, afterMealMin: 10 } });
    const a = Math.round(bf.p_high.p * 10);
    const c = Math.round(s.p_high.p * 10);
    tool_calls.push({ name: "what_if", args: { base_meal: meal, scenario: { walk_min: 15, walk_after_min: 10 } }, output: { baseline_p_high: bf.p_high, scenario_p_high: s.p_high } });
    return {
      ...b,
      reply: say(T.walk(a, c)),
      intent: "what_if",
      grounding: { passed: true, numbers: ["15", "180", String(a), String(c)], fallback_used: false },
      highlight: { view: "whatif" },
      disclosures: [
        { kind: "exploratory", text: "Exploratory simulation: a model what-if, not a proven effect." },
        { kind: "ranking_uncertain", text: "The two scenarios overlap; the model cannot say reliably which is better." },
        ...englishOnly,
      ],
    };
  }
  if (has(text, ["when", "next", "check", "cuándo", "quand", "wann", "quando", "いつ"])) {
    const nbp = buildNbp(model, req.ladder);
    tool_calls.push({ name: "next_best_prick", args: { patient_id: req.patient_id }, output: nbp });
    const time = clock(nbp.time);
    return {
      ...b,
      reply: say(T.nbp(time)),
      intent: "next_best_prick",
      grounding: { passed: true, numbers: [time], fallback_used: false },
      highlight: { view: "nbp", from: nbp.time },
      disclosures: [{ kind: "not_validated", text: "Next-reading timing is experimental: its benefit was not shown in testing." }, ...englishOnly],
    };
  }
  if (has(text, ["now", "right now", "ahora", "maintenant", "jetzt", "adesso", "ora", "今"])) {
    const st = buildState(model, req.ladder);
    tool_calls.push({ name: "get_state", args: { patient_id: req.patient_id, at: st.now }, output: { estimate: st.estimate, band: st.band, freshness: st.freshness } });
    const from = new Date(nowOf(req.patient_id));
    from.setHours(from.getHours() - 3);
    const stale = st.freshness.label === "stale";
    return {
      ...b,
      reply: say(T.now(st.estimate, st.band.lo, st.band.hi)),
      intent: "state",
      grounding: { passed: true, numbers: [st.estimate, st.band.lo, st.band.hi].map(String), fallback_used: false },
      highlight: { view: "stage", from: fmtLocal(from), to: st.now },
      disclosures: [
        ...(stale ? [{ kind: "stale_data", text: `The last reading is ${st.freshness.hours_since_reading.toFixed(1)} h old, so the range is wide.` }] : []),
        ...englishOnly,
      ],
    };
  }
  // Default: dinner forecast.
  const dinner = model.meals[3];
  const meal = { name: dinner.name, carbs: dinner.carbs, fibre: dinner.fibre, protein: dinner.protein, fat: dinner.fat, minutes_from_now: 50 };
  const fc = buildForecast(model, req.ladder, { meal });
  tool_calls.push({ name: "forecast", args: { patient_id: req.patient_id, horizon_min: 240, meal }, output: { forecast_id: fc.forecast_id, peak: fc.peak, p_high: fc.p_high, p_low: fc.p_low } });
  const n = Math.round(fc.p_high.p * 10);
  const NOW = nowOf(req.patient_id);
  const end = new Date(NOW);
  end.setMinutes(end.getMinutes() + 210);
  return {
    ...b,
    reply: say(T.dinner(fc.peak.value, clock(fc.peak.t), n)),
    intent: "forecast",
    grounding: { passed: true, numbers: [String(fc.peak.value), "180", String(n)], fallback_used: false },
    highlight: { view: "forecast", from: fmtLocal(NOW), to: fmtLocal(end) },
    disclosures: [
      ...(skipped ? [{ kind: "wider_range", text: "The portion was not given, so the usual dinner was simulated; the real range may be wider." }] : []),
      ...englishOnly,
    ],
  };
}
