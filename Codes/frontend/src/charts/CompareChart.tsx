import { useId, useMemo } from "react";
import * as d3 from "./d3";
import { m as motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import type { Forecast } from "@/api/types";
import { useSize } from "@/hooks/useSize";
import { formatHour, parseTime } from "@/lib/format";
import { EASE, bandPath, linePath, splitAt, toPoints, validatedHorizon } from "./util";

export interface PinnedCurve {
  key: string;
  label: string;
  forecast: Forecast;
  color: string;
}

interface Props {
  baseline: Forecast;
  scenario: Forecast | null;
  pending?: boolean;
  scenarioLabel?: string;
  baselineLabel?: string;
  /** Up to two saved scenarios, drawn as thin labelled lines for comparison. */
  pinned?: PinnedCurve[];
  height?: number;
}

const M = { top: 16, right: 14, bottom: 28, left: 38 };

/** Baseline vs scenario forecast (both bands visible); the scenario curve morphs as the plan changes. */
export function CompareChart({ baseline, scenario, pending, scenarioLabel, baselineLabel, pinned = [], height: hOverride }: Props) {
  const { t, i18n } = useTranslation();
  const reduce = useReducedMotion();
  const uid = useId().replace(/:/g, "");
  const [ref, { width: rawW }] = useSize<HTMLDivElement>();
  const width = Math.max(280, rawW);
  const height = hOverride ?? (width < 520 ? 240 : 320);
  const iw = width - M.left - M.right;
  const ih = height - M.top - M.bottom;

  const b = useMemo(() => toPoints(baseline.traj), [baseline.traj]);
  const s = useMemo(() => toPoints(scenario?.traj ?? baseline.traj), [scenario?.traj, baseline.traj]);
  const pins = useMemo(() => pinned.map((p) => ({ ...p, pts: toPoints(p.forecast.traj) })), [pinned]);
  const all = [...b, ...s, ...pins.flatMap((p) => p.pts)];
  const x = d3
    .scaleTime()
    .domain([d3.min(all, (d) => d.t) ?? 0, d3.max(all, (d) => d.t) ?? 1])
    .range([0, iw]);
  const yMax = Math.min(420, Math.max(250, (d3.max(all, (d) => d.q95) ?? 240) + 15));
  const y = d3.scaleLinear().domain([40, yMax]).range([ih, 0]).clamp(true);
  const tr = reduce ? { duration: 0 } : { duration: 0.4, ease: EASE };
  const ticks = x.ticks(d3.timeHour.every(1)!);
  const vh = parseTime(baseline.origin).getTime() + validatedHorizon(baseline) * 60_000;
  const bs = splitAt(b, vh);
  const ss = splitAt(s, vh);

  const labels = (() => {
    const out: { key: string; text: string; y: number; color: string }[] = [];
    const end = (pts: typeof b) => (pts.length ? pts[pts.length - 1] : null);
    const be = end(b);
    const se = end(s);
    if (be && baselineLabel) out.push({ key: "b", text: baselineLabel, y: y(be.q50), color: "rgb(var(--moon))" });
    if (scenario && se && scenarioLabel) out.push({ key: "s", text: scenarioLabel, y: y(se.q50), color: "rgb(var(--marigold))" });
    for (const p of pins) {
      const pe = end(p.pts);
      if (pe) out.push({ key: p.key, text: p.label, y: y(pe.q50), color: p.color });
    }
    out.sort((a, c) => a.y - c.y);
    for (let i = 1; i < out.length; i++) if (out[i].y - out[i - 1].y < 15) out[i].y = out[i - 1].y + 15;
    return out.map((l) => ({ ...l, y: Math.min(ih - 4, Math.max(10, l.y - 8)) }));
  })();

  return (
    <div ref={ref} className="w-full" style={{ height }}>
      {rawW > 0 && (
        <svg width={width} height={height} role="img" aria-label={t("whatif.caption")}>
          <defs>
            <clipPath id={`c-${uid}`}>
              <rect width={iw} height={ih} />
            </clipPath>
            <pattern id={`h-${uid}`} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="7" stroke="rgb(var(--moon))" strokeOpacity="0.09" strokeWidth="3" />
            </pattern>
          </defs>
          <g transform={`translate(${M.left},${M.top})`}>
            <rect width={iw} y={y(180)} height={y(70) - y(180)} fill="rgb(var(--teal))" opacity={0.1} />
            {[70, 180].map((v) => (
              <g key={v}>
                <line x2={iw} y1={y(v)} y2={y(v)} stroke="rgb(var(--teal))" strokeOpacity={0.45} strokeDasharray="2 5" />
                <text x={-8} y={y(v)} dy="0.32em" textAnchor="end" className="chart-label" fill="rgb(var(--teal))">
                  {v}
                </text>
              </g>
            ))}
            {x(vh) < iw && (
              <g>
                <rect x={x(vh)} width={Math.max(0, iw - x(vh))} height={ih} fill={`url(#h-${uid})`} />
                <text x={iw - 4} y={10} textAnchor="end" className="chart-label" fill="rgb(var(--moon-3))">
                  {iw - x(vh) > 150 ? t("stage.exploratory") : t("evidence.status.exploratory")}
                </text>
              </g>
            )}
            {ticks.map((d) => (
              <text key={+d} x={x(d)} y={ih + 18} textAnchor="middle" className="chart-label" fill="rgb(var(--moon-3))">
                {formatHour(d, i18n.language)}
              </text>
            ))}
            <g clipPath={`url(#c-${uid})`} className={pending ? "opacity-60 transition-opacity" : "transition-opacity"}>
              <path d={bandPath(b, x, y, "q05", "q95")} fill="rgb(var(--violet))" opacity={0.2} />
              <path d={linePath(bs.head, x, y)} fill="none" stroke="rgb(var(--moon))" strokeOpacity={0.8} strokeWidth={2} strokeDasharray="6 5" />
              <path d={linePath(bs.tail, x, y)} fill="none" stroke="rgb(var(--moon))" strokeOpacity={0.45} strokeWidth={1.6} strokeDasharray="2 5" />
              {pins.map((p) => (
                <path key={p.key} d={linePath(p.pts, x, y)} fill="none" stroke={p.color} strokeWidth={1.8} strokeOpacity={0.9} />
              ))}
              {scenario && (
                <>
                  <g className="breathe">
                    <motion.path initial={false} animate={{ d: bandPath(s, x, y, "q05", "q95") }} transition={tr} fill="rgb(var(--marigold))" opacity={0.2} />
                  </g>
                  <motion.path initial={false} animate={{ d: bandPath(s, x, y, "q25", "q75") }} transition={tr} fill="rgb(var(--marigold))" opacity={0.16} />
                  <motion.path initial={false} animate={{ d: linePath(ss.head, x, y) }} transition={tr} fill="none" stroke="rgb(var(--marigold))" strokeWidth={2.8} strokeLinecap="round" />
                  <motion.path initial={false} animate={{ d: linePath(ss.tail, x, y) }} transition={tr} fill="none" stroke="rgb(var(--marigold))" strokeOpacity={0.75} strokeWidth={2.2} strokeDasharray="5 5" />
                </>
              )}
            </g>
            {scenario && (
              <motion.g initial={false} animate={{ x: x(new Date(scenario.peak.t)), y: y(scenario.peak.value) }} transition={tr}>
                <circle r={5} fill="rgb(var(--marigold))" stroke="rgb(var(--night))" strokeWidth={2} />
                <text y={-11} textAnchor="middle" className="chart-label" fontWeight={700} fill="rgb(var(--marigold))">
                  {Math.round(scenario.peak.value)}
                </text>
              </motion.g>
            )}
            <g transform={`translate(${x(new Date(baseline.peak.t))},${y(baseline.peak.value)})`}>
              <circle r={4} fill="rgb(var(--night))" stroke="rgb(var(--moon))" strokeWidth={2} />
              <text y={-10} textAnchor="middle" className="chart-label" fill="rgb(var(--moon-2))">
                {Math.round(baseline.peak.value)}
              </text>
            </g>
            {labels.map((l) => (
              <text key={l.key} x={iw - 4} y={l.y} textAnchor="end" className="chart-label" fontWeight={700} fill={l.color} paintOrder="stroke" stroke="rgb(var(--night))" strokeWidth={4} strokeLinejoin="round">
                {l.text}
              </text>
            ))}
          </g>
        </svg>
      )}
    </div>
  );
}
