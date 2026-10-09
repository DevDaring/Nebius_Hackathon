// The "glass body" view of the next hours (lazy chunk). Organ flows come from POST /twin/{pid}/body
// and are SIMULATED by the physiology model; only blood glucose (the forecast) is validated.
import { Component, Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, useReducedMotion } from "framer-motion";
import { Box, Clock, Minus, Plus, RotateCcw, Shapes, Table2, UtensilsCrossed } from "lucide-react";
import type { Ladder, OrganKey, Prob, TwinState } from "@/api/types";
import { useBody } from "@/api/hooks";
import { ErrorState, InfoTip } from "@/components/ui";
import { bodyBloodBand, intervalKeys } from "@/lib/intervals";
import { hasWebGL, textTableByDefault } from "@/lib/stageRender";
import { GlucoseRiver } from "@/charts/GlucoseRiver";
import { EvidenceChip, SimulationLabel } from "@/components/evidence";
import { formatClock, formatReplayTime, freqText, pct, signed } from "@/lib/format";
import { readJSON, writeJSON } from "@/lib/storage";
import type { StageChange, StageDinner } from "@/store/app";
import {
  N_STEPS,
  biggestChanges,
  clampIndex,
  formatOrganValue,
  glucoseZone,
  isExploratory,
  mealIndex,
  organIntensities,
  organScales,
  organValues,
  peakDelta,
  topActive,
  type BodyPart,
} from "@/lib/body";
import { BodySvg } from "./BodySvg";
import { OrganPanel } from "./OrganPanel";
import { Timeline } from "./Timeline";
import { PARTS, UNIT_KEY, partColor, partStats, variantOf } from "./meta";
import type { CameraCmd, CameraCmdIn, LiveState, SceneLabel } from "./types";
import { useMedia } from "@/hooks/useMedia";

const BodyScene = lazy(() => import("./three/BodyScene"));
const PLAY_MS = 12_000;
const SIMPLE_KEY = "nemotwins.bodySimple";

export interface BodyViewProps {
  pid: string | null;
  ladder: Ladder;
  state: TwinState;
  dinner: StageDinner | null;
  change: StageChange | null;
  /** 2-hour high-glucose chance of the future shown (from the stage's state / forecast / what-if queries). */
  riskBaseline: Prob | null;
  riskScenario: Prob | null;
  presentation: boolean;
}


/** A WebGL failure inside the canvas falls back to the 2-D view instead of breaking the stage. */
class SceneBoundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

const ZONE_TEXT = { low: "text-violet-night", in: "text-teal", high: "text-coral-night" } as const;

