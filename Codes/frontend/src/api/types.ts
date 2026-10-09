// Types mirror docs/API_CONTRACT.md and docs/API_CONTRACT_AGENT.md (agent fields are optional, so a reply
// without them still renders). Keep this file the single source of truth for
// response shapes on the frontend. Components consume these types only through the client.

// ---------- shared ----------
export type Ladder = "full" | "4" | "2" | "1" | "0";
export const LADDERS: Ladder[] = ["full", "4", "2", "1", "0"];
/** UI and answer languages: exactly the languages listed on the NVIDIA Nemotron 3 Nano model card. */
export type Lang = "en-US" | "es-ES" | "fr-FR" | "de-DE" | "it-IT" | "ja-JP";
export const LANGS: Lang[] = ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"];
export const DEFAULT_LANG: Lang = "en-US";
export const isLang = (v: unknown): v is Lang => typeof v === "string" && (LANGS as string[]).includes(v);

/** Held-out reliability of the calibration bin containing p (reports/calibration_curve.json). */
export interface Reliability {
  pred_lo: number;
  pred_hi: number;
  observed: number;
  n: number;
  ci_lo: number;
  ci_hi: number;
  source: string;
}
export interface Prob {
  p: number;
  freq_text: string;
  /** Optional interval; not sent by the backend (a binomial-of-particles interval is not a valid uncertainty of the risk). */
  lo?: number;
  hi?: number;
  /** True for P(>180 in 2 h), false for P(<70 in 2 h). */
  validated?: boolean;
  /** P(>180) only. */
  reliability?: Reliability | null;
}
export interface Band {
  lo: number;
  hi: number;
}
export interface Quantiles {
  t: string[];
  q05: number[];
  q25: number[];
  q50: number[];
  q75: number[];
  q95: number[];
  /** Points beyond this many minutes after the origin are exploratory (not evaluated). */
  validated_horizon_min?: number;
}
export interface Reading {
  t: string;
  value: number;
  kind: "cgm" | "fingerprick" | "lab";
}
export interface MealEvent {
  t: string;
  name: string;
  carbs: number;
  fibre?: number;
  protein?: number;
  fat?: number;
  photo_url?: string;
}

// ---------- auth ----------
export type Role = "patient" | "clinician" | "admin";
export interface User {
  username: string;
  display_name: string;
  roles: Role[];
  /** A private throw-away demo session (POST /auth/demo). */
  demo?: boolean;
}
export interface LoginResponse {
  access_token: string;
  user: User;
}
export interface Health {
  ok: true;
  mode: "demo" | "live";
}

// ---------- patients ----------
export interface PatientSummary {
  id: string;
  name: string;
  age: number;
  sex: "F" | "M";
  city: string;
  occupation: string;
  /** The persona's own language tag from the dataset fixtures (may be a code outside the six UI languages). */
  language: string;
  synthetic: true;
  source_note: string;
  hba1c: number;
  risk_7d: number;
  tir_7d: number;
  sparkline: number[];
  avatar_initials: string;
  /** The historical time above 180 from the dataset reference CGM (what risk_7d always was). */
  tar_7d_reference?: { value: number; label_en: string };
  /** Operational state from what the twin has actually seen. */
  operational?: {
    estimate: number;
    band: Band;
    last_reading_age_h: number | null;
    p_high_2h: number | null;
    data_gap: boolean;
  };
}
export interface EhrProvenance {
  value: number | string | null;
  source: string;
  collection_date?: string | null;
  revision?: number | string | null;
}
export interface EhrRevision {
  revision: number | string;
  fields?: Record<string, unknown>;
  created_at?: string;
  source?: string;
  [k: string]: unknown;
}
export interface PatientDetail extends PatientSummary {
  ehr: {
    bmi: number;
    diabetes_years: number;
    medications: string[];
    fasting_glucose?: number;
    ldl?: number;
    egfr?: number;
    conditions: string[];
    provenance?: Record<string, EhrProvenance>;
    revisions?: EhrRevision[];
  };
  calibration: { cgm_days: number; start: string; end: string };
  sleep_window: { start: string; end: string };
}

