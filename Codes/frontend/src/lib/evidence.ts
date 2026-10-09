import type { Assimilation, ClaimStatus, Prob, Receipt, SafetyLevel, WidthChange, WidthChangeAt } from "@/api/types";

/** Visual tone and i18n keys for each evidence status (Evidence Receipt chips). */
export const STATUS_META: Record<ClaimStatus, { tone: "teal" | "ink" | "violet" | "marigold" | "slate" | "coral"; icon: "ruler" | "sigma" | "flask" | "check" | "compass" | "alert" }> = {
  measured: { tone: "teal", icon: "ruler" },
  estimated: { tone: "ink", icon: "sigma" },
  simulated: { tone: "violet", icon: "flask" },
  validated: { tone: "teal", icon: "check" },
  exploratory: { tone: "slate", icon: "compass" },
  not_validated: { tone: "coral", icon: "alert" },
};

export const isClaimStatus = (s: unknown): s is ClaimStatus => typeof s === "string" && s in STATUS_META;

/** Safety levels that must take visual priority over any success message. */
export const URGENT: SafetyLevel[] = ["low", "very_low", "high", "very_high"];
export const isUrgent = (level: SafetyLevel | undefined | null) => !!level && URGENT.includes(level);

/**
 * Signed band-width change of an assimilation, at the named horizon. When width_change is absent,
 * band_before/band_after (the current band) and a clipped narrowed_pct are converted here
 * without clipping so a widening band is never reported as "unchanged".
 */
export function widthChange(a: Assimilation): WidthChange {
  if (a.width_change?.now && a.width_change?.h120) return a.width_change;
  const wb = a.band_before.hi - a.band_before.lo;
  const wa = a.band_after.hi - a.band_after.lo;
  const now: WidthChangeAt = { before: wb, after: wa, signed_pct: wb > 0 ? ((wa - wb) / wb) * 100 : 0 };
  return { now, h120: { ...now, horizon_min: 0 } };
}

export type WidthDirection = "narrower" | "wider" | "same";
export function direction(signedPct: number): WidthDirection {
  if (!Number.isFinite(signedPct) || Math.abs(signedPct) < 1) return "same";
  return signedPct < 0 ? "narrower" : "wider";
}

/** Peak difference of a what-if, with its interval when the backend sends one. */
export function peakDelta(w: { delta_peak: number | { mean: number; lo: number; hi: number }; delta_peak_ci?: { lo: number; hi: number } }): { mean: number; lo: number | null; hi: number | null } {
  const d = w.delta_peak;
  const ci = w.delta_peak_ci;
  const okCi = ci && Number.isFinite(ci.lo) && Number.isFinite(ci.hi);
  if (typeof d === "number") return { mean: d, lo: okCi ? ci!.lo : null, hi: okCi ? ci!.hi : null };
  return { mean: d.mean, lo: Number.isFinite(d.lo) ? d.lo : null, hi: Number.isFinite(d.hi) ? d.hi : null };
}

/** Probability value from a Prob, a bare number (reveal.before.p_high), or null. */
export function probValue(p: Prob | number | null | undefined): number | null {
  if (typeof p === "number") return Number.isFinite(p) ? p : null;
  if (p && typeof p.p === "number" && Number.isFinite(p.p)) return p.p;
  return null;
}

/** Held-out reliability as "out of 10" numbers for the sentence shown under the risk. */
export function reliabilityTenths(p: Prob | null | undefined): { said: number; happened: number; lo: number; hi: number; n: number } | null {
  const r = p?.reliability;
  if (!r || ![r.observed, r.ci_lo, r.ci_hi, r.n].every((x) => typeof x === "number" && Number.isFinite(x))) return null;
  const ten = (x: number) => Math.round(Math.min(1, Math.max(0, x)) * 10);
  return { said: ten(p!.p), happened: ten(r.observed), lo: ten(r.ci_lo), hi: ten(r.ci_hi), n: r.n };
}

/** Markdown receipt built in the browser (offline mode, or when the server Markdown fails). */
export function receiptToMarkdown(r: Receipt, labels: { title: string; status: (s: ClaimStatus) => string; claim: string; value: string; source: string }): string {
  const rows = r.claims.map((c) => `| ${c.label_en} | ${c.value ?? "—"}${c.unit ? ` ${c.unit}` : ""} | ${labels.status(c.status)} | ${c.source.kind}: ${c.source.ref} |`);
  return [
    `# ${labels.title}`,
    "",
    `- forecast_id: ${r.forecast_id}`,
    `- persona: ${r.persona_id}`,
    `- replay_now: ${r.replay_now}`,
    `- generated_at: ${r.generated_at}`,
    "",
    `| ${labels.claim} | ${labels.value} | Status | ${labels.source} |`,
    "|---|---|---|---|",
    ...rows,
    "",
    "## Model",
    "```json",
    JSON.stringify(r.model ?? {}, null, 2),
    "```",
    "## Inputs",
    "```json",
    JSON.stringify(r.inputs ?? {}, null, 2),
    "```",
    "",
  ].join("\n");
}

/** Save text as a file in the browser. */
export function downloadText(text: string, filename: string, type = "text/markdown") {
  const blob = new Blob([text], { type: `${type};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
