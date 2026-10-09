import { useMemo } from "react";
import * as d3 from "./d3";
import { m as motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import type { Quantiles } from "@/api/types";
import { useSize } from "@/hooks/useSize";
import { formatClock, formatHour, parseTime, fixed } from "@/lib/format";
import { bandPath, linePath, toPoints } from "./util";

/* ---------------- Next-best-prick gain bars ---------------- */
export function GainBars({ candidates, best }: { candidates: { t: string; gain_pct: number }[]; best: string }) {
  const { t, i18n } = useTranslation();
  const reduce = useReducedMotion();
  const [ref, { width: rawW }] = useSize<HTMLDivElement>();
  const width = Math.max(220, rawW);
  const height = 92;
  const m = { top: 8, right: 4, bottom: 20, left: 4 };
  const pts = candidates.map((c) => ({ ts: parseTime(c.t).getTime(), g: c.gain_pct, t: c.t })).filter((p) => Number.isFinite(p.ts));
  if (pts.length === 0) return null;
  const t0 = pts[0].ts;
  const t1 = pts[pts.length - 1].ts + 30 * 60_000;
  const x = d3.scaleTime().domain([t0, t1]).range([m.left, width - m.right]);
  const y = d3.scaleLinear().domain([0, d3.max(pts, (p) => p.g) || 1]).range([height - m.bottom, m.top]);
  const bw = Math.max(2, x(t0 + 30 * 60_000) - x(t0) - 1.5);
  const bestTs = parseTime(best).getTime();
  const ticks = x.ticks(d3.timeHour.every(6)!);
  return (
    <div ref={ref} className="w-full" style={{ height }}>
      {rawW > 0 && (
        <svg width={width} height={height} role="img" aria-label={t("nbp.caption")}>
          {pts.map((p, i) => {
            const isBest = Math.abs(p.ts - bestTs) < 60_000;
            return (
              <motion.rect
                key={p.t}
                x={x(p.ts)}
                width={bw}
                rx={Math.min(3, bw / 2)}
                initial={reduce ? false : { y: height - m.bottom, height: 0 }}
                animate={{ y: y(p.g), height: height - m.bottom - y(p.g) }}
                transition={{ duration: 0.6, delay: reduce ? 0 : i * 0.012 }}
                fill={isBest ? "rgb(var(--marigold))" : "rgb(var(--ink-3))"}
                opacity={isBest ? 1 : 0.28}
              >
                <title>{`${formatClock(p.t, i18n.language)} · ${fixed(p.g, 1)}%`}</title>
              </motion.rect>
            );
          })}
          {ticks.map((d) => (
            <text key={+d} x={x(d)} y={height - 5} textAnchor="middle" className="chart-label" fill="rgb(var(--ink-3))">
              {formatHour(d, i18n.language)}
            </text>
          ))}
        </svg>
      )}
    </div>
  );
}

/* ---------------- Sparkline (48 h, hourly) ---------------- */
export function Sparkline({ values, width = 132, height = 36, tone = "ink" }: { values: number[]; width?: number; height?: number; tone?: "ink" | "moon" }) {
  const { t } = useTranslation();
  const v = values.filter((n) => Number.isFinite(n));
  if (v.length < 2) return <span className="text-xs text-ink-3">—</span>;
  const x = d3.scaleLinear().domain([0, v.length - 1]).range([2, width - 4]);
  const y = d3.scaleLinear().domain([40, Math.max(260, d3.max(v) ?? 200)]).range([height - 2, 2]);
  const line = d3.line<number>().x((_, i) => x(i)).y((d) => y(d)).curve(d3.curveMonotoneX)(v) ?? "";
  const col = tone === "moon" ? "rgb(var(--moon))" : "rgb(var(--ink-2))";
  const last = v[v.length - 1];
  return (
    <svg width={width} height={height} role="img" aria-label={t("a11y.sparkline")}>
      <rect x={0} width={width} y={y(180)} height={y(70) - y(180)} fill="rgb(var(--teal))" opacity={0.13} rx={3} />
      <path d={line} fill="none" stroke={col} strokeWidth={1.5} />
      <circle cx={x(v.length - 1)} cy={y(last)} r={2.8} fill={last > 180 ? "rgb(var(--coral))" : last < 70 ? "rgb(var(--violet))" : "rgb(var(--teal))"} />
    </svg>
  );
}

/* ---------------- AGP-style daily profile (paper) ---------------- */
export function AgpChart({ profile }: { profile: Quantiles }) {
  const { t, i18n } = useTranslation();
  const [ref, { width: rawW }] = useSize<HTMLDivElement>();
  const width = Math.max(300, rawW);
  const height = 200;
  const m = { top: 10, right: 10, bottom: 24, left: 34 };
  const pts = useMemo(() => toPoints(profile), [profile]);
  if (pts.length < 2) return <p className="text-sm text-ink-3">{t("common.notGenerated")}</p>;
  const x = d3.scaleTime().domain([pts[0].t, pts[pts.length - 1].t]).range([m.left, width - m.right]);
  const y = d3.scaleLinear().domain([40, Math.max(220, (d3.max(pts, (p) => p.q95) ?? 200) + 15)]).range([height - m.bottom, m.top]);
  const ticks = x.ticks(d3.timeHour.every(3)!);
  return (
    <div ref={ref} className="w-full" style={{ height }}>
      {rawW > 0 && (
        <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} preserveAspectRatio="xMinYMid meet" role="img" aria-label={t("doctor.profileCaption")}>
          <rect x={m.left} width={width - m.left - m.right} y={y(180)} height={y(70) - y(180)} fill="rgb(var(--teal))" opacity={0.12} />
          {[70, 180].map((v) => (
            <g key={v}>
              <line x1={m.left} x2={width - m.right} y1={y(v)} y2={y(v)} stroke="rgb(var(--teal-ink))" strokeOpacity={0.5} strokeDasharray="2 4" />
              <text x={m.left - 6} y={y(v)} dy="0.32em" textAnchor="end" className="chart-label" fill="rgb(var(--teal-ink))">
                {v}
              </text>
            </g>
          ))}
          <path d={bandPath(pts, x, y, "q05", "q95")} fill="rgb(var(--violet))" opacity={0.14} />
          <path d={bandPath(pts, x, y, "q25", "q75")} fill="rgb(var(--violet))" opacity={0.26} />
          <path d={linePath(pts, x, y)} fill="none" stroke="rgb(var(--violet-ink))" strokeWidth={2.2} />
          {ticks.map((d) => (
            <text key={+d} x={x(d)} y={height - 6} textAnchor="middle" className="chart-label" fill="rgb(var(--ink-3))">
              {formatHour(d, i18n.language)}
            </text>
          ))}
        </svg>
      )}
    </div>
  );
}