// ---------- twin ----------
export interface Abstain {
  flag: boolean;
  reason: string | null;
}
export interface Driver {
  name: string;
  label_en: string;
  contribution: number;
  source: "physiology" | "learned";
}
export interface PriorInput {
  value: number | string | null;
  source: string;
  date?: string | null;
}
/** What went into a forecast. */
export interface Provenance {
  model_version?: string;
  hybrid_trained_on?: string;
  inputs_revision?: number | string | null;
  prior_inputs?: Partial<Record<"hba1c" | "bmi" | "age" | "sex", PriorInput>>;
  observations_used?: number;
  replay_now?: string;
}
export interface Forecast {
  forecast_id: string;
  origin: string;
  horizon_min: number;
  traj: Quantiles;
  p_high: Prob;
  p_low: Prob;
  /** False (or absent) while P(<70) has not been validated: too few low events in the training data. */
  p_low_validated?: boolean;
  peak: { t: string; value: number };
  conformal_level: number;
  abstain: Abstain;
  drivers: Driver[];
  provenance?: Provenance;
}
export interface NextBestPrick {
  time: string;
  expected_gain_pct: number;
  reason: string;
  candidates: { t: string; gain_pct: number }[];
}
/** Replay clock (per user + persona). Distinct from wall-clock time. */
export interface ReplayClock {
  now: string;
  day: number;
  offset_min: number;
  max_offset_min: number;
  label_en: string;
  mode: "replay";
}
export interface TwinState {
  now: string;
  replay?: ReplayClock;
  ladder: Ladder;
  estimate: number;
  band: Band;
  freshness: { score: number; hours_since_reading: number; label: "fresh" | "ageing" | "stale" };
  last_observation: Reading | null;
  abstain: Abstain;
  ess: number;
  history: {
    virtual_cgm: Quantiles;
    readings: Reading[];
    true_cgm?: { t: string[]; v: number[] };
    meals: MealEvent[];
    steps: { t: string[]; v: number[] };
  };
  forecast: Forecast;
  /** False while P(<70) has not been validated (mirrors forecast.p_low_validated). */
  p_low_validated?: boolean;
  next_best_prick: NextBestPrick;
  target: { lo: number; hi: number };
}

export interface MealItem {
  food_id: string;
  units: number;
}
export interface MealInput {
  name?: string;
  carbs: number;
  carbs_sd?: number;
  fibre?: number;
  protein?: number;
  fat?: number;
  minutes_from_now?: number;
  items?: MealItem[];
}
export interface ForecastRequest {
  ladder: Ladder;
  horizon_min?: number;
  meal?: MealInput;
}

export interface Scenario {
  carb_scale?: number;
  swap?: { from: string; to: string; from_qty?: number; to_qty?: number };
  walk_min?: number;
  walk_after_min?: number;
  shift_min?: number;
  label?: string;
}
export interface WhatIfRequest {
  ladder: Ladder;
  base_meal: MealInput;
  scenario: Scenario;
}
/** POST /api/twin/{pid}/body: per-organ flows of the simplified physiology model (SIMULATED). */
export type OrganKey =
  | "stomach"
  | "intestine"
  | "gut_to_blood"
  | "liver"
  | "pancreas"
  | "insulin"
  | "insulin_uptake"
  | "exercise_uptake"
  | "unexplained";
export interface BodyRequest {
  ladder: Ladder;
  meal?: MealInput;
  /** Requires `meal`. */
  scenario?: Scenario;
}
export interface FluxSeries {
  q10: number[];
  q50: number[];
  q90: number[];
}
export interface BodyVariant {
  forecast_id: string;
  blood: { q05: number[]; q50: number[]; q95: number[] };
  fluxes: Record<OrganKey, FluxSeries>;
  learned_correction: number[];
}
export interface OrganMeta {
  key: OrganKey;
  label_en: string;
  unit: string;
  description_en: string;
  status: "simulated";
}
export interface BodyView {
  persona_id: string;
  replay_now: string;
  /** t[0] is the replay now, then every 5 min for 4 h (49 points). */
  t: string[];
  validated_horizon_min: number;
  label_en: string;
  validated_en: string;
  organs: OrganMeta[];
  baseline: BodyVariant;
  scenario: BodyVariant | null;
  scenario_label: string | null;
}
export interface WhatIf {
  baseline: Forecast;
  scenario: Forecast;
  delta_p_high: { mean: number; lo: number; hi: number };
  /** Signed mg/dL (scenario - baseline). May come with an interval. */
  delta_peak: number | { mean: number; lo: number; hi: number };
  /** Interval of the peak difference (simulation variability). */
  delta_peak_ci?: { lo: number; hi: number; interval_kind?: string };
  label_en?: string;
  assumptions_en?: string[];
  too_small_to_call: boolean;
  note: string;
}

