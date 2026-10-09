import { useId, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AnimatePresence, m as motion } from "framer-motion";
import {
  ChevronDown,
  Clock,
  Diamond,
  FastForward,
  Footprints,
  GraduationCap,
  HelpCircle,
  Loader2,
  Pause,
  Play,
  Repeat,
  Scale,
  Sparkles,
  TriangleAlert,
  UtensilsCrossed,
  X,
} from "lucide-react";
import type { Lang, PatientSummary, Prob, ReplayClock, RevealResult, TwinState, WhatIf } from "@/api/types";
import { useFoodSwaps } from "@/api/hooks";
import { canAdvance, replayLabel } from "@/lib/replay";
import { scenarioAssumptions, usualDinner } from "@/lib/stage";
import { direction, peakDelta, reliabilityTenths, widthChange } from "@/lib/evidence";
import { formatClock, formatInt, formatReplayTime, freqText, pct, signed, swapLabel, fixed } from "@/lib/format";
import { intervalKeys, stateBand } from "@/lib/intervals";
import { useApp, type ChangeKind, type StageChange, type StageDinner } from "@/store/app";
import { EvidenceChip, SimulationLabel } from "./evidence";
import { FreqDots, InfoTip, SyntheticBadge } from "./ui";
import { FreshnessMeter, LadderSwitch } from "./twin";

/* ---------------- Who: persona select ---------------- */
export function PersonaSelect({ patients, active, onPick }: { patients: PatientSummary[]; active: string | null; onPick: (id: string) => void }) {
  const { t } = useTranslation();
  const id = useId();
  const cur = patients.find((p) => p.id === active);
  return (
    <div className="flex min-w-0 items-center gap-2">
      <label htmlFor={id} className="sr-only">
        {t("stage.whose")}
      </label>
      <span className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full bg-marigold text-sm font-bold text-night sm:inline-flex" aria-hidden>
        {cur?.avatar_initials ?? "…"}
      </span>
      <div className="relative min-w-0">
        <select
          id={id}
          value={active ?? ""}
          onChange={(e) => onPick(e.target.value)}
          className="w-full min-w-0 max-w-[13rem] cursor-pointer appearance-none truncate rounded-full border border-night-line bg-night-2 py-2 pl-3.5 pr-9 text-base font-bold text-moon focus:border-marigold focus:outline-none focus:ring-2 focus:ring-marigold/40 sm:max-w-xs"
        >
          {patients.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} · {p.age}
            </option>
          ))}
        </select>
        <ChevronDown size={16} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-moon-2" aria-hidden />
      </div>
      <span className="hidden truncate text-xs text-moon-3 2xl:inline">{cur ? `${cur.city} · ${cur.occupation}` : ""}</span>
      <span className="shrink-0 whitespace-nowrap">
        <SyntheticBadge tone="night" note={cur?.source_note} />
      </span>
    </div>
  );
}

