import { useTranslation } from "react-i18next";
import { m as motion, useReducedMotion } from "framer-motion";
import { Plus, TriangleAlert } from "lucide-react";
import type { Ladder, TwinState } from "@/api/types";
import { LADDERS } from "@/api/types";
import { pct, fixed } from "@/lib/format";
import { InfoTip } from "./ui";

/* ---------------- Sensor ladder ---------------- */
const LADDER_KEY: Record<Ladder, string> = { full: "ladder.full", "4": "ladder.p4", "2": "ladder.p2", "1": "ladder.p1", "0": "ladder.none" };

export function LadderSwitch({ value, onChange, busy }: { value: Ladder; onChange: (l: Ladder) => void; busy?: boolean }) {
  const { t } = useTranslation();
  const reduce = useReducedMotion();
  return (
    <div data-tour="ladder">
      <div className="mb-2 flex items-center gap-1">
        <span id="ladder-label" className="eyebrow text-moon-3">
          {t("ladder.label")}
        </span>
        <InfoTip label={t("glossary.ladder")} tone="night" />
        {busy && <span className="ml-1 h-1.5 w-1.5 animate-pulse rounded-full bg-marigold" aria-hidden />}
      </div>
      <div role="radiogroup" aria-labelledby="ladder-label" aria-describedby="ladder-hint" className="grid grid-cols-5 gap-1 rounded-2xl border border-night-line/70 bg-night/60 p-1">
        {LADDERS.map((l) => {
          const on = l === value;
          return (
            <button
              key={l}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(l)}
              className={`relative min-h-[44px] rounded-xl px-1 text-xs font-semibold leading-tight transition-colors sm:px-2.5 sm:text-[0.8rem] ${
                on ? "text-night" : "text-moon-2 hover:text-moon"
              }`}
            >
              {on && (
                <motion.span
                  layoutId="ladder-pill"
                  className="absolute inset-0 rounded-xl bg-marigold"
                  transition={reduce ? { duration: 0 } : { type: "spring", damping: 26, stiffness: 300 }}
                />
              )}
              <span className="relative">{t(LADDER_KEY[l])}</span>
            </button>
          );
        })}
      </div>
      <p id="ladder-hint" className="mt-1.5 text-xs text-moon-3">
        {t("ladder.hint")}
      </p>
    </div>
  );
}

/* ---------------- Freshness ---------------- */
export function FreshnessMeter({ freshness }: { freshness: TwinState["freshness"] }) {
  const { t } = useTranslation();
  const score = Math.max(0, Math.min(1, freshness.score));
  const color = freshness.label === "fresh" ? "rgb(var(--teal))" : freshness.label === "ageing" ? "rgb(var(--marigold))" : "rgb(var(--coral-night))";
  const r = 20;
  const c = 2 * Math.PI * r;
  const h = freshness.hours_since_reading;
  const since = !Number.isFinite(h) || h >= 24 ? t("freshness.never") : h < 1 ? t("freshness.sinceMin", { m: Math.round(h * 60) }) : t("freshness.since", { h: fixed(h, 1) });
  return (
    <div className="flex items-center gap-3">
      <svg width={52} height={52} viewBox="0 0 52 52" role="img" aria-label={`${t("freshness.label")}: ${t(`freshness.${freshness.label}`)} (${pct(score)}%)`}>
        <circle cx={26} cy={26} r={r} fill="none" stroke="rgb(var(--night-3))" strokeWidth={5} />
        <motion.circle
          cx={26}
          cy={26}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={5}
          strokeLinecap="round"
          transform="rotate(-90 26 26)"
          strokeDasharray={c}
          initial={false}
          animate={{ strokeDashoffset: c * (1 - score) }}
          transition={{ duration: 1 }}
        />
        <text x={26} y={26} dy="0.34em" textAnchor="middle" className="chart-label" fontWeight={700} fill="rgb(var(--moon))">
          {pct(score)}
        </text>
      </svg>
      <div className="leading-tight">
        <div className="flex items-center gap-1">
          <span className="eyebrow text-moon-3">{t("freshness.label")}</span>
          <InfoTip label={t("glossary.freshness")} tone="night" />
        </div>
        <p className="text-base font-bold" style={{ color }}>
          {t(`freshness.${freshness.label}`)}
        </p>
        <p className="text-xs text-moon-2">{since}</p>
      </div>
    </div>
  );
}

/* ---------------- Risk cards ---------------- */
/** Pill shown next to P(<70): the low-glucose classifier has not been validated. */
export function NotValidatedPill({ tone = "paper" }: { tone?: "paper" | "night" }) {
  const { t } = useTranslation();
  return (
    <InfoTip label={t("risk.notValidatedHint")} tone={tone}>
      <span
        className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[0.7rem] font-semibold ${
          tone === "night" ? "border-moon-3/50 text-moon-2" : "border-ink-3/40 bg-paper-2 text-ink-2"
        }`}
      >
        <TriangleAlert size={11} aria-hidden />
        {t("risk.notValidated")}
      </span>
    </InfoTip>
  );
}

/* ---------------- Abstain ---------------- */
export function AbstainCard({ reason, onAdd }: { reason: string | null; onAdd: () => void }) {
  const { t } = useTranslation();
  return (
    <article className="card flex flex-col items-start gap-3 border-marigold/60 p-6 sm:flex-row sm:items-center sm:justify-between" role="status">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 rounded-full bg-marigold/15 p-2 text-marigold-ink">
          <TriangleAlert size={20} aria-hidden />
        </span>
        <div>
          <h2 className="text-lg font-bold">{t("abstain.title")}</h2>
          <p className="text-ink-2">{t("abstain.body")}</p>
          {reason && (
            <p className="mt-1 text-sm text-ink-3" lang="en">
              {reason}
            </p>
          )}
        </div>
      </div>
      <button type="button" className="btn-primary shrink-0" onClick={onAdd}>
        <Plus size={17} aria-hidden />
        {t("abstain.action")}
      </button>
    </article>
  );
}