export type GlucoseUnit = "mg/dL" | "mmol/L";
export interface AssimilateRequest {
  ladder: Ladder;
  value: number;
  /** Required; mmol/L is converted by the backend (x18.016). */
  unit: GlucoseUnit;
  /** Must be within 30 min of the replay now, else HTTP 422 {detail: {code: "stale_observation"}}. */
  observed_at?: string;
  /** Duplicates with the same key are ignored. */
  idempotency_key?: string;
  /** Optional free-text symptoms, read by the shared safety policy. */
  symptoms?: string;
}
export type SafetyLevel = "ok" | "low" | "very_low" | "high" | "very_high";
/** One shared safety policy (backend agent/safety.py) for manual entry, chat and replay. */
export interface Safety {
  level: SafetyLevel;
  emergency: boolean;
  title: string;
  message: string;
  actions: string[];
}
export interface WidthChangeAt {
  before: number;
  after: number;
  /** Negative = narrower. Not clipped. */
  signed_pct: number;
  horizon_min?: number;
}
export interface WidthChange {
  now: WidthChangeAt;
  h120: WidthChangeAt;
}
export interface Assimilation {
  state: TwinState;
  band_before: Band;
  band_after: Band;
  /** = -width_change.h120.signed_pct (may be negative). */
  narrowed_pct: number;
  innovation: number;
  safety?: Safety;
  width_change?: WidthChange;
}
export interface AdvanceRequest {
  ladder: Ladder;
  /** 15..240 */
  minutes: number;
}
export interface RevealRequest {
  ladder: Ladder;
  assimilate: boolean;
}
export interface RevealResult {
  reference: { t: string; value: number; source_en: string };
  before: {
    estimate: number;
    band: Band;
    forecast_peak: { t: string; value: number } | number | null;
    p_high: Prob | number | null;
  };
  after: Assimilation | null;
}

// ---------- evidence receipt ----------
export type ClaimStatus = "measured" | "estimated" | "simulated" | "validated" | "exploratory" | "not_validated";
export const CLAIM_STATUSES: ClaimStatus[] = ["measured", "estimated", "simulated", "validated", "exploratory", "not_validated"];
export interface ReceiptClaim {
  key: string;
  label_en: string;
  /** Label in the requested language (?lang=), when the backend has one. */
  label?: string;
  /** A number, a [lo, hi] pair, a time string or text. */
  value: number | string | number[] | null;
  /** "mg/dL", "%", "g", "probability", "proportion", "time", ... */
  unit?: string | null;
  status: ClaimStatus;
  source: { kind: "tool" | "report" | "dataset" | "user"; ref: string };
  /** Extra fields: t, n, ci, note, driver, freq_text... */
  [k: string]: unknown;
}
export interface Receipt {
  forecast_id: string;
  persona_id: string;
  replay_now: string;
  generated_at: string;
  claims: ReceiptClaim[];
  inputs: Record<string, unknown>;
  model: Record<string, unknown>;
  tool_calls: ToolCall[];
}

export interface Outlook {
  label: "projection";
  days: number[];
  tir_current: number[];
  tir_scenario: number[];
  ehba1c_current: number[];
  ehba1c_scenario: number[];
  scenario_label: string;
  note: string;
}

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  output: unknown;
}
export interface Explanation {
  physiology: Driver[];
  learned: Driver[];
  tool_calls: ToolCall[];
  text_en: string;
}