/* ---------------- Generic two-series line (90-day outlook) ---------------- */
export function TwoLineChart({
  xs,
  a,
  b,
  format,
  xLabel,
  ariaLabel,
  height = 170,
}: {
  xs: number[];
  a: number[];
  b: number[];
  format: (v: number) => string;
  xLabel: (v: number) => string;
  ariaLabel: string;
  height?: number;
}) {
  const [ref, { width: rawW }] = useSize<HTMLDivElement>();
  const width = Math.max(260, rawW);
  const m = { top: 18, right: 46, bottom: 24, left: 26 };
  const all = [...a, ...b].filter(Number.isFinite);
  if (xs.length < 2 || all.length < 2) return null;
  const x = d3.scaleLinear().domain([xs[0], xs[xs.length - 1]]).range([m.left, width - m.right]);
  const [lo, hi] = d3.extent(all) as [number, number];
  const pad = (hi - lo) * 0.25 || 1;
  const y = d3.scaleLinear().domain([lo - pad, hi + pad]).range([height - m.bottom, m.top]);
  const mk = (vals: number[]) => d3.line<number>().x((_, i) => x(xs[i])).y((d) => y(d)).curve(d3.curveMonotoneX)(vals) ?? "";
  const ticks = x.ticks(4);
  return (
    <div ref={ref} className="w-full" style={{ height }}>
      {rawW > 0 && (
        <svg width={width} height={height} role="img" aria-label={ariaLabel}>
          {y.ticks(3).map((v) => (
            <line key={v} x1={m.left} x2={width - m.right} y1={y(v)} y2={y(v)} stroke="rgb(var(--line))" />
          ))}
          <path d={mk(a)} fill="none" stroke="rgb(var(--ink-3))" strokeWidth={2} strokeDasharray="5 5" />
          <path d={mk(b)} fill="none" stroke="rgb(var(--marigold))" strokeWidth={2.6} />
          <text x={width - m.right + 6} y={y(a[a.length - 1])} dy="0.32em" className="chart-label" fill="rgb(var(--ink-2))">
            {format(a[a.length - 1])}
          </text>
          <text x={width - m.right + 6} y={y(b[b.length - 1])} dy="0.32em" className="chart-label" fontWeight={700} fill="rgb(var(--marigold-ink))">
            {format(b[b.length - 1])}
          </text>
          {ticks.map((d) => (
            <text key={d} x={x(d)} y={height - 6} textAnchor="middle" className="chart-label" fill="rgb(var(--ink-3))">
              {xLabel(d)}
            </text>
          ))}
        </svg>
      )}
    </div>
  );
}
