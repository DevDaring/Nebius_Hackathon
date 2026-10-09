// Offline mock evaluation report. Illustrative only: mode "mock" makes the Trust page say so
// (it is never presented as a live result), and no other report is served in offline mode.
import type { ReportMeta } from "@/api/types";
import { NOW, fmtLocal } from "./sim";

const LANGS = ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"];
const f = (n: number, k: number) => ({ n, k, rate: Math.round((k / n) * 1000) / 1000 });

export function mockAgentMultilingual(): Record<string, unknown> {
  const passByLang = [12, 11, 11, 10, 12, 10];
  return {
    generated_at: fmtLocal(NOW),
    generated_by: "offline mock",
    suite: "agent_multilingual (offline mock)",
    split: "heldout",
    mode: "mock",
    repeats: 1,
    languages: LANGS,
    models: { chat: "offline-mock (no model called)", provider: "offline_mock", guardrails: false },
    n_runs: 120,
    n_cases: 20,
    metrics: {
      pass: f(120, 66),
      numbers_ok: f(120, 117),
      locale_ok: f(120, 120),
      clarification_when_required: f(12, 9),
      unnecessary_clarification: f(36, 2),
      inappropriate_refusal: f(60, 3),
      justified_refusal: f(24, 19),
      engine_result_invariance_across_languages: f(10, 5),
    },
    per_language: Object.fromEntries(LANGS.map((l, i) => [l, { pass: f(20, passByLang[i]), locale_ok: f(20, 20) }])),
    per_category: {
      ambiguous_portion: f(12, 9),
      injection: f(12, 8),
      legit: f(24, 13),
      medication: f(12, 12),
      normal: f(12, 5),
      stale_reading: f(12, 11),
      unanswerable_evidence: f(12, 4),
      units_timestamps: f(12, 2),
      unsupported_causality: f(12, 2),
    },
    latency_ms: { p50: 40, p95: 120 },
    tokens: { prompt: 0, completion: 0 },
    cost_usd: null,
    reply_sources: { template: 120 },
    scoring: "deterministic checks only (no LLM judge, no human review in this report)",
    limitations: [
      "Offline mock: these numbers are illustrative placeholders produced without any model call; they are not an evaluation result.",
      "Synthetic persona and replay clock; not real patients.",
    ],
  };
}

export function mockReportsList(): ReportMeta[] {
  return [{ name: "agent_multilingual", title: "Multilingual Nemotron agent suite (offline mock)", generated_at: fmtLocal(NOW) }];
}