// ---------- meals & food ----------
export interface Food {
  id: string;
  name: string;
  name_en: string;
  unit: string;
  unit_label: string;
  grams_per_unit: number;
  /** Interpreted as per ONE unit (see README: contract ambiguity). */
  carbs_g: number;
  fibre_g: number;
  protein_g: number;
  fat_g: number;
  kcal: number;
  cuisine: string;
}
export interface FoodSwap {
  from: string;
  to: string;
  from_qty?: number;
  to_qty?: number;
  /** Label in the requested language (GET /api/food/swaps?lang=); label_en is the fallback when it is absent. */
  label?: string;
  label_en: string;
}
export interface Sample {
  id: string;
  title: string;
  image_url: string;
  /** Photo credit and licence, e.g. "Author - CC BY-SA 4.0". */
  attribution?: string;
  /** Meal samples: where the dishes come from ("us" | "india"), used to group the photos. */
  region?: string;
}
export interface MealDish {
  food_id: string | null;
  detected: string;
  name: string;
  units: number;
  unit: string;
  carbs: number;
  fibre: number;
  protein: number;
  fat: number;
  confidence: number;
  needs_pick: boolean;
  candidates?: Food[];
}
export interface MealParse {
  dishes: MealDish[];
  total: { carbs: number; fibre: number; protein: number; fat: number; kcal: number };
  carbs_sd: number;
  /** "manual" = built by hand in the UI from the food table (no photo, no model). */
  source: "fixture" | "live" | "manual";
  /** Which model proposed the dish candidates (never the nutrition numbers). */
  recognition?: { model: string; nvidia: boolean; provider: string } | null;
}

// ---------- capabilities ----------
export interface FeatureFlag {
  enabled: boolean;
  /** Short English explanation shown when the feature is off. */
  reason?: string | null;
  model?: string | null;
  nvidia?: boolean;
  provider?: string;
  engine?: string;
}
/** GET /api/capabilities (no auth, no secrets). */
export interface Capabilities {
  app_name: string;
  schema_version: string;
  locales: string[];
  default_locale: string;
  mode: "live" | "demo";
  inference: { provider: string; chat_model: string | null; planner_model?: string | null; available: boolean };
  features: {
    vision?: FeatureFlag;
    speech?: FeatureFlag;
    guardrails?: FeatureFlag;
    fish?: FeatureFlag;
    [k: string]: FeatureFlag | undefined;
  };
}

/** GET /api/admin/integrations (role admin). Never contains keys, tokens, prompts or user content. */
export interface AdminIntegrations {
  manifest: Record<string, unknown>;
  inference_health: { ok: boolean; model: string | null; latency_ms: number | null; checked_at: string | null; error_category: string | null };
  usage: {
    since: string | null;
    requests: number;
    errors: Record<string, number>;
    prompt_tokens: number;
    completion_tokens: number;
    by_model: Record<string, { requests: number; prompt_tokens: number; completion_tokens: number }>;
  };
  cloud: { auth_mode: string; configured: boolean; status: "not_configured" | "ok" | "error" | "sdk_missing" | string; detail: string | null; checked_at: string | null };
  deployment: { version: string | null; git_commit: string | null; environment: string | null };
  evaluation_jobs: { name: string; status: "completed" | "not_run" | "running" | "failed" | string; report: string | null; generated_at: string | null }[];
}

// ---------- agent / chat ----------
export type HighlightView = "stage" | "forecast" | "whatif" | "nbp" | "none";
export interface Highlight {
  view: HighlightView;
  from?: string;
  to?: string;
}
export interface ReferenceItem {
  title: string;
  url: string;
  domain: string;
  snippet: string;
}
export interface References {
  topic: string;
  chosen_by: string;
  provider: string;
  items: ReferenceItem[];
}

