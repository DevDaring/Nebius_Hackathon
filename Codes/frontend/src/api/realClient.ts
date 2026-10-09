import type {
  AdminIntegrations,
  AgentReply,
  BodyView,
  ApiClient,
  Capabilities,
  Assimilation,
  DoctorBrief,
  Explanation,
  Food,
  FoodSwap,
  Forecast,
  Health,
  LabConfirm,
  LabParse,
  LoginResponse,
  MealParse,
  NextBestPrick,
  Outlook,
  PatientDetail,
  QueueItem,
  Ready,
  Receipt,
  ReviewState,
  RevealResult,
  PatientSummary,
  ReportMeta,
  Sample,
  Tour,
  TwinState,
  User,
  VoiceSample,
  WhatIf,
} from "./types";
import { ApiError, request } from "./http";

const enc = encodeURIComponent;

function form(entries: Record<string, string | Blob | undefined>, filename?: string): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(entries)) {
    if (v === undefined) continue;
    if (v instanceof Blob) fd.append(k, v, v instanceof File ? v.name : filename ?? k);
    else fd.append(k, v);
  }
  return fd;
}

export const realClient: ApiClient = {
  login: (username, password) =>
    request<LoginResponse>("/auth/login", { body: { username, password }, auth: false }),
  demoSession: () => request<LoginResponse>("/auth/demo", { method: "POST", auth: false }),
  me: () => request<User>("/auth/me"),
  health: () => request<Health>("/health", { auth: false }),
  capabilities: () => request<Capabilities>("/capabilities", { auth: false }),
  adminIntegrations: () => request<AdminIntegrations>("/admin/integrations"),
  patients: () => request<PatientSummary[]>("/patients"),
  patient: (pid) => request<PatientDetail>(`/patients/${enc(pid)}`),
  twinState: (pid, ladder, reveal) =>
    request<TwinState>(`/twin/${enc(pid)}/state?ladder=${enc(ladder)}${reveal ? "&reveal=1" : ""}`),
  forecast: (pid, body) => request<Forecast>(`/twin/${enc(pid)}/forecast`, { body: { ...body } }),
  whatIf: (pid, body) => request<WhatIf>(`/twin/${enc(pid)}/what_if`, { body: { ...body } }),
  body: (pid, body) => request<BodyView>(`/twin/${enc(pid)}/body`, { body: { ...body } }),
  nextBestPrick: (pid, ladder) => request<NextBestPrick>(`/twin/${enc(pid)}/next_best_prick?ladder=${enc(ladder)}`),
  assimilate: (pid, body, lang) =>
    request<Assimilation>(`/twin/${enc(pid)}/assimilate${lang ? `?lang=${enc(lang)}` : ""}`, { body: { ...body } }),
  advance: (pid, body) => request<TwinState>(`/twin/${enc(pid)}/advance`, { body: { ...body } }),
  reveal: (pid, body, lang) => request<RevealResult>(`/twin/${enc(pid)}/reveal${lang ? `?lang=${enc(lang)}` : ""}`, { body: { ...body } }),
  receipt: (pid, fid, lang) => request<Receipt>(`/twin/${enc(pid)}/receipt/${enc(fid)}?lang=${enc(lang)}`),
  receiptMarkdown: (pid, fid, lang) => request<string>(`/twin/${enc(pid)}/receipt/${enc(fid)}?lang=${enc(lang)}&format=md`, { text: true }),
  outlook: (pid, ladder) => request<Outlook>(`/twin/${enc(pid)}/outlook_90d?ladder=${enc(ladder)}`),
  explain: (pid, forecastId) => request<Explanation>(`/twin/${enc(pid)}/explain/${enc(forecastId)}`),
  resetTwin: (pid) => request<{ ok: true }>(`/twin/${enc(pid)}/reset`, { method: "POST" }),
  foodSearch: (q, lang) => request<Food[]>(`/food/search?q=${enc(q)}&lang=${enc(lang)}`),
  foodSwaps: (lang) => request<FoodSwap[]>(`/food/swaps?lang=${enc(lang)}`),
  mealSamples: () => request<Sample[]>("/meal/samples"),
  // Contract says "multipart {image} OR {sample_id}": both are sent as multipart form fields.
  mealPhoto: (input) =>
    request<MealParse>("/meal/photo", {
      body: "image" in input ? form({ image: input.image }) : form({ sample_id: input.sample_id }),
    }),
  agentChat: (body, signal) => request<AgentReply>("/agent/chat", { body: { ...body }, signal }),
  agentConfirm: (body, signal) => request<AgentReply>("/agent/confirm", { body: { ...body }, signal }),
  voiceSamples: () => request<VoiceSample[]>("/demo/voice_samples"),
  labSamples: () => request<Sample[]>("/lab/samples"),
  labParse: (input) =>
    request<LabParse>("/lab/parse", {
      body: "file" in input ? form({ file: input.file }) : form({ sample_id: input.sample_id }),
    }),
  labConfirm: (patient_id, fields) => request<LabConfirm>("/lab/confirm", { body: { patient_id, fields } }),
  fhirBundle: (pid) => request<unknown>(`/fhir/${enc(pid)}/bundle`),
  doctorPanel: () => request<PatientSummary[]>("/doctor/panel"),
  doctorBrief: (pid) => request<DoctorBrief>(`/doctor/brief/${enc(pid)}`),
  doctorQueue: () => request<QueueItem[]>("/doctor/queue"),
  doctorReview: (pid, body) => request<{ pid: string; review: ReviewState } | ReviewState>(`/doctor/review/${enc(pid)}`, { body: { ...body } }),
  ready: () => request<Ready>("/ready"),
  reportsList: () => request<ReportMeta[]>("/reports"),
  report: async (name) => {
    try {
      return await request<unknown>(`/reports/${enc(name)}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
  demoTour: () => request<Tour>("/demo/tour"),
};
