# NemoTwins API contract — core endpoints

Agent, capabilities and admin endpoints: [`API_CONTRACT_AGENT.md`](API_CONTRACT_AGENT.md).

Base URL: `/api` (Vite dev proxy → `http://localhost:8000`). All JSON. All routes need
`Authorization: Bearer <token>` except these public ones:

* `POST /api/auth/login`, `GET /api/health`;
* `GET /api/samples/{kind}/{name}` (demo meal photos / synthetic lab reports) and
  `GET /api/reports/figures/{name}` (evaluation figures): non-sensitive, public so `<img src>` works;

Glucose is always mg/dL. Times are ISO-8601 strings in the patient's local time
(`Asia/Kolkata`, no offset suffix needed by the UI — treat as local). The twin runs on a
**replay clock**: each persona has a fixed demo "now" (`state.now`), so the demo is reproducible.

```ts
// ---------- shared ----------
type Ladder = "full" | "4" | "2" | "1" | "0";        // sensor ladder: full CGM, 4/2/1 pricks a day, none
type Lang = "en-US" | "es-ES" | "fr-FR" | "de-DE" | "it-IT" | "ja-JP";
interface Prob { p: number; lo: number; hi: number; freq_text: string }   // freq_text e.g. "about 7 times out of 10" (English; UI localises from p)
interface Band { lo: number; hi: number }
interface Quantiles { t: string[]; q05: number[]; q25: number[]; q50: number[]; q75: number[]; q95: number[] }
interface Reading { t: string; value: number; kind: "cgm" | "fingerprick" | "lab" }
interface MealEvent { t: string; name: string; carbs: number; fibre?: number; protein?: number; fat?: number; photo_url?: string }

// ---------- auth ----------
POST /api/auth/login  {username, password}  -> {access_token: string, user: User}
GET  /api/auth/me                           -> User
interface User { username: string; display_name: string; roles: ("patient"|"clinician")[] }

// ---------- patients (3 synthetic composite personas) ----------
GET /api/patients -> PatientSummary[]
GET /api/patients/{pid} -> PatientDetail
interface PatientSummary {
  id: string; name: string; age: number; sex: "F"|"M"; city: string; occupation: string;
  language: Lang; synthetic: true; source_note: string;      // e.g. "Synthetic composite: CGMacros participant 12 trajectory + invented EHR"
  hba1c: number; risk_7d: number;                             // 0..1 share of next-7-day forecast time above 180
  tir_7d: number;                                             // 0..1 time in range 70-180 (last 7 days, virtual CGM)
  sparkline: number[];                                        // last 48 h virtual CGM, hourly
  avatar_initials: string;
}
interface PatientDetail extends PatientSummary {
  ehr: { bmi: number; diabetes_years: number; medications: string[]; fasting_glucose?: number;
         ldl?: number; egfr?: number; conditions: string[] };
  calibration: { cgm_days: number; start: string; end: string };
  sleep_window: { start: string; end: string };              // "23:00","06:00"
}

// ---------- twin ----------
GET  /api/twin/{pid}/state?ladder=2  -> TwinState
interface TwinState {
  now: string; ladder: Ladder;
  estimate: number; band: Band;                 // current 90% band
  freshness: { score: number; hours_since_reading: number; label: "fresh"|"ageing"|"stale" };
  last_observation: Reading | null;
  abstain: { flag: boolean; reason: string | null };
  ess: number;                                  // effective particle fraction 0..1
  history: {                                    // last 36 h up to now
    virtual_cgm: Quantiles;                     // filtered reconstruction
    readings: Reading[];                        // what the twin actually saw at this ladder level
    true_cgm?: { t: string[]; v: number[] };    // hidden ground truth, ONLY sent when ?reveal=1 (Trust/demo)
    meals: MealEvent[];
    steps: { t: string[]; v: number[] };        // hourly step counts
  };
  forecast: Forecast;                           // next 4 h with no new meal
  next_best_prick: NextBestPrick;
  target: { lo: 70; hi: 180 };
  p_low_validated: false;
}

POST /api/twin/{pid}/forecast {ladder, horizon_min?: 240, meal?: MealInput} -> Forecast
interface MealInput { name?: string; carbs: number; carbs_sd?: number; fibre?: number; protein?: number; fat?: number; minutes_from_now?: number; items?: {food_id: string; units: number}[] }
interface Forecast {
  forecast_id: string; origin: string; horizon_min: number;
  traj: Quantiles;                              // 5-min grid from origin
  p_high: Prob;                                 // P(any value > 180 within next 2 h)
  p_low: Prob;                                  // P(any value < 70 within next 2 h)
  peak: { t: string; value: number };           // median-curve peak
  p_low_validated: false;                       // P(<70) is reported but NOT validated (too few lows in training data)
  conformal_level: 0.9;
  abstain: { flag: boolean; reason: string | null };
  drivers: Driver[];                            // top 5, signed mg/dL contribution to the 2-h value
}
interface Driver { name: string; label_en: string; contribution: number; source: "physiology" | "learned" }

POST /api/twin/{pid}/what_if {ladder, base_meal: MealInput, scenario: Scenario} -> WhatIf
interface Scenario { carb_scale?: number; swap?: {from: string; to: string}; walk_min?: number; walk_after_min?: number; shift_min?: number; label?: string }
interface WhatIf {
  baseline: Forecast; scenario: Forecast;
  delta_p_high: { mean: number; lo: number; hi: number };   // scenario - baseline
  delta_peak: number;
  too_small_to_call: boolean; note: string;
}

GET  /api/twin/{pid}/next_best_prick?ladder=2 -> NextBestPrick
interface NextBestPrick { time: string; expected_gain_pct: number; reason: string;   // gain = % reduction of forecast variance over next 12 h
                          candidates: { t: string; gain_pct: number }[] }          // 30-min grid, next 24 h, sleep skipped

POST /api/twin/{pid}/assimilate {ladder, value: number, at?: string} -> Assimilation
interface Assimilation { state: TwinState; band_before: Band; band_after: Band; narrowed_pct: number; innovation: number }

GET  /api/twin/{pid}/outlook_90d?ladder=2 -> Outlook
interface Outlook { label: "projection"; days: number[]; tir_current: number[]; tir_scenario: number[];
                    ehba1c_current: number[]; ehba1c_scenario: number[]; scenario_label: string; note: string;
                    anchor?: { tir_7d: number; mean_7d: number; source: string } }
// tir_current is anchored to the OBSERVED last-7-day TIR (same number as the doctor brief's tir_7d);
// tir_scenario = that anchor + the change the twin simulates for the scenario.

GET  /api/twin/{pid}/explain/{forecast_id} -> Explanation
interface Explanation { physiology: Driver[]; learned: Driver[]; tool_calls: ToolCall[]; text_en: string }

POST /api/twin/{pid}/reset -> {ok: true}        // reset demo state (assimilated readings, logged meals)

// ---------- meals & food ----------
GET  /api/food/search?q=rice&lang=en-US -> Food[]
GET  /api/food/swaps?lang=en-US -> {from: string; to: string; from_qty: number; to_qty: number;
                                   label: string /* in lang, English fallback */; label_en: string}[]
interface Food { id: string; name: string; name_en: string; unit: string; unit_label: string; grams_per_unit: number; carbs_g: number; fibre_g: number; protein_g: number; fat_g: number; kcal: number; cuisine: string }
GET  /api/meal/samples -> {id: string; title: string; image_url: string}[]              // demo thali photos
POST /api/meal/photo  multipart {image: File} OR {sample_id} -> MealParse
interface MealParse { dishes: {food_id: string|null; detected: string; name: string; units: number; unit: string; carbs: number; fibre: number; protein: number; fat: number; confidence: number; needs_pick: boolean; candidates?: Food[]}[];
                      total: { carbs: number; fibre: number; protein: number; fat: number; kcal: number }; carbs_sd: number; source: "fixture" | "live" }

// ---------- agent / voice ----------
POST /api/agent/chat {patient_id, text, lang, ladder} -> AgentReply
interface AgentReply { reply: string; lang: Lang; intent: string; tool_calls: ToolCall[];
                       grounding: { passed: boolean; numbers: string[]; fallback_used: boolean };
                       safety: { blocked: boolean; emergency: boolean; reason: string | null };
                       highlight: { view: "stage" | "forecast" | "whatif" | "nbp" | "none"; from?: string; to?: string };  // ISO window
                       audio_url: string | null;   // SIGNED relative URL "/api/audio/<key>.mp3?exp=<unix>&sig=<hmac>", ~24 h
                       source: "fixture" | "live"; // fixture = deterministic rules/templates; live = an LLM was used
                       source_detail: string }     // "rules" | "template" | "router <provider:model>" | "<provider:model>" | "template fallback after <provider:model>"
// safety.reason may be e.g. "glucose_below_54", "low_with_symptoms", "symptoms", "dose", "llm_dose",
// "hypo_reading" / "hyper_reading" (a reading < 70 or > 300: the reply is always the fixed safety message).
interface ToolCall { name: string; args: Record<string, unknown>; output: unknown }
POST /api/speech/stt multipart {audio: Blob, lang} -> {text: string; source}   (501 in demo mode => use the browser)
POST /api/speech/tts {text, lang} -> audio/mpeg bytes (404 => use browser speechSynthesis)
GET  /api/demo/voice_samples -> {lang: Lang; prompt: string; audio_url: string /* signed URL, or "" */}[]
GET  /api/audio/{key}.mp3?exp=&sig= -> audio/mpeg (public, signature required: 403 bad/expired, 404 unknown)
// Recorded demo audio lives in backend/fixtures/audio/; live TTS is cached in backend/data/cache/tts/ (gitignored).

// ---------- lab report -> FHIR ----------
GET  /api/lab/samples -> {id, title, image_url}[]
POST /api/lab/parse multipart {file} OR {sample_id} -> {fields: LabField[]; source}
interface LabField { code: string; name: string; value: number|string; unit: string; ref_range: string; implausible: boolean; loinc?: string }
POST /api/lab/confirm {patient_id, fields: LabField[]} -> {bundle_id: string; resource_count: number}
GET  /api/fhir/{pid}/bundle -> FHIR R4 Bundle JSON (downloadable)

// ---------- doctor ----------
GET /api/doctor/panel -> PatientSummary[] (sorted by risk_7d desc) 
GET /api/doctor/brief/{pid} -> { patient: PatientDetail; tir_7d: number; mean_glucose: number; gmi: number; hypo_events_7d: number;
                                  hyper_events_7d: number; daily_profile: Quantiles /* 24 h AGP-style */;
                                  top_driver: string /* largest driver of the patient's own 4-h forecast with NO new meal */;
                                  top_driver_detail?: {name: string; contribution: number; source: string; basis: string} | null;
                                  suggestions: string[]; generated_at: string }

// ---------- trust ----------
GET /api/reports -> {name: string; title: string; generated_at: string}[]
GET /api/reports/{name} -> JSON (see reports/*.json; names: sensor_ladder, calibration_length, baselines, nbp_value,
                                 transfer, subgroups, calibration_curve, error_grid, agent_multilingual, summary)
// sensor_ladder.json also has recent_prick_value {definition, n_forecasts, n_patients, rmse_with_prick{h},
//   rmse_without{h}, rmse60_difference_ci: [point, lo, hi]} and by_hours_since_reading
//   [{hours_since_reading, n, rmse60, coverage90_60, width90_60}];
// transfer.json rows carry n_people and n_recordings (ShanghaiT2DM: recordings != people);

// ---------- demo ----------
GET /api/demo/tour -> {steps: {id: string; title_en: string; body_en: string; route: string; action?: string}[]}
GET /api/health -> {ok: true; mode: "demo"|"live"}
```