export interface AgentReply {
  reply: string;
  lang: Lang;
  intent: string;
  tool_calls: ToolCall[];
  grounding: { passed: boolean; numbers: string[]; fallback_used: boolean; ungrounded?: string[] };
  safety: { blocked: boolean; emergency: boolean; reason: string | null; injection?: boolean };
  highlight: Highlight;
  /** Always null (no speech model on Nebius Token Factory). */
  audio_url?: string | null;
  /** "live" or "fixture"; "template" / "rules" are also accepted. */
  source: string;
  /** Which path produced the reply: "rules", "template", "template fallback after <provider>", "<provider>:<model>"… */
  source_detail?: string;
  /** Every number in the reply, with the tool field it was rendered from. */
  claims?: AgentClaim[];
  /** A reading/meal the agent would log; nothing is changed until it is confirmed. */
  pending_action?: PendingAction | null;
  /** Server-side id of this agent execution. */
  execution_id?: string;
  schema_version?: string;
  /** One short question the assistant needs answered before it can simulate. */
  clarification?: Clarification | null;
  /** Labelled notes rendered under the reply (never hidden). */
  disclosures?: Disclosure[];
  /** Deterministic and guardrail checks. Only numbers === "passed" may say "All numbers checked". */
  checks?: ReplyChecks;
  /** Which model (if any) wrote this reply. */
  model?: { provider: string; model_id: string | null; live: boolean } | null;
  /** Further reading from allowlisted health sites (Tavily search on a fixed topic query). Display only. */
  references?: References | null;
}
export interface ClarificationOption {
  label: string;
  /** Sent back as the next user message when chosen. */
  text: string;
}
export interface Clarification {
  slot: "portion" | "time" | "unit" | "food" | string;
  question: string;
  options: ClarificationOption[];
  /** Choosing skip re-sends `text` with `skip_slots` in the chat request. */
  skip?: (ClarificationOption & { skip_slots?: string[] }) | null;
}
export type DisclosureKind = "stale_data" | "exploratory" | "ranking_uncertain" | "fallback" | "not_validated" | "wider_range";
export const DISCLOSURE_KINDS: DisclosureKind[] = ["stale_data", "exploratory", "ranking_uncertain", "fallback", "not_validated", "wider_range"];
export interface Disclosure {
  kind: DisclosureKind | string;
  text: string;
}
export interface ReplyChecks {
  numbers?: "passed" | "failed" | "not_run" | string;
  guardrails_input?: "passed" | "blocked" | "not_run" | "unavailable" | string;
  guardrails_output?: "passed" | "blocked" | "not_run" | "unavailable" | string;
}
export interface AgentClaim {
  slot: string;
  field: string;
  value: unknown;
  rendered: string;
}
export interface PendingAction {
  id: string;
  kind: "log_reading" | "log_meal";
  summary_en: string;
  payload: Record<string, unknown>;
}
export interface ChatRequest {
  patient_id: string;
  text: string;
  lang: Lang;
  ladder: Ladder;
  /** Slots the user chose to skip after a clarification (the answer then uses a wider range). */
  skip_slots?: string[];
}
/** A sample question for the chat page (GET /api/demo/voice_samples; text only). */
export interface VoiceSample {
  lang: string;
  prompt: string;
  /** Not played (no speech model on Token Factory). */
  audio_url?: string;
}

// ---------- lab ----------
export interface LabField {
  code: string;
  name: string;
  value: number | string;
  unit: string;
  ref_range: string;
  implausible: boolean;
  loinc?: string;
  /** The value and unit as printed on the report (value/unit are converted in code). */
  original_value?: number | string | null;
  original_unit?: string | null;
  collection_date?: string | null;
}
export interface LabParse {
  fields: LabField[];
  source: string;
  /** Diagnoses explicitly listed on the report (no Condition is made otherwise). */
  diagnoses?: string[];
  collection_date?: string | null;
}
export interface LabConfirm {
  bundle_id: string;
  resource_count: number;
  /** The covariate revision created for model-supported fields (hba1c, bmi). */
  revision?: number | string | EhrRevision | null;
}

// ---------- doctor ----------
export type ReviewStatus = "unreviewed" | "reviewed" | "follow_up";
export interface ReviewState {
  status: ReviewStatus;
  note: string | null;
  at: string | null;
  by: string | null;
}
export type QueueReasonKind = "missing_data" | "concerning_observation" | "model_risk";
export interface QueueItem {
  pid: string;
  name: string;
  reasons: { kind: QueueReasonKind; detail_en: string }[];
  /** Tolerated shapes: {label, hours_since_reading} | number of hours | label string. */
  freshness: { label?: string; hours_since_reading?: number | null; score?: number } | number | string | null;
  review: ReviewState;
  operational?: PatientSummary["operational"];
  [k: string]: unknown;
}
export interface DoctorBrief {
  patient: PatientDetail;
  tir_7d: number;
  mean_glucose: number;
  gmi: number;
  hypo_events_7d: number;
  hyper_events_7d: number;
  daily_profile: Quantiles;
  top_driver: string;
  suggestions: string[];
  generated_at: string;
  disclaimer?: string;
  tar_7d_reference?: { value: number; label_en: string };
  operational?: PatientSummary["operational"];
  replay?: ReplayClock;
  replay_now?: string;
  reference_note?: string;
  suggestion_details?: Record<string, unknown>[];
  [k: string]: unknown;
}
export interface Ready {
  ok: boolean;
  [k: string]: unknown;
}