export default function BodyView({ pid, ladder, state: s, dinner, change, riskBaseline, riskScenario, presentation }: BodyViewProps) {
  const { t, i18n } = useTranslation();
  const reduced = !!useReducedMotion();
  const compact = useMedia("(max-width: 767px)");

  const req = useMemo(() => ({ ladder, ...(dinner ? { meal: dinner.meal } : {}), ...(dinner && change ? { scenario: change.scenario } : {}) }), [ladder, dinner, change]);
  const version = `${s.replay?.offset_min ?? 0}|${s.last_observation?.t ?? ""}|${s.history.readings.length}|${s.history.meals.length}`;
  const q = useBody(pid, req, version);
  const view = q.data && q.data.persona_id === pid ? q.data : null;

  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showScenario, setShowScenario] = useState(true);
  const [selected, setSelected] = useState<BodyPart | null>(null);
  const [cmd, setCmd] = useState<CameraCmd | null>(null);
  const seq = useRef(0);
  const [simple, setSimple] = useState<boolean>(() => readJSON(SIMPLE_KEY, false));
  const [webgl] = useState(hasWebGL);
  const [glFailed, setGlFailed] = useState(false);
  const use3d = webgl && !glFailed && !simple;
  // Without WebGL the readable table opens by default (the 2-D body alone is not enough to read values).
  const [textView, setTextView] = useState(() => textTableByDefault({ webgl, glFailed: false }));
  useEffect(() => {
    if (glFailed) setTextView(true);
  }, [glFailed]);
  const [active, setActive] = useState(true);
  const live = useRef<LiveState>({ tf: 0, mixTarget: 1, playing: false });
  const stageRef = useRef<HTMLDivElement>(null);

  const issue = useCallback((c: CameraCmdIn) => {
    seq.current += 1;
    setCmd({ ...c, seq: seq.current } as CameraCmd);
  }, []);

  // New persona: back to "now", nothing selected.
  useEffect(() => {
    setIdx(0);
    live.current.tf = 0;
    setPlaying(false);
    setSelected(null);
  }, [pid]);
  // A newly chosen change is shown straight away (the toggle switches back to "as planned").
  useEffect(() => {
    if (change) setShowScenario(true);
  }, [change]);

  const scenOn = !!view?.scenario && showScenario;
  live.current.mixTarget = scenOn ? 1 : 0;
  live.current.playing = playing;

  // Stop rendering when the canvas is off-screen or the tab is hidden.
  const hasView = view !== null;
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    let onScreen = true;
    let visible = document.visibilityState !== "hidden";
    const upd = () => setActive(onScreen && visible);
    const io = typeof IntersectionObserver !== "undefined" ? new IntersectionObserver(([e]) => ((onScreen = e.isIntersecting), upd())) : null;
    io?.observe(el);
    const vis = () => ((visible = document.visibilityState !== "hidden"), upd());
    document.addEventListener("visibilitychange", vis);
    return () => {
      io?.disconnect();
      document.removeEventListener("visibilitychange", vis);
    };
  }, [hasView]);

  // Play: 4 h in ~12 s.
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    if (live.current.tf >= N_STEPS - 0.01) {
      live.current.tf = 0;
      setIdx(0);
    }
    const tick = (now: number) => {
      const L = live.current;
      L.tf = Math.min(N_STEPS, L.tf + ((now - last) / PLAY_MS) * N_STEPS);
      last = now;
      setIdx(clampIndex(L.tf));
      if (L.tf >= N_STEPS) {
        setPlaying(false);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const goTo = useCallback((i: number) => {
    const k = clampIndex(i);
    setPlaying(false);
    live.current.tf = k;
    setIdx(k);
  }, []);
  const togglePlay = () => {
    if (reduced) goTo(idx >= N_STEPS ? 0 : idx + 3);
    else setPlaying((p) => !p);
  };

  const mealIdx = dinner ? mealIndex(dinner.meal, scenOn ? change?.scenario : null) : null;
  const followMeal = () => {
    if (use3d) issue({ kind: "follow" });
    const start = Math.max(0, (mealIdx ?? 0) - 1);
    if (reduced) goTo(Math.min(N_STEPS, start + 7));
    else {
      live.current.tf = start;
      setIdx(start);
      setPlaying(true);
    }
  };

  const scales = useMemo(() => (view ? organScales(view) : null), [view]);
  const variant = view ? variantOf(view, scenOn) : null;
  const intens = useMemo(() => (view && scales ? organIntensities(organValues(view, idx, scenOn ? 1 : 0), scales) : null), [view, scales, idx, scenOn]);

  const labelFor = useCallback(
    (part: BodyPart): SceneLabel => {
      const st = partStats(variant!, part, idx);
      return {
        part,
        name: t(`body.part.${part}.name`),
        value: part === "blood" ? String(Math.round(st.q50)) : formatOrganValue(part as OrganKey, st.q50),
        unit: t(UNIT_KEY[part]),
        color: partColor(part, st.q50),
      };
    },
    [variant, idx, t],
  );
  const labels = useMemo(() => {
    if (!variant || !intens) return [];
    let parts: BodyPart[] = PARTS;
    if (compact) {
      parts = topActive(intens, 4);
      if (selected && !parts.includes(selected)) parts = [...parts, selected];
    }
    return parts.map(labelFor);
  }, [variant, intens, compact, selected, labelFor]);

  const onSelect = useCallback((p: BodyPart) => setSelected(p), []);
  const onFocus = useCallback((p: BodyPart) => issue({ kind: "focus", part: p }), [issue]);
  const onInteract = useCallback(() => undefined, []);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!use3d) return;
    const k = e.key;
    const map: Record<string, CameraCmdIn> = {
      ArrowLeft: { kind: "rotate", dAz: -0.3, dPolar: 0 },
      ArrowRight: { kind: "rotate", dAz: 0.3, dPolar: 0 },
      ArrowUp: { kind: "rotate", dAz: 0, dPolar: -0.12 },
      ArrowDown: { kind: "rotate", dAz: 0, dPolar: 0.12 },
      "+": { kind: "zoom", factor: 0.85 },
      "=": { kind: "zoom", factor: 0.85 },
      "-": { kind: "zoom", factor: 1.18 },
      _: { kind: "zoom", factor: 1.18 },
    };
    if (map[k]) {
      e.preventDefault();
      issue(map[k]);
    }
  };

  const setSimplePref = (v: boolean) => {
    setSimple(v);
    writeJSON(SIMPLE_KEY, v || null);
  };

  const canvasH = presentation ? (compact ? 480 : 580) : compact ? 430 : 480;
  const lang = i18n.language;

  if (!view || !variant || !scales || !intens) {
    if (q.isError && !q.data)
      // The body data failed: keep the forecast readable with the chart instead of hiding it.
      return (
        <div className="space-y-2 p-2" data-body-fallback="chart">
          <ErrorState tone="night" message={t("body.loadError")} onRetry={() => void q.refetch()} />
          <GlucoseRiver state={s} rangeHours={6} />
        </div>
      );
    return (
      <div className="relative flex items-center justify-center overflow-hidden rounded-3xl body-stage" style={{ height: canvasH }} aria-busy="true" data-body-loading>
        <div className="skeleton-night absolute inset-0 opacity-40" />
        <p className="relative flex items-center gap-2 text-sm text-moon-2">
          <Box size={16} className="animate-pulse text-marigold" aria-hidden />
          {t("body.loading")}
        </p>
      </div>
    );
  }

  // Relative to the replay clock's date: a 4-hour look-ahead can cross midnight.
  const time = formatReplayTime(t, view.t[idx] ?? view.t[0], view.replay_now ?? view.t[0], lang);
  const rel = idx === 0 ? t("body.time.now") : t("body.time.plusMin", { n: idx * 5 });
  const blood = partStats(variant, "blood", idx);
  const bloodBand = bodyBloodBand(view, idx, blood.lo, blood.hi);
  const zone = glucoseZone(blood.q50);
  const explo = isExploratory(idx, view.validated_horizon_min);
  const risk = scenOn ? (riskScenario ?? riskBaseline) : riskBaseline;
  const changes = scales && view.scenario ? biggestChanges(view, scales) : [];
  const pd = peakDelta(view);

  const card = (
    <div className={`rounded-2xl border border-night-line/60 bg-night/75 backdrop-blur-md ${compact ? "grid grid-cols-2 gap-x-3 gap-y-1 px-3 py-2" : "space-y-2 p-3.5"}`} data-body-card>
      <div className={compact ? "col-span-2 flex flex-wrap items-center gap-2" : ""}>
        <p className={`flex flex-wrap items-center gap-x-1.5 gap-y-1 font-bold text-moon ${presentation ? "text-base" : "text-sm"}`}>
          <span className="inline-flex items-center gap-1 rounded-full bg-marigold px-1.5 py-0.5 text-[0.62rem] font-extrabold uppercase tracking-wider text-night">
            <Clock size={10} aria-hidden />
            {t("replay.badge")}
          </span>
          <span className="num whitespace-nowrap">{time}</span>
          <span className="num whitespace-nowrap font-semibold text-moon-2">· {rel}</span>
        </p>
        {explo && <p className="mt-1 inline-flex rounded-full border border-moon-3/50 px-2 py-0.5 text-[0.68rem] font-semibold text-moon-2">{t("body.time.exploratory")}</p>}
      </div>
      <div>
        <p className="eyebrow text-moon-3">{t("body.card.bloodGlucose")}</p>
        <p className="flex items-baseline gap-1.5">
          <span className={`num font-light tracking-tight ${ZONE_TEXT[zone]} ${presentation ? "text-5xl" : compact ? "text-3xl" : "text-4xl"}`} data-body-glucose>
            {Math.round(blood.q50)}
          </span>
          <span className="text-sm text-moon-2">{t("common.mgdl")}</span>
        </p>
        {/* At "now" this is the raw particle spread, after now the forecast band: labelled as such, never as the calibrated range. */}
        <p className="num flex items-center gap-0.5 text-xs text-moon-2" data-interval={bloodBand.kind}>
          {t(intervalKeys(bloodBand.kind).short, { lo: Math.round(blood.lo), hi: Math.round(blood.hi) })}
          <InfoTip label={t(intervalKeys(bloodBand.kind).explain)} tone="night" />
        </p>
      </div>
      <div>
        <p className="eyebrow flex flex-wrap items-center gap-1.5 text-moon-3">{t("body.card.highChance")}</p>
        {risk ? (
          <>
            <p className={`font-bold leading-tight text-coral-night ${presentation ? "text-lg" : "text-sm"}`}>{freqText(t, risk.p)}</p>
            <p className="num flex flex-wrap items-center gap-1.5 text-xs text-moon-2">
              {t("risk.pctOf", { n: pct(risk.p) })}
              <EvidenceChip status="validated" tone="night" />
            </p>
          </>
        ) : (
          <div className="skeleton-night mt-1 h-6" />
        )}
      </div>
    </div>
  );

  const scenarioToggle = view.scenario && change && (
    <div role="radiogroup" aria-label={t("body.scenario.label")} className="flex w-full rounded-full border border-night-line/70 bg-night/60 p-0.5" data-body-scenario>
      {[false, true].map((on) => (
        <button
          key={String(on)}
          type="button"
          role="radio"
          aria-checked={showScenario === on}
          onClick={() => setShowScenario(on)}
          className={`min-h-[36px] flex-1 truncate rounded-full px-2.5 text-xs font-semibold transition-colors ${showScenario === on ? "bg-marigold text-night" : "text-moon-2 hover:text-moon"}`}
        >
          {on ? change.label : t("futures.asPlanned")}
        </button>
      ))}
    </div>
  );

  const diff = view.scenario && change && (
    <div className="space-y-1.5 rounded-2xl border border-violet-night/40 bg-night-2/80 p-3" aria-live="polite" data-body-diff>
      <p className="text-xs font-bold text-moon">{t("body.scenario.diffTitle")}</p>
      <ul className="space-y-1 text-xs text-moon-2">
        {changes.map((c) => (
          <li key={c.key} className="num">
            {t("body.scenario.change", {
              organ: t(`body.part.${c.key}.name`),
              d: signed(c.delta, c.key === "stomach" || c.key === "intestine" || c.key === "insulin" ? 0 : Math.abs(c.delta) < 1 ? 2 : 1),
              unit: t(UNIT_KEY[c.key]),
              time: formatClock(view.t[c.index], lang),
            })}
          </li>
        ))}
        {!changes.length && <li>{t("body.scenario.noChange")}</li>}
        {pd !== null && <li className="num font-semibold text-moon">{t("body.scenario.peak", { d: signed(pd) })}</li>}
      </ul>
      <SimulationLabel />
    </div>
  );

  const btn = `inline-flex ${compact ? "h-8 min-w-8 px-2" : "h-9 min-w-9 px-2.5"} items-center justify-center gap-1.5 rounded-full border border-night-line/70 bg-night/70 text-xs font-semibold text-moon backdrop-blur hover:border-marigold/70 disabled:opacity-40`;

  const controls = (
    <div className={`flex flex-wrap items-center gap-1.5 ${compact ? "justify-end" : ""}`} role="toolbar" aria-label={t("body.view.controls")} data-body-controls>
      {use3d &&
        (["front", "side", "back"] as const).map((k) => (
          <button key={k} type="button" className={btn} onClick={() => issue({ kind: k })} data-body-cam={k}>
            {t(`body.view.${k}`)}
          </button>
        ))}
      <button type="button" className={`${btn} border-marigold/60 text-marigold`} onClick={followMeal} title={t("body.view.follow")} data-body-follow>
        <UtensilsCrossed size={14} aria-hidden />
        <span className={compact ? "sr-only" : ""}>{t("body.view.follow")}</span>
      </button>
      {use3d && (
        <>
          {!compact && (
            <>
          <button type="button" className={btn} onClick={() => issue({ kind: "zoom", factor: 0.85 })} aria-label={t("body.view.zoomIn")} title={t("body.view.zoomIn")}>
            <Plus size={14} aria-hidden />
          </button>
          <button type="button" className={btn} onClick={() => issue({ kind: "zoom", factor: 1.18 })} aria-label={t("body.view.zoomOut")} title={t("body.view.zoomOut")}>
            <Minus size={14} aria-hidden />
          </button>
            </>
          )}
          <button type="button" className={btn} onClick={() => issue({ kind: "reset" })} aria-label={t("body.view.reset")} title={t("body.view.reset")} data-body-cam="reset">
            <RotateCcw size={14} aria-hidden />
          </button>
        </>
      )}
    </div>
  );

  return (
    <div className={`space-y-3 ${presentation ? "body-presentation" : ""}`} data-body-view={use3d ? "3d" : "2d"}>
      <div className={compact ? "space-y-2" : "grid grid-cols-[15rem_minmax(0,1fr)] gap-3"}>
        {/* numbers: always visible */}
        <div className={compact ? "space-y-2" : "flex flex-col gap-3"}>
          {card}
          {scenarioToggle}
          {!compact && controls}
          {!compact && diff}
          {!compact && !diff && <p className="mt-auto text-[0.7rem] leading-snug text-moon-3">{use3d ? t("body.hint") : t("body.organs.hint")}</p>}
        </div>

        <div
          ref={stageRef}
          className="body-stage relative overflow-hidden rounded-3xl border border-night-line/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-marigold"
          style={{ height: canvasH }}
          tabIndex={0}
          role="group"
          aria-label={t("body.canvasLabel")}
          aria-describedby="body-keys"
          onKeyDown={onKey}
          data-body-stage
        >
          {use3d ? (
            <SceneBoundary onError={() => setGlFailed(true)}>
              <Suspense fallback={<div className="absolute inset-0 flex items-center justify-center text-sm text-moon-2">{t("body.loading")}</div>}>
                <BodyScene
                  view={view}
                  scales={scales}
                  live={live}
                  labels={labels}
                  selected={selected}
                  onSelect={onSelect}
                  onFocus={onFocus}
                  cmd={cmd}
                  reducedMotion={reduced}
                  compact={compact}
                  presentation={presentation}
                  active={active}
                  playing={playing}
                  onInteract={onInteract}
                  ariaLabel={t("body.canvasLabel")}
                  onContextLost={() => setGlFailed(true)}
                />
              </Suspense>
            </SceneBoundary>
          ) : (
            <div className={`absolute inset-0 px-2 pb-9 ${compact ? "pt-12" : "pt-3"}`}>
              <BodySvg
                view={view}
                scales={scales}
                tf={idx}
                showScenario={scenOn}
                selected={selected}
                onSelect={onSelect}
                labels={labels}
                reducedMotion={reduced}
                presentation={presentation}
                ariaLabel={t("body.canvasLabel")}
              />
            </div>
          )}

          {compact && <div className="absolute inset-x-2 top-2 z-30">{controls}</div>}

          {/* honesty banner: always visible */}
          <p className={`pointer-events-none absolute inset-x-0 bottom-0 z-20 bg-gradient-to-t from-night/95 via-night/70 to-transparent px-3 pb-2 pt-5 text-center leading-snug text-moon-2 ${presentation ? "text-sm" : "text-[0.7rem]"}`} data-body-honesty>
            {t("body.honesty")}
          </p>

          <AnimatePresence>
            {selected && !compact && (
              <OrganPanel key={selected} view={view} part={selected} idx={idx} showScenario={scenOn} scenarioLabel={change?.label ?? null} compact={false} onClose={() => setSelected(null)} />
            )}
          </AnimatePresence>
        </div>
      </div>

      <p id="body-keys" className="sr-only">
        {t("body.hintKeys")}
      </p>

      <Timeline
        times={view.t}
        idx={idx}
        onIdx={goTo}
        playing={playing}
        onTogglePlay={togglePlay}
        reducedMotion={reduced}
        validatedMin={view.validated_horizon_min}
        mealIdx={mealIdx}
        blood={variant.blood.q50}
        presentation={presentation}
      />

      {compact && diff}

      {/* organ list: keyboard / screen-reader way into every organ */}
      <div>
        <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-xs font-bold uppercase tracking-wide text-moon-2">{t("body.organs.title")}</h3>
          <div className="flex items-center gap-1.5">
            <button type="button" className={btn} onClick={() => setTextView((v) => !v)} aria-pressed={textView} data-body-textview>
              <Table2 size={14} aria-hidden />
              {textView ? t("body.textView.hide") : t("body.textView.show")}
            </button>
            {webgl && !glFailed && (
              <button type="button" className={btn} onClick={() => setSimplePref(!simple)} aria-pressed={simple} data-body-simple>
                {simple ? <Box size={14} aria-hidden /> : <Shapes size={14} aria-hidden />}
                {simple ? t("body.view.threeD") : t("body.view.simple")}
              </button>
            )}
          </div>
        </div>
        {(!webgl || glFailed) && <p className="mb-1.5 text-xs text-moon-3">{t("body.noWebgl")}</p>}
        <ul className={`flex gap-1.5 ${compact ? "-mx-1 overflow-x-auto px-1 pb-1" : "flex-wrap"}`} aria-label={t("body.organs.title")}>
          {PARTS.map((part) => {
            const l = labelFor(part);
            const on = selected === part;
            return (
              <li key={part} className="shrink-0">
                <button
                  type="button"
                  onClick={() => setSelected(part)}
                  aria-pressed={on}
                  className={`chip min-h-[36px] whitespace-nowrap text-xs ${on ? "border-marigold bg-marigold/15 text-moon" : "border-night-line text-moon-2 hover:border-marigold/60 hover:text-moon"}`}
                  data-body-organ={part}
                >
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: l.color }} aria-hidden />
                  <span className="font-semibold text-moon">{l.name}</span>
                  <span className="num">
                    {l.value} <span className="text-moon-3">{l.unit}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {textView && (
        <div className="overflow-x-auto rounded-2xl border border-night-line/60" data-body-table>
          <table className="w-full min-w-[30rem] text-left text-xs text-moon-2">
            <caption className="px-3 py-2 text-left text-xs font-semibold text-moon">{t("body.textView.caption", { time: `${time} (${rel})` })}</caption>
            <thead className="bg-night-2/80 text-moon">
              <tr>
                <th scope="col" className="px-3 py-1.5 font-semibold">{t("body.textView.organ")}</th>
                <th scope="col" className="px-3 py-1.5 font-semibold">{t("body.textView.value")}</th>
                <th scope="col" className="px-3 py-1.5 font-semibold">{t("body.textView.range")}</th>
                <th scope="col" className="px-3 py-1.5 font-semibold">{t("body.textView.status")}</th>
              </tr>
            </thead>
            <tbody>
              {PARTS.map((part) => {
                const st = partStats(variant, part, idx);
                const f = (v: number) => (part === "blood" ? String(Math.round(v)) : formatOrganValue(part as OrganKey, v));
                return (
                  <tr key={part} className="border-t border-night-line/50">
                    <th scope="row" className="px-3 py-1.5 font-semibold text-moon">{t(`body.part.${part}.name`)}</th>
                    <td className="num px-3 py-1.5">
                      {f(st.q50)} {t(UNIT_KEY[part])}
                    </td>
                    <td className="num px-3 py-1.5">
                      {f(st.lo)}–{f(st.hi)}
                    </td>
                    <td className="px-3 py-1.5">{part === "blood" ? `${t("body.panel.validated2h")} · ${t(intervalKeys(bloodBand.kind).label)}` : t("evidence.status.simulated")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* screen readers: the selected time, announced when not playing */}
      <p className="sr-only" aria-live="polite">
        {playing ? "" : `${t("body.live", { time: `${time} (${rel})`, g: Math.round(blood.q50), lo: Math.round(blood.lo), hi: Math.round(blood.hi) })} ${t(intervalKeys(bloodBand.kind).label)}.`}
      </p>

      <AnimatePresence>
        {selected && compact && (
          <OrganPanel key={selected} view={view} part={selected} idx={idx} showScenario={scenOn} scenarioLabel={change?.label ?? null} compact onClose={() => setSelected(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}
