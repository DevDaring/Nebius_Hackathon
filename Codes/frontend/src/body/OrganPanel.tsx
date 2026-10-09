import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { m as motion } from "framer-motion";
import { X } from "lucide-react";
import type { BodyView, OrganKey } from "@/api/types";
import { EvidenceChip } from "@/components/evidence";
import { formatClock } from "@/lib/format";
import { formatOrganValue, lastValidatedIndex, liverDirection, type BodyPart } from "@/lib/body";
import { UNIT_KEY, partColor, partStats } from "./meta";
import { bodyBloodBand, intervalKeys } from "@/lib/intervals";

interface Series {
  lo: number[];
  mid: number[];
  hi: number[];
}
function seriesOf(view: BodyView, part: BodyPart, scenario: boolean): Series | null {
  const v = scenario ? view.scenario : view.baseline;
  if (!v) return null;
  if (part === "blood") return { lo: v.blood.q05, mid: v.blood.q50, hi: v.blood.q95 };
  const s = v.fluxes[part as OrganKey];
  return s ? { lo: s.q10, mid: s.q50, hi: s.q90 } : null;
}

/** Sparkline of the q50 with its band over the 4 h, the scenario overlay and the selected time. */
export function Sparkline({ view, part, idx, showScenario, label }: { view: BodyView; part: BodyPart; idx: number; showScenario: boolean; label: string }) {
  const { t } = useTranslation();
  const pid = useId().replace(/:/g, "");
  const base = seriesOf(view, part, false);
  const scen = view.scenario ? seriesOf(view, part, true) : null;
  if (!base) return null;
  const W = 300;
  const H = 112;
  const padL = 30;
  const padR = 6;
  const padT = 8;
  const padB = 18;
  const n = base.mid.length - 1;
  const all = [...base.lo, ...base.hi, ...(scen ? [...scen.lo, ...scen.hi] : [])].filter(Number.isFinite);
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (part !== "blood") lo = Math.min(lo, 0);
  if (hi - lo < 1e-6) hi = lo + 1;
  const pad = (hi - lo) * 0.08;
  lo -= part === "blood" ? pad : 0;
  hi += pad;
  const x = (i: number) => padL + (i / n) * (W - padL - padR);
  const y = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  const line = (a: number[]) => a.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const area = (s: Series) => `${line(s.hi)}${s.lo.map((v, i) => [i, v] as const).reverse().map(([i, v]) => `L${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("")}Z`;
  const xv = x(lastValidatedIndex(view.validated_horizon_min, n));
  const fmt = (v: number) => (part === "blood" ? String(Math.round(v)) : formatOrganValue(part as OrganKey, v));
  const accent = part === "blood" ? "rgb(var(--teal-ink))" : "rgb(var(--violet-ink))";
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={label}>
        <defs>
          <pattern id={`hatch-${pid}`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" stroke="rgb(var(--ink-3))" strokeOpacity="0.18" strokeWidth="2" />
          </pattern>
        </defs>
        <rect x={xv} y={padT} width={W - padR - xv} height={H - padT - padB} fill={`url(#hatch-${pid})`} />
        {part !== "blood" && lo < 0 && hi > 0 && <line x1={padL} x2={W - padR} y1={y(0)} y2={y(0)} stroke="rgb(var(--ink-3))" strokeOpacity="0.5" strokeDasharray="2 3" />}
        {part === "blood" && (
          <>
            {[70, 180].filter((g) => g > lo && g < hi).map((g) => (
              <line key={g} x1={padL} x2={W - padR} y1={y(g)} y2={y(g)} stroke="rgb(var(--ink-3))" strokeOpacity="0.45" strokeDasharray="3 3" />
            ))}
          </>
        )}
        <path d={area(base)} fill={accent} fillOpacity={0.16} />
        <path d={line(base.mid)} fill="none" stroke={accent} strokeWidth={2} strokeLinejoin="round" opacity={scen && showScenario ? 0.6 : 1} strokeDasharray={scen && showScenario ? "4 3" : undefined} />
        {scen && (
          <path d={line(scen.mid)} fill="none" stroke="rgb(var(--marigold-ink))" strokeWidth={2.2} strokeLinejoin="round" opacity={showScenario ? 1 : 0.55} strokeDasharray={showScenario ? undefined : "4 3"} />
        )}
        <line x1={x(idx)} x2={x(idx)} y1={padT} y2={H - padB} stroke="rgb(var(--ink))" strokeOpacity="0.55" strokeWidth={1.2} />
        <circle cx={x(idx)} cy={y((showScenario && scen ? scen : base).mid[idx])} r={3.4} fill="rgb(var(--ink))" />
        <text x={padL - 4} y={padT + 8} textAnchor="end" className="chart-label" fill="rgb(var(--ink-3))" fontSize="9">
          {fmt(hi)}
        </text>
        <text x={padL - 4} y={H - padB} textAnchor="end" className="chart-label" fill="rgb(var(--ink-3))" fontSize="9">
          {fmt(lo)}
        </text>
        {[0, 12, 24, 36, 48].map((i) => (
          <text key={i} x={x(i)} y={H - 4} textAnchor={i === 0 ? "start" : i === 48 ? "end" : "middle"} className="chart-label" fill="rgb(var(--ink-3))" fontSize="9">
            {i === 0 ? t("body.time.now") : t("body.time.plusH", { n: i / 12 })}
          </text>
        ))}
      </svg>
    </figure>
  );
}