// ---------- trust ----------
export interface ReportMeta {
  name: string;
  title: string;
  generated_at: string;
}
export type ReportName =
  | "sensor_ladder"
  | "calibration_length"
  | "baselines"
  | "nbp_value"
  | "transfer"
  | "subgroups"
  | "calibration_curve"
  | "error_grid"
  | "agent_multilingual"
  | "summary";

// ---------- demo ----------
export interface TourStep {
  id: string;
  title_en: string;
  body_en: string;
  route: string;
  action?: string;
}
export interface Tour {
  steps: TourStep[];
}

/** The full surface of the backend, as used by the UI. Real and mock clients implement it. */
export interface ApiClient {
  login(username: string, password: string): Promise<LoginResponse>;
  /** One-click private demo session (a fresh throw-away user on the synthetic personas). */
  demoSession(): Promise<LoginResponse>;
  me(): Promise<User>;
  health(): Promise<Health>;
  /** GET /api/capabilities (unauthenticated). */
  capabilities(): Promise<Capabilities>;
  /** GET /api/admin/integrations (role admin). */
  adminIntegrations(): Promise<AdminIntegrations>;
  patients(): Promise<PatientSummary[]>;
  patient(pid: string): Promise<PatientDetail>;
  twinState(pid: string, ladder: Ladder, reveal?: boolean): Promise<TwinState>;
  forecast(pid: string, body: ForecastRequest): Promise<Forecast>;
  whatIf(pid: string, body: WhatIfRequest): Promise<WhatIf>;
  body(pid: string, body: BodyRequest): Promise<BodyView>;
  nextBestPrick(pid: string, ladder: Ladder): Promise<NextBestPrick>;
  assimilate(pid: string, body: AssimilateRequest, lang?: Lang): Promise<Assimilation>;
  advance(pid: string, body: AdvanceRequest): Promise<TwinState>;
  reveal(pid: string, body: RevealRequest, lang?: Lang): Promise<RevealResult>;
  receipt(pid: string, forecastId: string, lang: Lang): Promise<Receipt>;
  /** GET .../receipt/{id}?format=md as text. */
  receiptMarkdown(pid: string, forecastId: string, lang: Lang): Promise<string>;
  outlook(pid: string, ladder: Ladder): Promise<Outlook>;
  explain(pid: string, forecastId: string): Promise<Explanation>;
  resetTwin(pid: string): Promise<{ ok: true }>;
  foodSearch(q: string, lang: Lang): Promise<Food[]>;
  foodSwaps(lang: Lang): Promise<FoodSwap[]>;
  mealSamples(): Promise<Sample[]>;
  mealPhoto(input: { image: File } | { sample_id: string }): Promise<MealParse>;
  agentChat(body: ChatRequest, signal?: AbortSignal): Promise<AgentReply>;
  agentConfirm(body: { action_id: string; confirm: boolean; lang?: Lang }, signal?: AbortSignal): Promise<AgentReply>;
  voiceSamples(): Promise<VoiceSample[]>;
  labSamples(): Promise<Sample[]>;
  labParse(input: { file: File } | { sample_id: string }): Promise<LabParse>;
  labConfirm(patientId: string, fields: LabField[]): Promise<LabConfirm>;
  fhirBundle(pid: string): Promise<unknown>;
  doctorPanel(): Promise<PatientSummary[]>;
  doctorBrief(pid: string): Promise<DoctorBrief>;
  doctorQueue(): Promise<QueueItem[]>;
  doctorReview(pid: string, body: { status: ReviewStatus; note: string }): Promise<{ pid: string; review: ReviewState } | ReviewState>;
  ready(): Promise<Ready>;
  reportsList(): Promise<ReportMeta[]>;
  /** Returns null when the report has not been generated yet (404). */
  report(name: ReportName): Promise<unknown | null>;
  demoTour(): Promise<Tour>;
}
