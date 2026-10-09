import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./index";
import { ApiError } from "./http";
import type {
  AdvanceRequest,
  Assimilation,
  AssimilateRequest,
  BodyRequest,
  ForecastRequest,
  Ladder,
  Lang,
  ReportName,
  RevealRequest,
  RevealResult,
  ReviewState,
  ReviewStatus,
  TwinState,
  WhatIfRequest,
} from "./types";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";

/** Query keys include the mock flag so real and mock data never mix in the cache. */
const k = (...parts: unknown[]) => [useAuth.getState().mock ? "mock" : "live", ...parts];

export const qk = {
  patients: () => k("patients"),
  patient: (pid: string) => k("patient", pid),
  state: (pid: string, ladder: Ladder) => k("state", pid, ladder),
  nbp: (pid: string, ladder: Ladder) => k("nbp", pid, ladder),
  outlook: (pid: string, ladder: Ladder) => k("outlook", pid, ladder),
  explain: (pid: string, fid: string) => k("explain", pid, fid),
  receipt: (pid: string, fid: string, lang: string) => k("receipt", pid, fid, lang),
  report: (name: string) => k("report", name),
};

/**
 * GET /api/capabilities (no auth). When unavailable, callers use capFlags(undefined),
 * which gives the defaults (photo upload offered, fish allowed, no model id shown).
 */
export function useCapabilities() {
  return useQuery({ queryKey: k("capabilities"), queryFn: () => api.capabilities(), staleTime: 5 * 60_000, retry: 0 });
}

/** GET /api/admin/integrations: only requested when the signed-in user has the admin role. */
export function useAdminIntegrations(enabled: boolean) {
  return useQuery({ queryKey: k("adminIntegrations"), queryFn: () => api.adminIntegrations(), enabled, retry: 0, staleTime: 15_000 });
}

export function useHealth() {
  return useQuery({ queryKey: k("health"), queryFn: () => api.health(), staleTime: 5 * 60_000, retry: 0 });
}

export function usePatients() {
  return useQuery({ queryKey: qk.patients(), queryFn: () => api.patients(), staleTime: 60_000 });
}

/** The active persona id: the stored choice if valid, else the first persona. */
export function useActivePatientId(): string | null {
  const { data } = usePatients();
  const stored = useApp((s) => s.patientId);
  if (!data || data.length === 0) return stored;
  if (stored && data.some((p) => p.id === stored)) return stored;
  return data[0].id;
}

export function usePatient(pid: string | null) {
  return useQuery({
    queryKey: qk.patient(pid ?? ""),
    queryFn: () => api.patient(pid as string),
    enabled: !!pid,
    staleTime: 60_000,
  });
}