/** Organ details: side panel on wide screens, bottom sheet on phones. */
export function OrganPanel({
  view,
  part,
  idx,
  showScenario,
  scenarioLabel,
  compact,
  onClose,
}: {
  view: BodyView;
  part: BodyPart;
  idx: number;
  showScenario: boolean;
  scenarioLabel: string | null;
  compact: boolean;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const closeRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    closeRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (prev && document.body.contains(prev)) prev.focus({ preventScroll: true });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const v = showScenario && view.scenario ? view.scenario : view.baseline;
  const st = partStats(v, part, idx);
  const name = t(`body.part.${part}.name`);
  const unit = t(UNIT_KEY[part]);
  const fmt = (x: number) => (part === "blood" ? String(Math.round(x)) : formatOrganValue(part as OrganKey, x));
  const time = formatClock(view.t[idx] ?? view.t[0], i18n.language);
  const dir = part === "liver" ? liverDirection(st.q50) : null;

  const body = (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id={titleId} className="flex items-center gap-2 text-lg font-bold leading-tight text-ink">
            <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: partColor(part, st.q50) }} aria-hidden />
            {name}
          </h3>
          <p className="num mt-0.5 text-xs text-ink-3">{t("body.panel.now", { time })}</p>
        </div>
        <button ref={closeRef} type="button" onClick={onClose} className="rounded-full p-2 text-ink-2 hover:bg-paper-2" aria-label={t("common.close")}>
          <X size={18} aria-hidden />
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {part === "blood" ? (
          <EvidenceChip status="validated" label={t("body.panel.validated2h")} />
        ) : (
          <EvidenceChip status="simulated" label={t("body.panel.simulatedBy")} />
        )}
        {showScenario && scenarioLabel && <span className="rounded-full border border-marigold-ink/40 bg-marigold/10 px-2 py-0.5 text-[0.7rem] font-semibold text-marigold-ink">{scenarioLabel}</span>}
      </div>
      <p className="flex flex-wrap items-baseline gap-x-1.5">
        <span className="num text-3xl font-extrabold tracking-tight text-ink">{fmt(st.q50)}</span>
        <span className="text-sm text-ink-2">{unit}</span>
      </p>
      {dir && <p className="-mt-2 text-sm font-semibold text-ink-2">{t(`body.panel.${dir}`)}</p>}
      <p className="num -mt-1 text-xs text-ink-2">
        {part === "blood" ? `${t(intervalKeys(bodyBloodBand(view, idx, st.lo, st.hi).kind).short, { lo: fmt(st.lo), hi: fmt(st.hi) })} ${t("common.mgdl")}` : t("body.panel.range", { lo: fmt(st.lo), hi: fmt(st.hi) })}
      </p>
      <p className="text-sm leading-relaxed text-ink-2">{t(`body.part.${part}.desc`)}</p>
      <div>
        <p className="eyebrow mb-1 text-ink-3">{t("body.panel.spark")}</p>
        <Sparkline view={view} part={part} idx={idx} showScenario={showScenario} label={t("body.panel.sparkLabel", { organ: name })} />
        <p className="mt-1 text-[0.7rem] text-ink-3">{t("body.time.exploratory")}</p>
      </div>
      <p className="border-t border-line pt-2 text-[0.7rem] leading-snug text-ink-3">{t("body.honesty")}</p>
    </div>
  );

  if (compact) {
    return (
      <div className="fixed inset-0 z-50 flex items-end" role="presentation">
        <motion.div className="absolute inset-0 bg-night/60" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} aria-hidden />
        <motion.section
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          className="relative max-h-[78vh] w-full overflow-y-auto rounded-t-3xl bg-paper px-4 pb-[max(env(safe-area-inset-bottom),16px)] pt-2 text-ink shadow-lift"
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "100%" }}
          transition={{ type: "spring", damping: 30, stiffness: 320 }}
          data-organ-panel={part}
        >
          <div className="mx-auto mb-2 h-1.5 w-10 rounded-full bg-line" aria-hidden />
          {body}
        </motion.section>
      </div>
    );
  }
  return (
    <motion.section
      role="dialog"
      aria-labelledby={titleId}
      className="absolute bottom-3 right-3 top-3 z-40 w-[19.5rem] overflow-y-auto rounded-3xl bg-paper p-4 text-ink shadow-lift"
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 24 }}
      transition={{ duration: 0.22 }}
      data-organ-panel={part}
    >
      {body}
    </motion.section>
  );
}
