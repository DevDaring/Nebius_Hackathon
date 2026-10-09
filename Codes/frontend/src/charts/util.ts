import * as d3 from "./d3";
import type { Forecast, Quantiles } from "@/api/types";
import { parseTime } from "@/lib/format";

export interface QPoint {
  t: number;
  q05: number;
  q25: number;
  q50: number;
  q75: number;
  q95: number;
}

/** Quantiles (column arrays) → row points, dropping malformed entries. */
export function toPoints(q: Quantiles | null | undefined): QPoint[] {
  if (!q || !Array.isArray(q.t)) return [];
  const out: QPoint[] = [];
  for (let i = 0; i < q.t.length; i++) {
    const t = parseTime(q.t[i]).getTime();
    const p = { t, q05: q.q05?.[i], q25: q.q25?.[i], q50: q.q50?.[i], q75: q.q75?.[i], q95: q.q95?.[i] };
    if (Number.isFinite(t) && Number.isFinite(p.q50)) {
      out.push({
        t,
        q50: p.q50,
        q05: Number.isFinite(p.q05) ? p.q05 : p.q50,
        q25: Number.isFinite(p.q25) ? p.q25 : p.q50,
        q75: Number.isFinite(p.q75) ? p.q75 : p.q50,
        q95: Number.isFinite(p.q95) ? p.q95 : p.q50,
      });
    }
  }
  return out;
}

export type X = d3.ScaleTime<number, number>;
export type Y = d3.ScaleLinear<number, number>;

export const curve = d3.curveMonotoneX;

export function bandPath(pts: QPoint[], x: X, y: Y, lo: keyof QPoint, hi: keyof QPoint): string {
  return (
    d3
      .area<QPoint>()
      .x((d) => x(d.t))
      .y0((d) => y(d[lo]))
      .y1((d) => y(d[hi]))
      .curve(curve)(pts) ?? ""
  );
}

export function linePath(pts: QPoint[], x: X, y: Y, key: keyof QPoint = "q50"): string {
  return (
    d3
      .line<QPoint>()
      .x((d) => x(d.t))
      .y((d) => y(d[key]))
      .curve(curve)(pts) ?? ""
  );
}

/**
 * Split a curve at time tMs into the part up to tMs (validated) and the part from tMs on
 * (exploratory). The two parts share the boundary point so the drawn line stays continuous.
 */
export function splitAt(pts: QPoint[], tMs: number): { head: QPoint[]; tail: QPoint[] } {
  if (!pts.length || !Number.isFinite(tMs)) return { head: pts, tail: [] };
  const i = pts.findIndex((p) => p.t > tMs);
  if (i === -1) return { head: pts, tail: [] };
  if (i === 0) return { head: [], tail: pts };
  return { head: pts.slice(0, i), tail: pts.slice(i - 1) };
}

export function nearestIndex(pts: { t: number }[], t: number): number {
  if (pts.length === 0) return -1;
  const i = d3.bisector((d: { t: number }) => d.t).center(pts, t);
  return Math.max(0, Math.min(pts.length - 1, i));
}

export const EASE = [0.22, 1, 0.36, 1] as const;

/** Colours for paper surfaces (ink variants keep 3:1 for graphics on paper). */
export const SERIES = [
  "rgb(var(--teal-ink))",
  "rgb(var(--violet-ink))",
  "rgb(var(--marigold-ink))",
  "rgb(var(--coral-ink))",
  "rgb(var(--ink-3))",
];

/** Minutes after the origin that were evaluated (traj.validated_horizon_min; 120 otherwise). */
export const validatedHorizon = (f: Forecast | null | undefined) => f?.traj?.validated_horizon_min ?? 120;