export function useTwinState(pid: string | null, ladder: Ladder) {
  return useQuery({
    queryKey: qk.state(pid ?? "", ladder),
    queryFn: () => api.twinState(pid as string, ladder),
    enabled: !!pid,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

export function useOutlook(pid: string | null, ladder: Ladder) {
  return useQuery({
    queryKey: qk.outlook(pid ?? "", ladder),
    queryFn: () => api.outlook(pid as string, ladder),
    enabled: !!pid,
    staleTime: 60_000,
  });
}

export function useExplain(pid: string | null, forecastId: string | null) {
  return useQuery({
    queryKey: qk.explain(pid ?? "", forecastId ?? ""),
    queryFn: () => api.explain(pid as string, forecastId as string),
    enabled: !!pid && !!forecastId,
    // 404 = the server no longer holds this forecast; the Why drawer re-asks for a fresh one instead
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
  });
}

export function useForecast(pid: string | null, body: ForecastRequest | null) {
  return useQuery({
    queryKey: k("forecast", pid, body),
    queryFn: () => api.forecast(pid as string, body as ForecastRequest),
    enabled: !!pid && !!body,
    placeholderData: keepPreviousData,
  });
}

export function useWhatIf(pid: string | null, body: WhatIfRequest | null) {
  return useQuery({
    queryKey: k("whatif", pid, body),
    queryFn: () => api.whatIf(pid as string, body as WhatIfRequest),
    enabled: !!pid && !!body,
    placeholderData: keepPreviousData,
  });
}

/**
 * Per-organ flows for the 3-D body view. `version` changes whenever the twin changes (replay offset,
 * newest observation, forecast id), so the body never shows flows from an older twin.
 */
export function useBody(pid: string | null, body: BodyRequest | null, version: string | number | null) {
  return useQuery({
    queryKey: k("body", pid, body?.ladder ?? null, version, body?.meal ?? null, body?.scenario ?? null),
    queryFn: () => api.body(pid as string, body as BodyRequest),
    enabled: !!pid && !!body,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

export function useFoodSwaps(lang: Lang) {
  return useQuery({ queryKey: k("swaps", lang), queryFn: () => api.foodSwaps(lang), staleTime: Infinity, placeholderData: keepPreviousData });
}

export function useFoodSearch(q: string, lang: Lang) {
  return useQuery({
    queryKey: k("food", q, lang),
    queryFn: () => api.foodSearch(q, lang),
    enabled: q.trim().length >= 2,
    placeholderData: keepPreviousData,
  });
}

export function useMealSamples() {
  return useQuery({ queryKey: k("mealSamples"), queryFn: () => api.mealSamples(), staleTime: Infinity });
}

export function useLabSamples() {
  return useQuery({ queryKey: k("labSamples"), queryFn: () => api.labSamples(), staleTime: Infinity });
}

/** Sample questions for the chat page (recordings, if any, are not played: there is no speech). */
export function useVoiceSamples() {
  return useQuery({ queryKey: k("voiceSamples"), queryFn: () => api.voiceSamples(), staleTime: 60 * 60 * 1000 });
}

export function useDoctorPanel() {
  return useQuery({ queryKey: k("panel"), queryFn: () => api.doctorPanel(), staleTime: 60_000 });
}

export function useDoctorBrief(pid: string | undefined) {
  return useQuery({ queryKey: k("brief", pid), queryFn: () => api.doctorBrief(pid as string), enabled: !!pid });
}

export function useReportsList() {
  return useQuery({ queryKey: k("reports"), queryFn: () => api.reportsList(), retry: 0 });
}

/** `enabled: false` skips the request (e.g. an optional report that GET /api/reports does not list yet). */
export function useReport(name: ReportName, enabled = true) {
  return useQuery({ queryKey: qk.report(name), queryFn: () => api.report(name), retry: 0, staleTime: 5 * 60_000, enabled });
}

export function useTour() {
  return useQuery({ queryKey: k("tour"), queryFn: () => api.demoTour(), staleTime: Infinity });
}

export function useReceipt(pid: string | null, forecastId: string | null, lang: Lang) {
  return useQuery({
    queryKey: qk.receipt(pid ?? "", forecastId ?? "", lang),
    queryFn: () => api.receipt(pid as string, forecastId as string, lang),
    enabled: !!pid && !!forecastId,
    retry: 0,
  });
}

export function useDoctorQueue() {
  return useQuery({ queryKey: k("queue"), queryFn: () => api.doctorQueue(), staleTime: 30_000, retry: 0 });
}

export function useDoctorReview() {
  const qc = useQueryClient();
  return useMutation<{ pid: string; review: ReviewState } | ReviewState, Error, { pid: string; status: ReviewStatus; note: string }>({
    mutationFn: ({ pid, status, note }) => api.doctorReview(pid, { status, note }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: k("queue") }),
  });
}

export function useReady() {
  return useQuery({ queryKey: k("ready"), queryFn: () => api.ready(), staleTime: 30_000, retry: 0 });
}

/**
 * Everything derived from a persona's twin (forecasts, what-ifs, receipts, briefs, the doctor
 * views). Called after any change to the twin: a reading, a replay advance or a reveal.
 */
function invalidateTwin(qc: ReturnType<typeof useQueryClient>, pid: string, keepLadder?: Ladder) {
  void qc.invalidateQueries({ queryKey: k("state", pid), predicate: (q) => keepLadder === undefined || q.queryKey[3] !== keepLadder });
  for (const key of ["nbp", "forecast", "whatif", "body", "outlook", "explain", "receipt", "brief"]) void qc.invalidateQueries({ queryKey: k(key, pid) });
  for (const key of ["panel", "queue", "patients"]) void qc.invalidateQueries({ queryKey: k(key) });
}

/** Assimilate a measured reading: writes the returned state straight into the cache. */
export function useAssimilate(pid: string | null, ladder: Ladder) {
  const qc = useQueryClient();
  const lang = useApp((s) => s.lang);
  return useMutation<Assimilation, Error, Omit<AssimilateRequest, "ladder">>({
    mutationFn: (body) => api.assimilate(pid as string, { ...body, ladder }, lang),
    onSuccess: (res) => {
      qc.setQueryData<TwinState>(qk.state(pid as string, ladder), res.state);
      invalidateTwin(qc, pid as string, ladder);
    },
  });
}

/** Move the persona's replay clock forward. Pricks scheduled inside the window are assimilated by the backend. */
export function useAdvance(pid: string | null, ladder: Ladder) {
  const qc = useQueryClient();
  return useMutation<TwinState, Error, Omit<AdvanceRequest, "ladder">>({
    mutationFn: (body) => api.advance(pid as string, { ...body, ladder }),
    onSuccess: (res) => {
      qc.setQueryData<TwinState>(qk.state(pid as string, ladder), res);
      invalidateTwin(qc, pid as string, ladder);
    },
  });
}

/** Reveal the dataset reference reading at the replay now ("Watch the twin learn"). */
export function useReveal(pid: string | null, ladder: Ladder) {
  const qc = useQueryClient();
  const lang = useApp((s) => s.lang);
  return useMutation<RevealResult, Error, Omit<RevealRequest, "ladder">>({
    mutationFn: (body) => api.reveal(pid as string, { ...body, ladder }, lang),
    onSuccess: (res) => {
      if (res.after) {
        qc.setQueryData<TwinState>(qk.state(pid as string, ladder), res.after.state);
        invalidateTwin(qc, pid as string, ladder);
      }
    },
  });
}