`reports/summary.json` shape (Trust panel headline):
```json
{ "generated_at": "...", "dataset": "CGMacros v1.0.0", "n_patients_eval": 0,
  "ladder": [{"level":"full","rmse":{"30":0,"60":0,"90":0,"120":0},"auroc_high":0,"auprc_high":0,"auroc_low":0,"coverage90":0,"width90":0}],
  "limitations": ["..."] }
```

---

## Replay clock, readings, evidence, ownership and operations (typed in `backend/nemotwins/api/schemas.py`, tested in `backend/tests/test_api_flows.py`)


```ts
// ---------- replay clock (per user + persona, persisted) ----------
interface Replay { now: string; day: number; offset_min: number; max_offset_min: 720; label_en: string; mode: "replay" }
TwinState.replay: Replay
POST /api/twin/{pid}/advance {ladder, minutes /*15..240*/} -> TwinState
      // propagates through the dataset's recorded meals/activity; the ladder's scheduled pricks inside the
      // window are assimilated at their own times (CGM samples for ladder "full")
POST /api/twin/{pid}/reveal?lang= {ladder, assimilate: boolean} -> {
      reference: { t: string; value: number; source_en: "Dataset reference CGM — hidden from the twin until revealed" };
      before: { estimate: number; band: Band; forecast_peak: number; p_high: Prob };
      after: Assimilation | null }                       // "Watch the twin learn"
POST /api/twin/{pid}/reset -> {ok:true}                  // also resets the replay clock

// ---------- assimilate (changed request) ----------
POST /api/twin/{pid}/assimilate?lang= {ladder, value, unit: "mg/dL"|"mmol/L", observed_at?: string, idempotency_key?: string}
      // observed_at more than 30 min from the replay now -> 422 {detail:{code:"stale_observation", message}}
Assimilation += {
  safety: { level: "ok"|"low"|"very_low"|"high"|"very_high"; emergency: boolean; title: string; message: string; actions: string[] };
  width_change: { now: {before:number; after:number; signed_pct:number};
                  h120: {before:number; after:number; signed_pct:number; horizon_min:120} } }  // negative = narrower
Assimilation.narrowed_pct  // = -width_change.h120.signed_pct (may be negative: the band widened)
// the same safety policy (agent/safety.py assess_reading) runs for manual entry, chat and replay reveal

// ---------- probabilities, horizon, provenance (changed) ----------
interface Prob { p: number; freq_text: string; validated: boolean;
                 reliability?: { pred_lo: number; pred_hi: number; observed: number; n: number;
                                 ci_lo: number; ci_hi: number; source: "reports/calibration_curve.json" } }
// p_high: validated=true + held-out reliability of its probability bin (no particle-binomial interval)
// p_low:  validated=false (too few low-glucose events to validate)
Quantiles.validated_horizon_min: 120      // points after 120 min are exploratory
Forecast.provenance = { model_version; hybrid_trained_on; inputs_revision; prior_inputs: {field: {value, source, date}};
                        observations_used; replay_now }

// ---------- evidence receipt ----------
GET /api/twin/{pid}/receipt/{forecast_id}?lang=[&format=md] -> {
  forecast_id, persona_id, replay_now, generated_at,
  claims: { key; label_en; value; unit; status: "measured"|"estimated"|"simulated"|"validated"|"exploratory"|"not_validated";
            source: { kind: "tool"|"report"|"dataset"|"user"; ref: string } }[],
  inputs, model, tool_calls }

// ---------- ownership ----------
// forecasts / explain / receipt: only for the (user, persona) that created the forecast, else 404.
// FHIR resources, lab revisions, replay clocks, events and reviews are stored per user.

// ---------- EHR revisions ----------
LabField += { original_value; original_unit; collection_date }   // units converted deterministically in code
POST /api/lab/confirm  -> also stores a covariate revision (hba1c, bmi) for this user + persona;
                          the twin re-personalises (EHR-conditioned prior -> calibration) and caches are invalidated
PatientDetail.ehr += { provenance: {field: {value, source: "persona EHR"|"lab upload (confirmed)", collection_date, revision}},
                       revisions: [...] }
// FHIR: effectiveDateTime = collection date; Condition only when the report lists a diagnosis explicitly.

// ---------- clinician ----------
PatientSummary += { tar_7d_reference: {value, label_en: "Historical time above 180 (dataset reference CGM, last 7 days)"};
                    operational: {estimate, band, last_reading_age_h, p_high_2h, data_gap} }   // risk_7d = historical TAR
GET  /api/doctor/queue -> {pid, name, reasons: {kind: "missing_data"|"concerning_observation"|"model_risk"; detail_en}[],
                           freshness, review: {status: "unreviewed"|"reviewed"|"follow_up"; note; at; by}}[]
POST /api/doctor/review/{pid} {status, note}
// the brief uses the user's own events + replay clock; its walk suggestion comes from a computed what-if

// ---------- agent ----------
AgentReply += { claims: {slot; field; value; rendered}[]; pending_action?: {id; kind: "log_reading"|"log_meal"; summary_en; payload} }
// numbers in replies are rendered only through slots filled from tool fields; mutations need confirmation:
POST /api/agent/confirm {action_id, confirm: boolean} -> AgentReply

// ---------- ops ----------
GET /api/ready                 // db + model warm
// per-user rate limits on chat / stt / tts / meal/photo / lab/parse -> 429 + Retry-After; bounded uploads -> 413
// sample_id must be a manifest id (unknown -> 404); live sample parses go to data/cache/runtime/<user>/, never fixtures/
// what_if responses carry assumptions_en[] and label_en "Model simulation — not a proven effect"
```

Public (no token): `/api/health`, `/api/ready`, `/api/auth/login`, `/api/samples/*`, `/api/reports/figures/*`.
`/api/audio/*` needs a valid signature (`?exp=&sig=`) instead of a bearer token.
