import * as d3 from "./d3";
import { fixed } from "@/lib/format";
import { m as motion, useReducedMotion } from "framer-motion";
import { useSize } from "@/hooks/useSize";
import { SERIES } from "./util";

export interface Series {
  key: string;
  label: string;
  values: { x: number; y: number }[];
  color?: string;
  dashed?: boolean;
}

/**
 * Ordered levels (e.g. full CGM -> no data) use one hue from strong to soft. color-mix keeps the
 * ramp correct in both themes because --violet-ink and --card are redefined for dark mode.
 */
export const RAMP = [100, 78, 60, 46, 34].map((p) => `color-mix(in oklab, rgb(var(--violet-ink)) ${p}%, rgb(var(--card)))`);

/** Multi-series line with direct end labels (no legend lookup). */
export function MultiLine({
  series,
  xLabel,
  yLabel,
  ariaLabel,
  height = 240,
  yFormat = (v: number) => String(v),
  zeroBased = true,
}: {
  series: Series[];
  xLabel: (x: number) => string;
  yLabel: string;
  ariaLabel: string;
  height?: number;
  yFormat?: (v: number) => string;
  zeroBased?: boolean;
}) {
  const [ref, { width: rawW }] = useSize<HTMLDivElement>();
  const width = Math.max(280, rawW);
  // Narrow screens: no end labels (they would collide); an HTML legend below carries identity.
  const narrow = width < 520;
  const m = { top: 30, right: narrow ? 14 : 104, bottom: 30, left: 40 };
  const xs = Array.from(new Set(series.flatMap((s) => s.values.map((v) => v.x)))).sort((a, b) => a - b);
  const ys = series.flatMap((s) => s.values.map((v) => v.y));
  if (xs.length === 0 || ys.length === 0) return null;
  const x = d3.scalePoint<number>().domain(xs).range([m.left, width - m.right]).padding(0.3);
  const lo = zeroBased ? 0 : (d3.min(ys) ?? 0) * 0.9;
  const y = d3.scaleLinear().domain([lo, (d3.max(ys) ?? 1) * 1.08]).nice().range([height - m.bottom, m.top]);
  // Spread end labels so they do not overlap.
  const ends = series
    .map((s, i) => ({ s, i, y: y(s.values[s.values.length - 1]?.y ?? 0) }))
    .sort((a, b) => a.y - b.y);
  for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 14) ends[k].y = ends[k - 1].y + 14;
  return (
    <div className="w-full">
    <div ref={ref} className="w-full" style={{ height }}>
      {rawW > 0 && (
        <svg width={width} height={height} role="img" aria-label={ariaLabel}>
          {y.ticks(4).map((v) => (
            <g key={v}>
              <line x1={m.left} x2={width - m.right} y1={y(v)} y2={y(v)} stroke="rgb(var(--line))" />
              <text x={m.left - 6} y={y(v)} dy="0.32em" textAnchor="end" className="chart-label" fill="rgb(var(--ink-3))">
                {yFormat(v)}
              </text>
            </g>
          ))}
          <text x={m.left - 30} y={m.top - 16} className="chart-label" fill="rgb(var(--ink-3))">
            {yLabel}
          </text>
          {xs.map((v) => (
            <text key={v} x={x(v)} y={height - 8} textAnchor="middle" className="chart-label" fill="rgb(var(--ink-3))">
              {xLabel(v)}
            </text>
          ))}
          {series.map((s, i) => {
            const col = s.color ?? SERIES[i % SERIES.length];
            const d = d3
              .line<{ x: number; y: number }>()
              .x((p) => x(p.x) ?? 0)
              .y((p) => y(p.y))(s.values.slice().sort((a, b) => a.x - b.x));
            return (
              <g key={s.key}>
                <path d={d ?? ""} fill="none" stroke={col} strokeWidth={2} strokeDasharray={s.dashed ? "5 4" : undefined} />
                {s.values.map((p) => (
                  <g key={p.x}>
                    <circle cx={x(p.x)} cy={y(p.y)} r={4} fill={col} stroke="rgb(var(--card))" strokeWidth={2} />
                    {/* bigger invisible hit target for the tooltip */}
                    <circle cx={x(p.x)} cy={y(p.y)} r={11} fill="transparent">
                      <title>{`${s.label} · ${xLabel(p.x)}: ${yFormat(p.y)}`}</title>
                    </circle>
                  </g>
                ))}
              </g>
            );
          })}
          {!narrow &&
            ends.map(({ s, i, y: ly }) => (
              <g key={s.key} transform={`translate(${width - m.right + 8},${ly})`}>
                <circle r={3.5} cx={3} fill={s.color ?? SERIES[i % SERIES.length]} />
                <text x={11} dy="0.32em" className="chart-label" fontWeight={600} fill="rgb(var(--ink-2))">
                  {s.label}
                </text>
              </g>
            ))}
        </svg>
      )}
    </div>
      {narrow && rawW > 0 && (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
          {series.map((s, i) => (
            <li key={s.key} className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color ?? SERIES[i % SERIES.length] }} aria-hidden />
              {s.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Vertical bars with a reference line (coverage vs nominal). */
export function RefBars({
  bars,
  reference,
  format,
  ariaLabel,
  refLabel,
}: {
  bars: { key: string; label: string; short?: string; value: number; sub?: string }[];
  reference: number;
  format: (v: number) => string;
  ariaLabel: string;
  refLabel: string;
}) {
  const reduce = useReducedMotion();
  const [ref, { width: rawW }] = useSize<HTMLDivElement>();
  const width = Math.max(260, rawW);
  const height = 280;
  const m = { top: 20, right: 10, bottom: 44, left: 40 };
  if (bars.length === 0) return null;
  const x = d3.scaleBand().domain(bars.map((b) => b.key)).range([m.left, width - m.right]).padding(0.35);
  const lo = Math.min(reference, d3.min(bars, (b) => b.value) ?? 0);
  const y = d3.scaleLinear().domain([Math.max(0, lo - 0.15), 1]).range([height - m.bottom, m.top]);
  return (
    <div ref={ref} className="w-full" style={{ height }}>
      {rawW > 0 && (
        <svg width={width} height={height} role="img" aria-label={ariaLabel}>
          {y.ticks(4).map((v) => (
            <g key={v}>
              <line x1={m.left} x2={width - m.right} y1={y(v)} y2={y(v)} stroke="rgb(var(--line))" />
              <text x={m.left - 6} y={y(v)} dy="0.32em" textAnchor="end" className="chart-label" fill="rgb(var(--ink-3))">
                {format(v)}
              </text>
            </g>
          ))}
          {bars.map((b) => {
            const off = Math.abs(b.value - reference) > 0.05;
            return (
              <g key={b.key}>
                <motion.rect
                  x={x(b.key)}
                  width={x.bandwidth()}
                  rx={6}
                  initial={reduce ? false : { y: y(y.domain()[0]), height: 0 }}
                  animate={{ y: y(b.value), height: y(y.domain()[0]) - y(b.value) }}
                  transition={{ duration: 0.7 }}
                  fill={off ? "rgb(var(--coral))" : "rgb(var(--teal))"}
                  opacity={0.85}
                />
                <text x={(x(b.key) ?? 0) + x.bandwidth() / 2} y={y(b.value) - 6} textAnchor="middle" className="chart-label" fontWeight={700} fill="rgb(var(--ink))">
                  {format(b.value)}
                </text>
                <text x={(x(b.key) ?? 0) + x.bandwidth() / 2} y={height - m.bottom + 16} textAnchor="middle" className="chart-label" fill="rgb(var(--ink-2))">
                  {x.bandwidth() < 64 && b.short ? b.short : b.label}
                  <title>{b.label}</title>
                </text>
                {b.sub && (
                  <text x={(x(b.key) ?? 0) + x.bandwidth() / 2} y={height - m.bottom + 30} textAnchor="middle" className="chart-label" fill="rgb(var(--ink-3))">
                    {b.sub}
                  </text>
                )}
              </g>
            );
          })}
          <line x1={m.left} x2={width - m.right} y1={y(reference)} y2={y(reference)} stroke="rgb(var(--ink))" strokeWidth={1.5} strokeDasharray="6 4" />
          <title>{refLabel}</title>
        </svg>
      )}
    </div>
  );
}

/** Reliability diagram: stated probability vs observed frequency. */
export function Reliability({
  curves,
  xLabel,
  yLabel,
  ariaLabel,
}: {
  curves: { key: string; label: string; points: { p: number; o: number; n?: number }[]; color: string; dashed?: boolean }[];
  xLabel: string;
  yLabel: string;
  ariaLabel: string;
}) {
  const [ref, { width: rawW }] = useSize<HTMLDivElement>();
  const size = Math.min(Math.max(240, rawW), 380);
  const m = { top: 12, right: 20, bottom: 40, left: 56 };
  const x = d3.scaleLinear().domain([0, 1]).range([m.left, size - m.right]);
  const y = d3.scaleLinear().domain([0, 1]).range([size - m.bottom, m.top]);
  const maxN = d3.max(curves.flatMap((c) => c.points.map((p) => p.n ?? 1))) ?? 1;
  const r = d3.scaleSqrt().domain([0, maxN]).range([2.5, 7]);
  return (
    <div ref={ref} className="w-full">
      {rawW > 0 && (
        <svg width={size} height={size} role="img" aria-label={ariaLabel} className="mx-auto block">
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <g key={v}>
              <line x1={x(0)} x2={x(1)} y1={y(v)} y2={y(v)} stroke="rgb(var(--line))" />
              <text x={x(0) - 6} y={y(v)} dy="0.32em" textAnchor="end" className="chart-label" fill="rgb(var(--ink-3))">
                {Math.round(v * 100)}%
              </text>
              <text x={x(v)} y={y(0) + 14} textAnchor="middle" className="chart-label" fill="rgb(var(--ink-3))">
                {Math.round(v * 100)}%
              </text>
            </g>
          ))}
          <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="rgb(var(--ink-3))" strokeDasharray="4 4" />
          <text x={(x(0) + x(1)) / 2} y={size - 6} textAnchor="middle" className="chart-label" fill="rgb(var(--ink-2))">
            {xLabel}
          </text>
          <text transform={`translate(12,${(y(0) + y(1)) / 2}) rotate(-90)`} textAnchor="middle" className="chart-label" fill="rgb(var(--ink-2))">
            {yLabel}
          </text>
          {curves.map((c) => {
            const pts = c.points.slice().sort((a, b) => a.p - b.p);
            const d = d3
              .line<{ p: number; o: number }>()
              .x((p) => x(p.p))
              .y((p) => y(p.o))(pts);
            return (
              <g key={c.key}>
                <path d={d ?? ""} fill="none" stroke={c.color} strokeWidth={2} strokeDasharray={c.dashed ? "5 4" : undefined} />
                {pts.map((p, i) => (
                  <circle key={i} cx={x(p.p)} cy={y(Math.min(1, Math.max(0, p.o)))} r={r(p.n ?? 1)} fill={c.dashed ? "rgb(var(--card))" : c.color} fillOpacity={0.9} stroke={c.dashed ? c.color : "rgb(var(--card))"} strokeWidth={c.dashed ? 2 : 1.5}>
                    <title>{`${c.label}: ${Math.round(p.p * 100)}% → ${Math.round(p.o * 100)}%${p.n ? ` (n=${p.n})` : ""}`}</title>
                  </circle>
                ))}
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

/** Horizontal share bars (e.g. error-grid zones). */
export function ShareBars({ items, ariaLabel }: { items: { key: string; label: string; value: number; tone: "good" | "ok" | "bad" }[]; ariaLabel: string }) {
  const reduce = useReducedMotion();
  const tone = { good: "bg-teal", ok: "bg-marigold", bad: "bg-coral" } as const;
  return (
    <ul className="space-y-2.5" aria-label={ariaLabel}>
      {items.map((it) => (
        <li key={it.key} className="grid grid-cols-[4.5rem_1fr_3.5rem] items-center gap-3 text-sm">
          <span className="font-medium text-ink-2">{it.label}</span>
          <span className="h-3 overflow-hidden rounded-full bg-paper-2">
            <motion.span
              className={`block h-full rounded-full ${tone[it.tone]}`}
              initial={reduce ? false : { width: 0 }}
              animate={{ width: `${Math.max(0.5, Math.min(100, it.value * 100))}%` }}
              transition={{ duration: 0.8 }}
            />
          </span>
          <span className="num text-right font-semibold">{fixed((it.value * 100), it.value < 0.1 ? 1 : 0)}%</span>
        </li>
      ))}
    </ul>
  );
}

/** Signed horizontal bars around zero (forecast drivers). */
export function SignedBars({
  items,
  format,
}: {
  items: { key: string; label: string; value: number }[];
  format: (v: number) => string;
}) {
  const reduce = useReducedMotion();
  const max = Math.max(1, ...items.map((i) => Math.abs(i.value)));
  return (
    <ul className="space-y-3">
      {items.map((it, idx) => {
        const w = (Math.abs(it.value) / max) * 50;
        const up = it.value >= 0;
        return (
          <li key={it.key}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span className="font-medium text-ink">{it.label}</span>
              <span className={`num shrink-0 font-semibold ${up ? "text-coral-ink" : "text-teal-ink"}`}>{format(it.value)}</span>
            </div>
            <div className="relative h-2.5 rounded-full bg-paper-2" aria-hidden>
              <span className="absolute left-1/2 top-[-3px] h-[16px] w-px bg-ink-3/60" />
              <motion.span
                className={`absolute top-0 h-full rounded-full ${up ? "bg-coral" : "bg-teal"}`}
                style={up ? { left: "50%" } : { right: "50%" }}
                initial={reduce ? false : { width: 0 }}
                animate={{ width: `${w}%` }}
                transition={{ duration: 0.7, delay: reduce ? 0 : idx * 0.06 }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Mean difference with a 95% interval per row, around a zero line (paired comparisons). */
export function ForestPlot({
  items,
  format,
  ariaLabel,
  betterLabel,
  worseLabel,
}: {
  items: { key: string; label: string; mean: number; lo: number; hi: number; sub?: string }[];
  format: (v: number) => string;
  ariaLabel: string;
  betterLabel: string;
  worseLabel: string;
}) {
  const reduce = useReducedMotion();
  const [ref, { width: rawW }] = useSize<HTMLDivElement>();
  const width = Math.max(260, rawW);
  const rowH = 56;
  const m = { top: 24, right: 16, bottom: 28, left: 16 };
  const height = m.top + m.bottom + items.length * rowH;
  if (!items.length) return null;
  const ext = Math.max(...items.flatMap((i) => [Math.abs(i.lo), Math.abs(i.hi), Math.abs(i.mean)])) * 1.25 || 1;
  const x = d3.scaleLinear().domain([-ext, ext]).range([m.left, width - m.right]).nice();
  return (
    <div ref={ref} className="w-full" style={{ height }}>
      {rawW > 0 && (
        <svg width={width} height={height} role="img" aria-label={ariaLabel}>
          <text x={x(0) - 8} y={14} textAnchor="end" className="chart-label" fill="rgb(var(--teal-ink))">
            ← {betterLabel}
          </text>
          <text x={x(0) + 8} y={14} className="chart-label" fill="rgb(var(--coral-ink))">
            {worseLabel} →
          </text>
          {x.ticks(5).map((v) => (
            <text key={v} x={x(v)} y={height - 8} textAnchor="middle" className="chart-label" fill="rgb(var(--ink-3))">
              {format(v)}
            </text>
          ))}
          <line x1={x(0)} x2={x(0)} y1={m.top - 4} y2={height - m.bottom + 4} stroke="rgb(var(--ink-3))" strokeDasharray="4 4" />
          {items.map((it, i) => {
            const cy = m.top + i * rowH + rowH / 2 + 6;
            const crosses = it.lo <= 0 && it.hi >= 0;
            const col = crosses ? "rgb(var(--ink-2))" : it.mean < 0 ? "rgb(var(--teal-ink))" : "rgb(var(--coral-ink))";
            return (
              <g key={it.key}>
                <text x={m.left} y={cy - 16} className="chart-label" fontWeight={600} fill="rgb(var(--ink))">
                  {it.label}
                  {it.sub && (
                    <tspan fill="rgb(var(--ink-3))" fontWeight={400}>
                      {"  "}
                      {it.sub}
                    </tspan>
                  )}
                </text>
                <motion.line
                  y1={cy}
                  y2={cy}
                  initial={reduce ? false : { x1: x(it.mean), x2: x(it.mean) }}
                  animate={{ x1: x(it.lo), x2: x(it.hi) }}
                  transition={{ duration: 0.7 }}
                  stroke={col}
                  strokeWidth={2}
                  strokeLinecap="round"
                />
                <circle cx={x(it.mean)} cy={cy} r={6} fill={col} stroke="rgb(var(--card))" strokeWidth={2}>
                  <title>{`${it.label}: ${format(it.mean)} (95% ${format(it.lo)} to ${format(it.hi)})`}</title>
                </circle>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

const ZONE_FILL: Record<string, string> = {
  A: "rgb(var(--teal))",
  B: "color-mix(in oklab, rgb(var(--teal)) 45%, rgb(var(--card)))",
  C: "rgb(var(--marigold))",
  D: "rgb(var(--coral))",
  E: "rgb(var(--coral-ink))",
};

/** One stacked 100% bar per row (error-grid zones A..E), with A+B summarised at the end. */
export function ZoneStack({ rows, ariaLabel, zoneLabel }: { rows: { key: string; label: string; zones: Record<string, number> }[]; ariaLabel: string; zoneLabel: (z: string) => string }) {
  const reduce = useReducedMotion();
  const zones = ["A", "B", "C", "D", "E"];
  return (
    <div aria-label={ariaLabel} role="group">
      <ul className="space-y-3">
        {rows.map((r) => {
          const ab = (r.zones.A ?? 0) + (r.zones.B ?? 0);
          return (
            <li key={r.key} className="grid grid-cols-[6.5rem_1fr_3.6rem] items-center gap-3 text-sm sm:grid-cols-[8rem_1fr_4rem]">
              <span className="font-medium leading-tight text-ink-2">{r.label}</span>
              <span className="flex h-4 overflow-hidden rounded-full bg-paper-2">
                {zones.map((z) =>
                  (r.zones[z] ?? 0) > 0 ? (
                    <motion.span
                      key={z}
                      className="block h-full border-r-2 border-card last:border-r-0"
                      style={{ background: ZONE_FILL[z] }}
                      initial={reduce ? false : { width: 0 }}
                      animate={{ width: `${r.zones[z]}%` }}
                      transition={{ duration: 0.8 }}
                      title={`${zoneLabel(z)}: ${fixed((r.zones[z] ?? 0), 1)}%`}
                    />
                  ) : null,
                )}
              </span>
              <span className="num text-right font-semibold" title="A+B">
                {fixed(ab, 1)}%
              </span>
            </li>
          );
        })}
      </ul>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        {zones.map((z) => (
          <li key={z} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: ZONE_FILL[z] }} aria-hidden />
            {zoneLabel(z)}
          </li>
        ))}
      </ul>
    </div>
  );
}