/* ---------------- Replay clock ---------------- */
export function ReplayBar({
  replay,
  fallbackNow,
  busy,
  playing,
  onAdvance,
  onTogglePlay,
  compact,
}: {
  replay: ReplayClock | null;
  fallbackNow?: string;
  busy?: boolean;
  playing: boolean;
  onAdvance: (min: number) => void;
  onTogglePlay: () => void;
  compact?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const label = replayLabel(t, i18n.language, replay, fallbackNow);
  const progress = replay ? Math.min(1, replay.offset_min / Math.max(1, replay.max_offset_min)) : 0;
  const wall = new Intl.DateTimeFormat(`${i18n.language}-u-nu-latn`, { hour: "numeric", minute: "2-digit" }).format(new Date());
  const disabled = !replay;
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2" data-tour="replay">
      <div className="flex min-w-0 items-center gap-2 rounded-full border border-dashed border-marigold/60 bg-night-2/80 py-1 pl-1.5 pr-3.5" role="status" aria-live="polite">
        <span className="inline-flex items-center gap-1 rounded-full bg-marigold px-2 py-0.5 text-[0.65rem] font-extrabold uppercase tracking-wider text-night">
          <Clock size={11} aria-hidden />
          {t("replay.badge")}
        </span>
        <span className="num truncate text-sm font-bold text-moon">{label}</span>
        <InfoTip label={t("replay.hint", { wall })} tone="night" />
      </div>
      {!disabled && (
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onTogglePlay}
            aria-pressed={playing}
            disabled={!canAdvance(replay, 15) && !playing}
            className="btn-night h-9 min-h-0 px-3 text-xs"
            aria-label={playing ? t("replay.pause") : t("replay.play")}
          >
            {playing ? <Pause size={14} aria-hidden /> : <Play size={14} aria-hidden />}
            {!compact && <span className="hidden sm:inline">{playing ? t("replay.pause") : t("replay.play")}</span>}
          </button>
          {[30, 60].map((mins) => (
            <button key={mins} type="button" className="btn-night hidden h-9 min-h-0 px-3 text-xs sm:inline-flex" disabled={busy || !canAdvance(replay, mins)} onClick={() => onAdvance(mins)}>
              <FastForward size={14} aria-hidden />
              {mins === 30 ? t("replay.plus30") : t("replay.plus60")}
            </button>
          ))}
          {busy && <Loader2 size={15} className="animate-spin text-marigold" aria-label={t("replay.advancing")} />}
        </div>
      )}
      {replay && (
        <span className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-night-3 xl:block" role="img" aria-label={t("replay.progress", { n: Math.round(progress * 100) })}>
          <span className="block h-full rounded-full bg-marigold/80" style={{ width: `${progress * 100}%` }} />
        </span>
      )}
    </div>
  );
}

