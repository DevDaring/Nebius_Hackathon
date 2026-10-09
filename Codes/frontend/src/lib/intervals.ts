import type { Band, BodyView, Quantiles, TwinState } from "@/api/types";
import { parseTime } from "./format";

/**
 * The twin reports three differently defined glucose intervals. They are NOT interchangeable and
 * must never be averaged or shown under the same label (regression: at an estimate of 154 mg/dL the
 * stage tile said "likely 116–192" while the body card said "90% likely 142–167" for the same moment):
 *
 * - calibratedNow  `state.band` — the present-state 90% range, conformally calibrated: the backend
 *   widens the particle spread to at least the held-out 30-minute conformal quantile for this sensor
 *   level and time since the last reading. Time origin: the replay clock "now".
 * - particleSpread `history.virtual_cgm.q05/q95` and the body view's blood band at t = now — the raw
 *   5th–95th percentile of the particle filter. Not calibrated (it under-covers), so usually narrower.
 * - forecastBand   `forecast.traj.q05/q95` and the body view's blood band after now — the particle
 *   forecast widened to the conformal 90% band at each evaluated horizon (exploratory beyond 120 min).
 */
export type IntervalKind = "calibratedNow" | "particleSpread" | "forecastBand";

export interface LabelledInterval {
  kind: IntervalKind;
  lo: number;
  hi: number;
  /** Nominal level (90% band / 5th–95th percentile). Only calibratedNow and forecastBand are calibrated. */
  level: 0.9;
  calibrated: boolean;
  /** The replay-clock time the interval describes. */
  at: string;
  /** Minutes after the replay now (0 = now). */
  horizonMin: number;
}

const mk = (kind: IntervalKind, b: Band, at: string, horizonMin: number): LabelledInterval => ({
  kind,
  lo: b.lo,
  hi: b.hi,
  level: 0.9,
  calibrated: kind !== "particleSpread",
  at,
  horizonMin,
});

/** The stage "Estimated now" tile: the calibrated present-state band. */
export function stateBand(s: Pick<TwinState, "band" | "now" | "replay">): LabelledInterval {
  return mk("calibratedNow", s.band, s.replay?.now ?? s.now, 0);
}

/** A point of the past/now virtual CGM: raw particle spread. */
export function historyBandAt(q: Quantiles, i: number, now: string): LabelledInterval {
  const at = q.t[i];
  return mk("particleSpread", { lo: q.q05[i], hi: q.q95[i] }, at, Math.round((parseTime(at).getTime() - parseTime(now).getTime()) / 60_000));
}

/** Which definition a chart point uses: up to now it is the particle spread, after now the forecast band. */
export function kindAtTime(tMs: number, nowMs: number): IntervalKind {
  return tMs > nowMs ? "forecastBand" : "particleSpread";
}

/** Body view blood band at step `idx` (t[0] = replay now is the raw particle spread, later steps are forecast bands). */
export function bodyBloodBand(view: Pick<BodyView, "t">, idx: number, lo: number, hi: number): LabelledInterval {
  return mk(idx === 0 ? "particleSpread" : "forecastBand", { lo, hi }, view.t[idx] ?? view.t[0], idx * 5);
}

/** i18n keys for an interval's short label (with {{lo}}/{{hi}}) and its explanation. */
export const intervalKeys = (kind: IntervalKind) => ({ short: `interval.${kind}.short`, label: `interval.${kind}.label`, explain: `interval.${kind}.explain` });
