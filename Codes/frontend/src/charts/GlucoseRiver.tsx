import { useId, useMemo, useState, type KeyboardEvent } from "react";
import * as d3 from "./d3";
import { AnimatePresence, m as motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import type { Band, Forecast, TwinState } from "@/api/types";
import { useSize } from "@/hooks/useSize";
import { formatClock, formatHour, parseTime, mealName } from "@/lib/format";
import { intervalKeys, kindAtTime } from "@/lib/intervals";
import { EASE, bandPath, linePath, nearestIndex, splitAt, toPoints, validatedHorizon, type QPoint } from "./util";

export interface RippleEvent {
  key: number;
  t: string;
  value: number;
  before: Band;
  after: Band;
}

/** Two possible futures branching from the same past: the baseline and one changed scenario. */
export interface Futures {
  baseline: Forecast;
  scenario?: Forecast | null;
  baselineLabel: string;
  scenarioLabel?: string;
}

interface Props {
  state: TwinState;
  rangeHours?: number;
  /** A meal forecast drawn as the twin curve; the no-meal forecast becomes a dashed "without". */
  overlay?: Forecast | null;
  /** Baseline + scenario (both bands visible, labelled directly). Takes precedence over overlay. */
  futures?: Futures | null;
  /** The previous forecast, kept as a faint ghost while the revised one animates in. */
  ghost?: Forecast | null;
  /** A revealed dataset reference value (hidden from the twin until revealed). */
  reference?: { t: string; value: number } | null;
  highlight?: { from?: string; to?: string } | null;
  ripple?: RippleEvent | null;
  compact?: boolean;
  /** Dim the forecast while a refetch is running. */
  pending?: boolean;
  label?: string;
  /** Height override in px. */
  height?: number;
}

const M = { top: 24, right: 14, bottom: 28, left: 38 };

/**
 * The "glucose river": past readings as dots, the virtual-CGM reconstruction with its band, the
 * next hours as curves inside their bands (two futures when a scenario is given), the 70–180
 * lane and a replay-now marker. Points beyond the validated horizon are dashed: exploratory.
 */
export function GlucoseRiver({ state, rangeHours = 12, overlay, futures, ghost, reference, highlight, ripple, compact, pending, label, height: hOverride }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const reduce = useReducedMotion();
  const uid = useId().replace(/:/g, "");
  const [wrapRef, { width: rawW }] = useSize<HTMLDivElement>();
  const width = Math.max(280, rawW || 0);
  const height = hOverride ?? (compact ? 210 : width < 640 ? 268 : 360);
  const innerW = width - M.left - M.right;
  const innerH = height - M.top - M.bottom;

  const now = parseTime(state.now).getTime();
  const past = useMemo(() => toPoints(state.history.virtual_cgm), [state.history.virtual_cgm]);
  // Primary future (marigold) and an optional secondary (baseline when a scenario is shown).
  const primaryFc: Forecast | null = futures ? (futures.scenario ?? futures.baseline) : (overlay ?? state.forecast ?? null);
  const secondaryFc: Forecast | null = futures ? (futures.scenario ? futures.baseline : null) : overlay ? state.forecast : null;
  const prim = useMemo(() => toPoints(primaryFc?.traj), [primaryFc?.traj]);
  const sec = useMemo(() => toPoints(secondaryFc?.traj), [secondaryFc?.traj]);
  const gh = useMemo(() => toPoints(ghost?.traj), [ghost?.traj]);
  const twoFutures = !!futures?.scenario;

  const readings = useMemo(
    () =>
      (state.history.readings ?? [])
        .map((r) => ({ ...r, ts: parseTime(r.t).getTime() }))
        .filter((r) => Number.isFinite(r.ts) && Number.isFinite(r.value)),
    [state.history.readings],
  );
  const meals = useMemo(
    () => (state.history.meals ?? []).map((m) => ({ ...m, ts: parseTime(m.t).getTime() })).filter((m) => Number.isFinite(m.ts)),
    [state.history.meals],
  );
  const steps = useMemo(() => {
    const s = state.history.steps;
    if (!s?.t) return [];
    return s.t.map((tt, i) => ({ ts: parseTime(tt).getTime(), v: s.v?.[i] ?? 0 })).filter((d) => Number.isFinite(d.ts));
  }, [state.history.steps]);

  const lastT = Math.max(now + 4 * 3600_000, prim.length ? prim[prim.length - 1].t : now, sec.length ? sec[sec.length - 1].t : now);
  const x = useMemo(() => d3.scaleTime().domain([now - rangeHours * 3600_000, lastT]).range([0, innerW]), [now, rangeHours, lastT, innerW]);
  const yMax = useMemo(() => {
    const vis = (p: QPoint) => p.t >= now - rangeHours * 3600_000;
    const highs = [...past.filter(vis).map((p) => p.q95), ...prim.map((p) => p.q95), ...sec.map((p) => p.q95), ...gh.map((p) => p.q95), ...readings.map((r) => r.value), reference?.value ?? 0];
    return Math.min(420, Math.max(260, (d3.max(highs) ?? 240) + 15));
  }, [past, prim, sec, gh, readings, reference, now, rangeHours]);
  const y = useMemo(() => d3.scaleLinear().domain([40, yMax]).range([innerH, 0]).clamp(true), [yMax, innerH]);

  // 250–450 ms: a meaningful state transition, never a slow morph (reduced motion: none).
  const tr = reduce ? { duration: 0 } : { duration: 0.4, ease: EASE };

  // Validated vs exploratory split of each future.
  const vhMs = (f: Forecast | null) => validatedHorizon(f) * 60_000 + (f ? parseTime(f.origin).getTime() : now);
  const primSplit = splitAt(prim, vhMs(primaryFc));
  const secSplit = splitAt(sec, vhMs(secondaryFc));
  const vhX = x(vhMs(primaryFc));

  const pastBand = bandPath(past, x, y, "q05", "q95");
  const pastLine = linePath(past, x, y);

  const tickEvery = rangeHours <= 6 ? 1 : rangeHours <= 12 ? 2 : 6;
  const xTicks = x.ticks(d3.timeHour.every(tickEvery)!);
  const stepMax = d3.max(steps, (d) => d.v) || 1;

  // ----- hover / pin / keyboard -----
  const series = useMemo(() => [...past, ...prim].sort((a, b) => a.t - b.t), [past, prim]);
  const [hover, setHover] = useState<number | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);
  const idxAt = (e: React.PointerEvent<SVGRectElement>) => {
    const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
    return nearestIndex(series, x.invert(e.clientX - rect.left).getTime());
  };
  const shown = hover ?? pinned;
  const hp = shown !== null && shown >= 0 && shown < series.length ? series[shown] : null;
  const nearReading = hp ? readings.find((r) => Math.abs(r.ts - hp.t) < 8 * 60_000 && r.kind !== "cgm") : null;
  const secAtHover = hp && sec.length ? sec[nearestIndex(sec, hp.t)] : null;
  const exploratoryAt = (p: QPoint) => p.t > vhMs(primaryFc);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!series.length) return;
    const step = Math.max(1, Math.round(15 / 5)); // 15 minutes on a 5-minute grid
    const cur = pinned ?? nearestIndex(series, now);
    let next: number | null = cur;
    if (e.key === "ArrowRight") next = Math.min(series.length - 1, cur + step);
    else if (e.key === "ArrowLeft") next = Math.max(0, cur - step);
    else if (e.key === "Home") next = nearestIndex(series, now - rangeHours * 3600_000);
    else if (e.key === "End") next = series.length - 1;
    else if (e.key === "Escape") next = null;
    else return;
    e.preventDefault();
    setPinned(next);
  };

  const visibleFingerpricks = readings.filter((r) => r.kind !== "cgm" && r.ts >= now - rangeHours * 3600_000);
  const showValueLabels = visibleFingerpricks.length <= 10;

  const hlFrom = highlight?.from ? parseTime(highlight.from).getTime() : null;
  const hlTo = highlight?.to ? parseTime(highlight.to).getTime() : null;
  const hasHl = highlight && (hlFrom !== null || hlTo !== null);
  const hlX0 = hasHl ? x(hlFrom ?? hlTo! - 30 * 60_000) : 0;
  const hlX1 = hasHl ? x(hlTo ?? hlFrom! + 30 * 60_000) : 0;

  const nowX = x(now);
  const estY = y(state.estimate);
  const nowText = formatClock(state.now, lang);
  const nowW = Math.max(44, nowText.length * 6.6 + 16);

  // Direct labels at the right end of each future, nudged apart when they collide.
  const endLabels = (() => {
    if (compact) return [];
    const out: { key: string; text: string; y: number; tone: "prim" | "sec" }[] = [];
    const end = (pts: QPoint[]) => (pts.length ? pts[pts.length - 1] : null);
    const pe = end(prim);
    const se = end(sec);
    const primText = futures ? (futures.scenario ? (futures.scenarioLabel ?? "") : futures.baselineLabel) : overlay ? t("meal.withMeal") : t("stage.forecast");
    const secText = futures ? futures.baselineLabel : overlay ? t("meal.without") : "";
    if (pe && primText) out.push({ key: "p", text: primText, y: y(pe.q50), tone: "prim" });
    if (se && secText) out.push({ key: "s", text: secText, y: y(se.q50), tone: "sec" });
    if (out.length === 2 && Math.abs(out[0].y - out[1].y) < 16) {
      const [a, b] = out[0].y <= out[1].y ? [out[0], out[1]] : [out[1], out[0]];
      const mid = (a.y + b.y) / 2;
      a.y = mid - 9;
      b.y = mid + 9;
    }
    return out.map((l) => ({ ...l, y: Math.max(10, Math.min(innerH - 22, l.y - 10)) }));
  })();

  const announce = hp
    ? `${formatClock(new Date(hp.t), lang)}, ${hp.t > now ? t("stage.forecast") : t("stage.median")}: ${Math.round(hp.q50)} ${t("common.mgdl")}, ${t(intervalKeys(kindAtTime(hp.t, now)).short, { lo: Math.round(hp.q05), hi: Math.round(hp.q95) })}${hp.t > now && exploratoryAt(hp) ? `, ${t("evidence.status.exploratory")}` : ""}`
    : "";

  return (
    <div
      ref={wrapRef}
      className="relative w-full select-none rounded-2xl"
      style={{ height }}
      tabIndex={0}
      role="group"
      aria-label={`${label ?? t("a11y.riverChart")}. ${t("a11y.chartKeys")}`}
      onKeyDown={onKey}
      onBlur={() => setHover(null)}
    >
      {rawW > 0 && (
        <svg width={width} height={height} role="img" aria-label={label ?? t("a11y.riverChart")} className="block">
          <desc>{`${t("stage.estimate")}: ${Math.round(state.estimate)} ${t("common.mgdl")}, ${t("interval.calibratedNow.short", { lo: Math.round(state.band.lo), hi: Math.round(state.band.hi) })}.`}</desc>
          <defs>
            <clipPath id={`plot-${uid}`}>
              <rect x={0} y={-4} width={innerW} height={innerH + 8} />
            </clipPath>
            <linearGradient id={`fcfade-${uid}`} x1="0" x2="1">
              <stop offset="0" stopColor="rgb(var(--marigold))" stopOpacity="0.34" />
              <stop offset="1" stopColor="rgb(var(--marigold))" stopOpacity="0.14" />
            </linearGradient>
            <pattern id={`hatch-${uid}`} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="7" stroke="rgb(var(--moon))" strokeOpacity="0.09" strokeWidth="3" />
            </pattern>
            <filter id={`glow-${uid}`} x="-20%" y="-50%" width="140%" height="200%">
              <feGaussianBlur stdDeviation="5" />
            </filter>
          </defs>
          <g transform={`translate(${M.left},${M.top})`}>
            {/* target lane */}
            <rect x={0} width={innerW} y={y(180)} height={Math.max(0, y(70) - y(180))} fill="rgb(var(--teal))" opacity={0.1} />
            {[70, 180].map((v) => (
              <g key={v}>
                <line x1={0} x2={innerW} y1={y(v)} y2={y(v)} stroke="rgb(var(--teal))" strokeOpacity={0.45} strokeDasharray="2 5" />
                <text x={-8} y={y(v)} dy="0.32em" textAnchor="end" className="chart-label" fill="rgb(var(--teal))">
                  {v}
                </text>
              </g>
            ))}
            {[250, 350].filter((v) => v < yMax).map((v) => (
              <g key={v}>
                <line x1={0} x2={innerW} y1={y(v)} y2={y(v)} stroke="rgb(var(--moon))" strokeOpacity={0.05} />
                <text x={-8} y={y(v)} dy="0.32em" textAnchor="end" className="chart-label" fill="rgb(var(--moon-3))">
                  {v}
                </text>
              </g>
            ))}
            <text x={-30} y={-10} className="chart-label" fill="rgb(var(--moon-3))">
              {t("common.mgdl")}
            </text>
            {!compact && (
              <text x={6} y={y(180) + 13} className="chart-label" fill="rgb(var(--teal))" opacity={0.85}>
                {t("stage.target")}
              </text>
            )}

            {/* x axis */}
            {xTicks.map((d) => (
              <g key={+d} transform={`translate(${x(d)},0)`}>
                <line y1={0} y2={innerH} stroke="rgb(var(--moon))" strokeOpacity={0.05} />
                <text y={innerH + 18} textAnchor="middle" className="chart-label" fill="rgb(var(--moon-3))">
                  {formatHour(d, lang)}
                </text>
              </g>
            ))}

            {/* exploratory region beyond the validated horizon */}
            {primaryFc && vhX < innerW && (
              <g>
                <rect x={vhX} y={0} width={Math.max(0, innerW - vhX)} height={innerH} fill={`url(#hatch-${uid})`} />
                <line x1={vhX} x2={vhX} y1={0} y2={innerH} stroke="rgb(var(--moon))" strokeOpacity={0.25} strokeDasharray="1 4" />
                {!compact && innerW - vhX > 40 && (
                  <text x={innerW - 4} y={11} textAnchor="end" className="chart-label" fill="rgb(var(--moon-3))">
                    {innerW - vhX > 150 ? t("stage.exploratory") : t("evidence.status.exploratory")}
                  </text>
                )}
              </g>
            )}

            <g clipPath={`url(#plot-${uid})`}>
              {/* steps as a faint floor */}
              {steps.map((s) => {
                const h = (s.v / stepMax) * 14;
                return <rect key={s.ts} x={x(s.ts)} width={Math.max(1, x(s.ts + 3600_000) - x(s.ts) - 1.5)} y={innerH - h} height={h} fill="rgb(var(--moon))" opacity={0.05} />;
              })}

              {/* highlight from the voice answer */}
              <AnimatePresence>
                {hasHl && (
                  <motion.rect
                    key={`${hlFrom}-${hlTo}`}
                    x={Math.min(hlX0, hlX1)}
                    width={Math.max(8, Math.abs(hlX1 - hlX0))}
                    y={0}
                    height={innerH}
                    rx={10}
                    fill="rgb(var(--marigold))"
                    stroke="rgb(var(--marigold))"
                    strokeOpacity={0.6}
                    strokeDasharray="4 4"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: [0, 0.4, 0.24] }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: reduce ? 0 : 1.2 }}
                    style={{ fillOpacity: 0.5 }}
                  />
                )}
              </AnimatePresence>

              {/* virtual CGM reconstruction */}
              <motion.path initial={false} animate={{ d: pastBand }} transition={tr} fill="rgb(var(--violet))" opacity={0.16} />
              <motion.path initial={false} animate={{ d: pastLine }} transition={tr} fill="none" stroke="rgb(var(--moon))" strokeOpacity={0.6} strokeWidth={1.6} />

              {/* ghost of the previous forecast (Watch the twin learn) */}
              {gh.length > 0 && (
                <g aria-hidden>
                  <path d={bandPath(gh, x, y, "q05", "q95")} fill="none" stroke="rgb(var(--moon-2))" strokeOpacity={0.45} strokeWidth={1} strokeDasharray="2 3" />
                  <path d={linePath(gh, x, y)} fill="none" stroke="rgb(var(--moon-2))" strokeOpacity={0.6} strokeWidth={1.6} strokeDasharray="3 4" />
                </g>
              )}

              {/* futures */}
              <g className={pending ? "opacity-50 transition-opacity" : "transition-opacity"}>
                {sec.length > 0 && (
                  <g>
                    {twoFutures && (
                      <motion.path initial={false} animate={{ d: bandPath(sec, x, y, "q05", "q95") }} transition={tr} fill="rgb(var(--moon))" fillOpacity={0.1} stroke="rgb(var(--moon))" strokeOpacity={0.35} strokeWidth={1} strokeDasharray="3 4" />
                    )}
                    <motion.path initial={false} animate={{ d: linePath(secSplit.head, x, y) }} transition={tr} fill="none" stroke="rgb(var(--moon))" strokeOpacity={0.8} strokeWidth={2} strokeDasharray="6 5" />
                    <motion.path initial={false} animate={{ d: linePath(secSplit.tail, x, y) }} transition={tr} fill="none" stroke="rgb(var(--moon))" strokeOpacity={0.45} strokeWidth={1.6} strokeDasharray="2 5" />
                  </g>
                )}
                <g className="breathe">
                  <motion.path initial={false} animate={{ d: bandPath(prim, x, y, "q05", "q95") }} transition={tr} fill={`url(#fcfade-${uid})`} />
                </g>
                <motion.path initial={false} animate={{ d: bandPath(prim, x, y, "q25", "q75") }} transition={tr} fill="rgb(var(--marigold))" opacity={0.18} />
                <motion.path initial={false} animate={{ d: linePath(primSplit.head, x, y) }} transition={tr} fill="none" stroke="rgb(var(--marigold))" strokeWidth={7} opacity={0.3} filter={`url(#glow-${uid})`} />
                <motion.path initial={false} animate={{ d: linePath(primSplit.head, x, y) }} transition={tr} fill="none" stroke="rgb(var(--marigold))" strokeWidth={2.8} strokeLinecap="round" />
                <motion.path initial={false} animate={{ d: linePath(primSplit.tail, x, y) }} transition={tr} fill="none" stroke="rgb(var(--marigold))" strokeOpacity={0.75} strokeWidth={2.2} strokeDasharray="5 5" strokeLinecap="round" />
              </g>

              {/* readings */}
              {readings
                .filter((r) => r.kind === "cgm")
                .map((r) => (
                  <circle key={`${r.t}-${r.value}`} cx={x(r.ts)} cy={y(r.value)} r={1.5} fill="rgb(var(--moon))" opacity={0.55} />
                ))}
              {readings
                .filter((r) => r.kind !== "cgm")
                .map((r, i, arr) => (
                  <g key={`${r.t}-${r.kind}-${i}`} transform={`translate(${x(r.ts)},${y(r.value)})`}>
                    {r.kind === "lab" ? (
                      <rect x={-5} y={-5} width={10} height={10} transform="rotate(45)" fill="rgb(var(--night))" stroke="rgb(var(--violet-night))" strokeWidth={2.2} />
                    ) : (
                      <>
                        <circle r={9} fill="rgb(var(--marigold))" opacity={0.16} />
                        <circle r={5.2} fill="rgb(var(--night))" stroke="rgb(var(--moon))" strokeWidth={2.4} />
                      </>
                    )}
                    {showValueLabels && !compact && (i === arr.length - 1 || Math.abs(x(arr[i + 1].ts) - x(r.ts)) > 16) && (
                      <text y={-13} textAnchor="middle" className="chart-label" fontWeight={700} fill="rgb(var(--moon))">
                        {Math.round(r.value)}
                      </text>
                    )}
                  </g>
                ))}

              {/* meals along the floor */}
              {meals.map((m, i) => (
                <g key={`${m.t}-${i}`} transform={`translate(${x(m.ts)},${innerH - 9})`}>
                  <title>{`${mealName(t, m.name)} · ${t("stage.carbsG", { n: Math.round(m.carbs) })}`}</title>
                  <circle r={8} fill="rgb(var(--night-3))" stroke="rgb(var(--marigold))" strokeOpacity={0.7} strokeWidth={1.4} />
                  <path d="M-2.6 -4v3.2a1.6 1.6 0 0 0 1.6 1.6h0.2M-1.3 -4v8M2.8 -4c-1 .8-1.5 2.2-1.5 3.6V1.2h1.5V4" fill="none" stroke="rgb(var(--marigold))" strokeWidth={1.1} strokeLinecap="round" />
                </g>
              ))}

              {/* assimilation ripple + band change at the reading */}
              <AnimatePresence>
                {ripple && (
                  <motion.g key={ripple.key} initial={{ opacity: 1 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    {[0, 0.25, 0.5].map((delay) => (
                      <motion.circle
                        key={delay}
                        cx={x(parseTime(ripple.t).getTime())}
                        cy={y(ripple.value)}
                        fill="none"
                        stroke="rgb(var(--marigold))"
                        strokeWidth={2}
                        initial={{ r: 4, opacity: 0.9 }}
                        animate={{ r: reduce ? 4 : 60, opacity: 0 }}
                        transition={{ duration: reduce ? 0 : 1.2, delay: reduce ? 0 : delay, ease: "easeOut" }}
                      />
                    ))}
                    <motion.rect
                      x={x(parseTime(ripple.t).getTime()) - 7}
                      width={14}
                      rx={7}
                      fill="rgb(var(--marigold))"
                      fillOpacity={0.14}
                      stroke="rgb(var(--marigold))"
                      strokeWidth={1.6}
                      initial={{ y: y(ripple.before.hi), height: Math.max(14, y(ripple.before.lo) - y(ripple.before.hi)) }}
                      animate={{ y: y(ripple.after.hi), height: Math.max(14, y(ripple.after.lo) - y(ripple.after.hi)), opacity: [1, 1, 0] }}
                      transition={{ duration: reduce ? 0 : 1.8, ease: EASE, times: [0, 0.6, 1] }}
                    />
                  </motion.g>
                )}
              </AnimatePresence>
            </g>

            {/* revealed dataset reference value */}
            {reference && Number.isFinite(reference.value) && (
              <g transform={`translate(${x(parseTime(reference.t).getTime())},${y(reference.value)})`}>
              <motion.g initial={reduce ? false : { opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: reduce ? 0 : 0.35 }}>
                <rect x={-7} y={-7} width={14} height={14} transform="rotate(45)" fill="none" stroke="rgb(var(--teal))" strokeWidth={2.4} strokeDasharray="3 2" />
                <circle r={2.4} fill="rgb(var(--teal))" />
                {!compact && (
                  <text x={10} y={-10} className="chart-label" fontWeight={700} fill="rgb(var(--teal))" paintOrder="stroke" stroke="rgb(var(--night))" strokeWidth={4} strokeLinejoin="round">
                    {t("learn.refShort", { v: Math.round(reference.value) })}
                  </text>
                )}
              </motion.g>
              </g>
            )}

            {/* direct labels on the futures */}
            {endLabels.map((l) => (
              <text
                key={l.key}
                x={innerW - 4}
                y={l.y}
                textAnchor="end"
                className="chart-label chart-label-strong"
                fontWeight={700}
                fill={l.tone === "prim" ? "rgb(var(--marigold))" : "rgb(var(--moon))"}
                paintOrder="stroke"
                stroke="rgb(var(--night))"
                strokeWidth={4}
                strokeLinejoin="round"
              >
                {l.text}
              </text>
            ))}

            {/* replay-now marker */}
            <line x1={nowX} x2={nowX} y1={-6} y2={innerH} stroke="rgb(var(--moon))" strokeOpacity={0.45} strokeDasharray="3 4" />
            <g transform={`translate(${nowX},${-13})`}>
              <rect x={-nowW / 2} y={-9} width={nowW} height={18} rx={9} fill="rgb(var(--moon))" />
              <text textAnchor="middle" dy="0.34em" className="chart-label" fontWeight={700} fill="rgb(var(--night))">
                {nowText}
              </text>
            </g>
            <motion.g initial={false} animate={{ y: estY }} transition={tr}>
              <circle cx={nowX} r={6} fill="rgb(var(--marigold))" className="origin-center animate-pulseRing" style={{ transformBox: "fill-box" }} />
              <circle cx={nowX} r={6} fill="rgb(var(--marigold))" stroke="rgb(var(--night))" strokeWidth={2} />
            </motion.g>

            {/* hover / pinned guide */}
            {hp && (
              <g pointerEvents="none">
                <line x1={x(hp.t)} x2={x(hp.t)} y1={0} y2={innerH} stroke="rgb(var(--moon))" strokeOpacity={pinned !== null && hover === null ? 0.8 : 0.5} strokeDasharray={pinned !== null && hover === null ? "4 3" : undefined} />
                <circle cx={x(hp.t)} cy={y(hp.q50)} r={4.5} fill={hp.t > now ? "rgb(var(--marigold))" : "rgb(var(--moon))"} stroke="rgb(var(--night))" strokeWidth={2} />
                {secAtHover && hp.t > now && <circle cx={x(secAtHover.t)} cy={y(secAtHover.q50)} r={4} fill="rgb(var(--night))" stroke="rgb(var(--moon))" strokeWidth={2} />}
              </g>
            )}
            <rect
              width={innerW}
              height={innerH}
              fill="transparent"
              onPointerMove={(e) => setHover(idxAt(e))}
              onPointerDown={(e) => {
                const i = idxAt(e);
                setPinned((p) => (p === i ? null : i));
              }}
              onPointerLeave={() => setHover(null)}
              style={{ touchAction: "pan-y" }}
            />
          </g>
        </svg>
      )}

      {hp && (
        <div
          className="pointer-events-none absolute z-10 w-48 rounded-2xl border border-night-line bg-night-2/95 px-3 py-2 text-xs text-moon shadow-lift backdrop-blur"
          style={{ left: Math.min(Math.max(M.left + x(hp.t) - 96, 4), width - 196), top: 6 }}
        >
          <div className="flex items-center justify-between gap-2 text-moon-2">
            <span className="num">{formatClock(new Date(hp.t), lang)}</span>
            <span className={hp.t > now ? "text-marigold" : ""}>{hp.t > now ? (exploratoryAt(hp) ? t("evidence.status.exploratory") : t("stage.forecast")) : ""}</span>
          </div>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="num text-lg font-bold">{Math.round(hp.q50)}</span>
            <span className="text-moon-2">{t("common.mgdl")}</span>
          </div>
          <div className="text-moon-2" data-interval={kindAtTime(hp.t, now)}>
            {t(intervalKeys(kindAtTime(hp.t, now)).short, { lo: Math.round(hp.q05), hi: Math.round(hp.q95) })}
          </div>
          {secAtHover && hp.t > now && (
            <div className="mt-1 border-t border-night-line pt-1 text-moon-2">
              {futures?.baselineLabel ?? t("meal.without")}: <span className="num font-semibold text-moon">{Math.round(secAtHover.q50)}</span>
            </div>
          )}
          {nearReading && (
            <div className="mt-1 border-t border-night-line pt-1 text-moon">
              {t(nearReading.kind === "lab" ? "stage.lab" : "stage.fingerprick")}: <span className="num font-semibold">{Math.round(nearReading.value)}</span>
            </div>
          )}
        </div>
      )}
      <p className="sr-only" aria-live="polite">
        {pinned !== null ? announce : ""}
      </p>
    </div>
  );
}