/* ---------------- What might happen: summary strip ---------------- */
function Tile({ eyebrow, chip, children, className = "" }: { eyebrow: ReactNode; chip?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`stage-card flex min-w-0 flex-col gap-0.5 px-3 py-2.5 sm:px-4 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <p className="eyebrow text-moon-3">{eyebrow}</p>
        {chip}
      </div>
      {children}
    </div>
  );
}

export function ReliabilityLine({ prob, tone = "night", short = false }: { prob: Prob | null | undefined; tone?: "night" | "paper"; short?: boolean }) {
  const { t, i18n } = useTranslation();
  const r = reliabilityTenths(prob ?? null);
  const cls = tone === "night" ? "text-moon-2" : "text-ink-2";
  if (!r) return <p className={`text-xs leading-snug ${cls}`}>{short ? t("risk.reliabilityMissingShort") : t("risk.reliabilityMissing")}</p>;
  if (short) return <p className={`num text-xs leading-snug ${cls}`}>{t("risk.reliabilityShort", { said: r.said, happened: r.happened })}</p>;
  return (
    <p className={`text-xs leading-snug ${cls}`}>
      {t("risk.reliability", { said: r.said, happened: r.happened })}{" "}
      <span className="num opacity-80">{t("risk.reliabilityCi", { lo: r.lo, hi: r.hi, n: formatInt(r.n, i18n.language) })}</span>
    </p>
  );
}

export function SummaryStrip({
  state,
  risk,
  riskContext,
  onWhy,
  onAdd,
}: {
  state: TwinState;
  /** The 2-hour high-glucose risk of the future shown on the chart. */
  risk: Prob | null;
  riskContext: string | null;
  onWhy: () => void;
  onAdd: () => void;
}) {
  const { t, i18n } = useTranslation();
  const last = state.last_observation;
  const h = state.freshness.hours_since_reading;
  const p = risk?.p ?? null;
  const halfBand = Math.round((state.band.hi - state.band.lo) / 2);
  const nowBand = stateBand(state);
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-[1fr_1fr_1.35fr_1fr] lg:gap-3" aria-live="polite">
      <Tile eyebrow={t("stage.estimate")} chip={<EvidenceChip status="estimated" tone="night" />}>
        <p className="flex items-baseline gap-1.5">
          <motion.span key={state.estimate} initial={{ opacity: 0.4 }} animate={{ opacity: 1 }} className="num text-3xl font-light tracking-tight text-moon sm:text-4xl">
            {Math.round(state.estimate)}
          </motion.span>
          <span className="text-sm text-moon-2">{t("common.mgdl")}</span>
        </p>
        {/* Calibrated present-state band (state.band). Not the same interval as the chart/body "now" spread. */}
        <p className="num flex items-center gap-0.5 text-xs text-moon-2" data-interval="calibratedNow">
          {t(intervalKeys(nowBand.kind).short, { lo: Math.round(nowBand.lo), hi: Math.round(nowBand.hi) })}
          <InfoTip label={t(intervalKeys(nowBand.kind).explain)} tone="night" />
        </p>
      </Tile>

      <Tile eyebrow={t("stage.lastMeasured")} chip={last ? <EvidenceChip status="measured" tone="night" /> : undefined} className="hidden lg:flex">
        {last ? (
          <>
            <p className="flex items-baseline gap-1.5">
              <span className="num text-2xl font-bold text-moon">{Math.round(last.value)}</span>
              <span className="text-sm text-moon-2">{t("common.mgdl")}</span>
            </p>
            <p className="text-xs text-moon-2">
              {t(last.kind === "cgm" ? "stage.cgm" : last.kind === "lab" ? "stage.lab" : "stage.fingerprick")} · {formatReplayTime(t, last.t, state.replay?.now ?? state.now, i18n.language)} ·{" "}
              {h < 1 ? t("stage.minAgo", { n: Math.round(h * 60) }) : t("stage.hAgo", { n: fixed(h, 1) })}
            </p>
          </>
        ) : (
          <>
            <p className="text-base font-semibold text-moon">{t("freshness.never")}</p>
            <button type="button" onClick={onAdd} className="self-start text-xs font-semibold text-marigold underline underline-offset-4">
              {t("actions.add")}
            </button>
          </>
        )}
      </Tile>

      <Tile eyebrow={t("risk.next2h")} chip={<EvidenceChip status="validated" tone="night" />}>
        {p !== null ? (
          <>
            <p className="text-base font-bold leading-tight text-coral-night sm:text-xl">{freqText(t, p)}</p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <FreqDots p={p} tone="coral" />
              <span className="num text-xs text-moon-2">{t("risk.pctOf", { n: pct(p) })}</span>
            </div>
            {riskContext && <p className="text-xs text-moon-3">{riskContext}</p>}
            <div className="hidden lg:block">
              <ReliabilityLine prob={risk} short />
            </div>
          </>
        ) : (
          <div className="skeleton-night h-10" />
        )}
      </Tile>

      <Tile eyebrow={t("stage.howSure")} className="hidden lg:flex">
        <p className="text-sm text-moon">
          <span className="num font-bold">±{halfBand}</span> {t("common.mgdl")} <span className="text-moon-2">{t("stage.bandNow")}</span>
        </p>
        <p className="text-xs text-moon-2">
          {t("freshness.label")}: <span className="font-semibold">{t(`freshness.${state.freshness.label}`)}</span>
        </p>
        <button type="button" onClick={onWhy} className="mt-0.5 inline-flex items-center gap-1 self-start text-xs font-semibold text-marigold underline underline-offset-4">
          <HelpCircle size={13} aria-hidden />
          {t("stage.evidenceLink")}
        </button>
      </Tile>
      {/* Phone: the same facts in one line, so the chart stays near the top. */}
      <p className="col-span-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 px-1 text-xs text-moon-2 lg:hidden">
        {last ? (
          <span>
            {t("stage.lastMeasured")}: <span className="num font-semibold text-moon">{Math.round(last.value)}</span> · {h < 1 ? t("stage.minAgo", { n: Math.round(h * 60) }) : t("stage.hAgo", { n: fixed(h, 1) })}
          </span>
        ) : (
          <span>{t("freshness.never")}</span>
        )}
        <span aria-hidden>·</span>
        <span>
          <span className="num font-semibold text-moon">±{halfBand}</span> {t("stage.bandNow")}
        </span>
        <button type="button" onClick={onWhy} className="font-semibold text-marigold underline underline-offset-4">
          {t("stage.evidenceLink")}
        </button>
      </p>
    </div>
  );
}

/* ---------------- Low glucose: evidence status instead of a big number ---------------- */
export function LowEvidencePanel({ prob, tone = "night" }: { prob: Prob | null | undefined; tone?: "night" | "paper" }) {
  const { t } = useTranslation();
  const p = prob?.p;
  const night = tone === "night";
  return (
    <section className={night ? "stage-card p-4" : "card p-5"} aria-labelledby="low-ev-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="low-ev-title" className={`text-sm font-bold ${night ? "text-moon" : ""}`}>
          {t("lowPanel.title")}
        </h2>
        <EvidenceChip status="not_validated" tone={tone} />
      </div>
      <p className={`mt-1.5 text-sm leading-relaxed ${night ? "text-moon-2" : "text-ink-2"}`}>{t("lowPanel.body")}</p>
      <p className={`mt-1 text-xs leading-relaxed ${night ? "text-moon-3" : "text-ink-3"}`}>{t("lowPanel.safety")}</p>
      {typeof p === "number" && (
        <details className={`mt-2 text-xs ${night ? "text-moon-3" : "text-ink-3"}`}>
          <summary className="cursor-pointer font-semibold">{t("lowPanel.showRaw")}</summary>
          <p className="mt-1">{t("lowPanel.raw", { text: freqText(t, p) })}</p>
        </details>
      )}
    </section>
  );
}

/* ---------------- Your dinner + one change ---------------- */
const CHANGE_ICON: Record<ChangeKind, typeof Scale> = { portion: Scale, walk: Footprints, swap: Repeat, timing: Clock };

export function DinnerPanel({ state, dinner, change }: { state: TwinState | undefined; dinner: StageDinner | null; change: StageChange | null }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const setDinner = useApp((s) => s.setStageDinner);
  const setChange = useApp((s) => s.setStageChange);
  const seedWhatIf = useApp((s) => s.seedWhatIf);
  const swaps = useFoodSwaps(i18n.language as Lang);
  const usual = usualDinner(state);

  const options = useMemo(() => {
    const out: StageChange[] = [
      { kind: "portion", scenario: { carb_scale: 0.7, label: "70% of the carbs" }, label: t("futures.change.portion", { pct: 70 }) },
      { kind: "walk", scenario: { walk_min: 15, walk_after_min: 10, label: "15-minute walk after the meal" }, label: t("futures.change.walk", { n: 15 }) },
    ];
    const items = new Set((dinner?.meal.items ?? []).map((i) => i.food_id));
    const sw = (swaps.data ?? []).find((s) => items.has(s.from));
    if (sw) out.push({ kind: "swap", scenario: { swap: { from: sw.from, to: sw.to, from_qty: sw.from_qty, to_qty: sw.to_qty }, label: sw.label_en }, label: swapLabel(sw, i18n.language).text });
    out.push({ kind: "timing", scenario: { shift_min: -30, label: "Eat 30 minutes earlier" }, label: t("futures.change.timing", { n: 30 }) });
    return out;
  }, [dinner, swaps.data, t, i18n.language]);

  const sd = dinner?.meal.carbs_sd ? Math.round(dinner.meal.carbs_sd) : null;
  return (
    <section className="stage-card flex flex-col gap-3 p-4" aria-labelledby="dinner-title" data-tour="dinner">
      <div className="flex items-center justify-between gap-2">
        <h2 id="dinner-title" className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-moon-2">
          <UtensilsCrossed size={15} className="text-marigold" aria-hidden />
          {t("futures.dinnerTitle")}
        </h2>
        {dinner && (
          <button type="button" onClick={() => setDinner(null)} className="rounded-full p-1.5 text-moon-3 hover:bg-night-3 hover:text-moon" aria-label={t("futures.removeDinner")}>
            <X size={15} aria-hidden />
          </button>
        )}
      </div>
      {dinner ? (
        <div>
          <p className="text-base font-bold text-moon">{dinner.source === "usual" ? t("whatif.usualDinner") : dinner.title}</p>
          <p className="num text-sm text-moon-2">
            {t("futures.dinnerCarbs", { n: Math.round(dinner.meal.carbs) })}
            {sd ? ` ${t("meal.plusMinus", { n: sd })}` : ""} · {t("meal.inMin", { n: dinner.meal.minutes_from_now ?? 30 })}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-moon-2">{t("futures.pickDinner")}</p>
          {usual && (
            <button
              type="button"
              onClick={() => setDinner({ meal: usual, source: "usual", title: usual.name ?? "" })}
              className="flex w-full items-center justify-between gap-2 rounded-2xl border border-marigold/50 bg-marigold/10 px-3.5 py-2.5 text-left text-sm font-semibold text-moon hover:bg-marigold/20"
            >
              <span>
                {t("whatif.usualDinner")}
                <span className="num block text-xs font-normal text-moon-2">{t("futures.fromHistory", { n: Math.round(usual.carbs) })}</span>
              </span>
              <span className="rounded-full bg-marigold px-2.5 py-1 text-xs font-bold text-night">{t("futures.confirm")}</span>
            </button>
          )}
          <Link to="/meal" className="flex items-center gap-2 rounded-2xl border border-night-line px-3.5 py-2.5 text-sm font-semibold text-moon hover:bg-night-3">
            <Sparkles size={15} className="text-marigold" aria-hidden />
            {t("futures.snap")}
          </Link>
        </div>
      )}

      <div>
        <p id="change-label" className="mb-1.5 text-xs font-semibold text-moon-3">
          {t("futures.exploreChange")}
        </p>
        <div role="radiogroup" aria-labelledby="change-label" className="flex flex-wrap gap-1.5">
          {options.map((o) => {
            const Icon = CHANGE_ICON[o.kind];
            const on = change?.kind === o.kind;
            return (
              <button
                key={o.kind}
                type="button"
                role="radio"
                aria-checked={on}
                disabled={!dinner}
                onClick={() => setChange(on ? null : o)}
                className={`chip min-h-[38px] text-xs disabled:cursor-not-allowed disabled:opacity-40 ${on ? "border-marigold bg-marigold text-night" : "border-night-line text-moon hover:border-marigold/60"}`}
              >
                <Icon size={13} aria-hidden />
                {o.label}
              </button>
            );
          })}
        </div>
        {!dinner && <p className="mt-1.5 text-xs text-moon-3">{t("futures.needDinner")}</p>}
        {dinner && (
          <button
            type="button"
            className="mt-2 text-xs font-semibold text-marigold underline underline-offset-4"
            onClick={() => {
              seedWhatIf({ base: dinner.meal, scenario: change?.scenario ?? {} });
              navigate("/whatif");
            }}
          >
            {t("futures.openStudio")}
          </button>
        )}
      </div>
    </section>
  );
}

/* ---------------- Simulated difference ---------------- */
const pts = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(Math.round(v * 100))}`;

export function DifferenceStrip({ w, loading, change, dinner }: { w: WhatIf | null | undefined; loading: boolean; change: StageChange; dinner: StageDinner }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const pd = w ? peakDelta(w) : null;
  const assumptions = scenarioAssumptions(t, change.scenario, dinner.meal);
  return (
    <div className="rounded-3xl border border-violet-night/40 bg-night-2/70 p-3.5 sm:p-4" aria-live="polite" data-tour="difference">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-bold text-moon">{t("futures.diffTitle", { change: change.label })}</p>
        <SimulationLabel />
      </div>
      {!w ? (
        <div className="mt-2 flex items-center gap-2 text-sm text-moon-2">{loading && <Loader2 size={15} className="animate-spin" aria-hidden />}{t("whatif.computing")}</div>
      ) : w.too_small_to_call ? (
        <div className="mt-2">
          <p className="text-xl font-extrabold text-moon">{t("whatif.tooSmall")}</p>
          <p className="text-sm text-moon-2">{t("futures.tooSmallBody")}</p>
          <p className="num mt-1 text-xs text-moon-3">
            {t("futures.riskDelta", { d: pts(w.delta_p_high.mean) })} · {t("whatif.interval", { lo: pts(w.delta_p_high.lo), hi: pts(w.delta_p_high.hi) })}
          </p>
        </div>
      ) : (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <div>
            <p className="eyebrow text-moon-3">{t("futures.peakLabel")}</p>
            <p className={`num text-2xl font-extrabold ${pd && pd.mean < 0 ? "text-teal" : "text-coral-night"}`}>
              {pd ? signed(pd.mean) : "—"} <span className="text-sm font-semibold text-moon-2">{t("common.mgdl")}</span>
            </p>
            {pd && pd.lo !== null && pd.hi !== null && <p className="num text-xs text-moon-3">{t("futures.peakInterval", { lo: signed(pd.lo), hi: signed(pd.hi) })}</p>}
          </div>
          <div>
            <p className="eyebrow text-moon-3">{t("futures.riskLabel")}</p>
            <p className={`num text-2xl font-extrabold ${w.delta_p_high.mean < 0 ? "text-teal" : "text-coral-night"}`}>
              {pts(w.delta_p_high.mean)} <span className="text-sm font-semibold text-moon-2">{t("futures.points")}</span>
            </p>
            <p className="num text-xs text-moon-3">{t("whatif.interval", { lo: pts(w.delta_p_high.lo), hi: pts(w.delta_p_high.hi) })}</p>
          </div>
        </div>
      )}
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-moon-2 underline underline-offset-4">
        <ChevronDown size={13} className={`transition ${open ? "rotate-180" : ""}`} aria-hidden />
        {t("futures.assumptions")}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.ul initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="mt-1.5 list-disc space-y-0.5 overflow-hidden pl-5 text-xs text-moon-2">
            {assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ---------------- Watch the twin learn ---------------- */
export function LearnPanel({
  state,
  reveal,
  revealing,
  learning,
  learned,
  onReveal,
  onLearn,
  onDismiss,
  onAdvance,
  advancing,
}: {
  state: TwinState;
  reveal: RevealResult | null;
  revealing: boolean;
  learning: boolean;
  learned: RevealResult | null;
  onReveal: () => void;
  onLearn: () => void;
  onDismiss: () => void;
  onAdvance: (min: number) => void;
  advancing: boolean;
}) {
  const { t, i18n } = useTranslation();
  const replay = state.replay ?? null;
  const ref = reveal?.reference;
  const before = reveal?.before;
  const inside = ref && before ? ref.value >= before.band.lo && ref.value <= before.band.hi : null;
  const diff = ref && before ? Math.round(ref.value - before.estimate) : null;
  const wc = learned?.after ? widthChange(learned.after) : null;
  const dir120 = wc ? direction(wc.h120.signed_pct) : null;
  return (
    <section className="stage-card flex flex-col gap-3 p-4" aria-labelledby="learn-title" data-tour="learn">
      <h2 id="learn-title" className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-moon-2">
        <GraduationCap size={15} className="text-teal" aria-hidden />
        {t("learn.title")}
      </h2>
      {!reveal && (
        <>
          <p className="text-sm text-moon-2">{t("learn.intro")}</p>
          <div className="flex flex-wrap gap-1.5">
            {[30, 60].map((m) => (
              <button key={m} type="button" className="btn-night h-9 min-h-0 px-3 text-xs" disabled={advancing || !canAdvance(replay, m)} onClick={() => onAdvance(m)}>
                <FastForward size={13} aria-hidden />
                {m === 30 ? t("learn.advance30") : t("learn.advance60")}
              </button>
            ))}
          </div>
          <button type="button" className="btn-marigold h-10 min-h-0 w-full text-sm" onClick={onReveal} disabled={revealing || !replay} aria-busy={revealing}>
            {revealing ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Diamond size={15} aria-hidden />}
            {t("learn.reveal")}
          </button>
          {!replay && <p className="text-xs text-moon-3">{t("learn.needsReplay")}</p>}
        </>
      )}
      {reveal && ref && before && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-2.5">
          <div className="rounded-2xl border border-dashed border-teal/60 bg-teal/10 p-3">
            <p className="flex items-center gap-1.5 text-xs font-bold text-teal">
              <Diamond size={13} aria-hidden />
              {t("learn.refTitle")}
            </p>
            <p className="mt-0.5 flex items-baseline gap-1.5">
              <span className="num text-3xl font-bold text-moon">{Math.round(ref.value)}</span>
              <span className="text-sm text-moon-2">{t("common.mgdl")}</span>
              <span className="text-xs text-moon-3">· {formatClock(ref.t, i18n.language)}</span>
            </p>
            <p className="text-xs leading-snug text-moon-2">{t("learn.refSource")}</p>
          </div>
          <p className="text-sm leading-snug text-moon">
            {t("learn.compare", { est: Math.round(before.estimate), lo: Math.round(before.band.lo), hi: Math.round(before.band.hi) })}{" "}
            <span className={inside ? "text-teal" : "text-coral-night"}>
              {inside ? t("learn.inside") : diff !== null && diff > 0 ? t("learn.above", { n: diff }) : t("learn.below", { n: Math.abs(diff ?? 0) })}
            </span>
          </p>
          {!learned ? (
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-marigold h-10 min-h-0 flex-1 text-sm" onClick={onLearn} disabled={learning} aria-busy={learning}>
                {learning ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <GraduationCap size={15} aria-hidden />}
                {t("learn.learn")}
              </button>
              <button type="button" className="btn-night h-10 min-h-0 text-sm" onClick={onDismiss}>
                {t("common.cancel")}
              </button>
            </div>
          ) : (
            wc && (
              <div className="rounded-2xl bg-night/60 p-3">
                <p className="text-xs font-semibold text-moon-3">{t("learn.bandAt", { h: 2 })}</p>
                <p className="num text-lg font-bold text-moon">
                  {t("learn.widthFromTo", { a: Math.round(wc.h120.before), b: Math.round(wc.h120.after) })}{" "}
                  <span className={dir120 === "wider" ? "text-coral-night" : dir120 === "narrower" ? "text-teal" : "text-moon-2"}>
                    ({signed(wc.h120.signed_pct)}%)
                  </span>
                </p>
                <p className="text-xs leading-snug text-moon-2">
                  {dir120 === "wider" ? t("learn.widerWhy") : dir120 === "narrower" ? t("learn.narrowerWhy") : t("learn.sameWhy")}
                </p>
                <p className="num mt-1 text-xs text-moon-3">{t("learn.nowBand", { a: Math.round(wc.now.before), b: Math.round(wc.now.after), d: signed(wc.now.signed_pct) })}</p>
                <button type="button" className="mt-2 text-xs font-semibold text-marigold underline underline-offset-4" onClick={onDismiss}>
                  {t("learn.again")}
                </button>
              </div>
            )
          )}
        </motion.div>
      )}
    </section>
  );
}

/* ---------------- Experiment panel: the sensor ladder ---------------- */
export function ExperimentPanel({ state, ladder, onLadder, busy, defaultOpen = false }: { state: TwinState | undefined; ladder: import("@/api/types").Ladder; onLadder: (l: import("@/api/types").Ladder) => void; busy: boolean; defaultOpen?: boolean }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <section className="stage-card p-4" data-tour="experiment">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-2 text-left">
        <span>
          <span className="flex items-center gap-2 text-sm font-bold text-moon">
            <TriangleAlert size={15} className="text-marigold" aria-hidden />
            {t("experiment.title")}
          </span>
          <span className="block text-xs text-moon-3">{t("experiment.subtitle", { level: t(`ladder.${ladder === "full" ? "full" : ladder === "0" ? "none" : `p${ladder}`}`) })}</span>
        </span>
        <ChevronDown size={18} className={`shrink-0 text-moon-2 transition ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {open && (
        <div id={id} className="mt-3 grid gap-4">
          <LadderSwitch value={ladder} onChange={onLadder} busy={busy} />
          {state && <FreshnessMeter freshness={state.freshness} />}
          <p className="text-xs leading-relaxed text-moon-3">{t("experiment.note")}</p>
        </div>
      )}
    </section>
  );
}

