import { Component, Suspense, lazy, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Activity, HelpCircle, Loader2, PersonStanding, Plus, Table2, Droplet } from "lucide-react";
import type { Assimilation, Forecast, RevealResult } from "@/api/types";
import { ApiError, UnreachableError } from "@/api/http";
import { useActivePatientId, useAdvance, useForecast, usePatients, useReveal, useTwinState, useWhatIf } from "@/api/hooks";
import { GlucoseRiver, type Futures, type RippleEvent } from "@/charts/GlucoseRiver";
import { ChartTable } from "@/charts/ChartTable";
import { AbstainCard } from "@/components/twin";
import { AddReadingSheet } from "@/components/AddReadingSheet";
import { DifferenceStrip, DinnerPanel, ExperimentPanel, LearnPanel, LowEvidencePanel, PersonaSelect, ReliabilityLine, ReplayBar, SummaryStrip } from "@/components/stage";
import { EvidenceChip } from "@/components/evidence";
import { ErrorState, InfoTip } from "@/components/ui";
import { useApp } from "@/store/app";
import { toast } from "@/store/toast";
import { formatReplayTime, signed } from "@/lib/format";
import { canAdvance } from "@/lib/replay";
import { stageRenderer } from "@/lib/stageRender";
import { direction, isUrgent, widthChange } from "@/lib/evidence";

const RANGES = [6, 12, 36];

// The 3-D glass body (three.js) is its own chunk, loaded only when the Body view is shown.
const BodyView = lazy(() => import("@/body/BodyView"));

function BodySkeleton() {
  const { t } = useTranslation();
  return (
    <div className="skeleton-night flex h-[430px] items-center justify-center rounded-3xl md:h-[480px]" aria-busy="true">
      <span className="text-sm text-moon-2">{t("body.loading")}</span>
    </div>
  );
}

/** If the body view (its chunk or the component) fails, the stage falls back to the chart. */
class BodyBoundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
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

function Legend({ two }: { two: boolean }) {
  const { t } = useTranslation();
  const item = "inline-flex items-center gap-1.5";
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-moon-2">
      <li className={item}>
        <span className="h-2.5 w-2.5 rounded-full border-2 border-moon bg-night" aria-hidden />
        {t("stage.fingerprick")}
      </li>
      <li className={item}>
        <span className="h-0.5 w-4 rounded bg-moon/60" aria-hidden />
        {t("stage.pastLine")}
      </li>
      {two && (
        <li className={item}>
          <span className="w-4 border-t-2 border-dashed border-moon" aria-hidden />
          {t("futures.asPlanned")}
        </li>
      )}
      <li className={item}>
        <span className="h-1 w-4 rounded bg-marigold" aria-hidden />
        {two ? t("futures.withChange") : t("stage.forecast")}
      </li>
      <li className={item}>
        <span className="h-3 w-4 rounded bg-marigold/25" aria-hidden />
        {t("stage.band")}
        <InfoTip label={t("glossary.band")} tone="night" />
      </li>
      <li className={item}>
        <span className="w-4 border-t-2 border-dotted border-moon-3" aria-hidden />
        {t("stage.exploratoryLegend")}
        <InfoTip label={t("evidence.explain.exploratory")} tone="night" />
      </li>
    </ul>
  );
}

/** Next useful measurement: an experimental suggestion (its benefit was not shown in testing). */
function NextCheck({ time, gain, replayNow }: { time: string; gain: number; replayNow: string | null }) {
  const { t, i18n } = useTranslation();
  return (
    <section className="stage-card p-4" aria-labelledby="nbp-title" data-tour="nbp">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="nbp-title" className="flex items-center gap-2 text-sm font-bold text-moon">
          <Droplet size={15} className="text-marigold" aria-hidden />
          {t("nbp.title")}
        </h2>
        <EvidenceChip status="exploratory" tone="night" />
      </div>
      <p className="mt-1.5 text-base font-semibold text-moon">{t("nbp.headlineSoft", { time: formatReplayTime(t, time, replayNow, i18n.language) })}</p>
      <p className="text-xs text-moon-2">{t("nbp.gain", { pct: Math.round(gain) })}</p>
      <p className="mt-1 text-xs text-moon-3">{t("nbp.experimentalNote")}</p>
    </section>
  );
}

export function TwinStagePage() {
  const { t } = useTranslation();
  const patients = usePatients();
  const pid = useActivePatientId();
  const setPatient = useApp((s) => s.setPatient);
  const ladder = useApp((s) => s.ladder);
  const setLadder = useApp((s) => s.setLadder);
  const highlight = useApp((s) => s.highlight);
  const openWhy = useApp((s) => s.openWhy);
  const addOpen = useApp((s) => s.addReadingOpen);
  const setAddOpen = useApp((s) => s.setAddReadingOpen);
  const dinner = useApp((s) => s.stageDinner);
  const change = useApp((s) => s.stageChange);
  const showSafety = useApp((s) => s.showSafety);
  const presentation = useApp((s) => s.presentation);
  const stageView = useApp((s) => s.stageView);
  const setStageView = useApp((s) => s.setStageView);
  const [bodyFailed, setBodyFailed] = useState(false);
  // stageRenderer: "chart" when chosen or when the body view failed; the body view itself picks 3-D vs 2-D.
  const bodyMode = stageRenderer({ pref: stageView === "chart" ? "chart" : "body", webgl: true, glFailed: false, simple: false, bodyFailed }) !== "chart";
  const state = useTwinState(pid, ladder);
  const advance = useAdvance(pid, ladder);
  const reveal = useReveal(pid, ladder);
  const [range, setRange] = useState(12);
  const [table, setTable] = useState(false);
  const [ripple, setRipple] = useState<RippleEvent | null>(null);
  const [ghost, setGhost] = useState<Forecast | null>(null);
  const [revealed, setRevealed] = useState<RevealResult | null>(null);
  const [learned, setLearned] = useState<RevealResult | null>(null);
  const [playing, setPlaying] = useState(false);
  const rippleSeq = useRef(0);
  const [vh, setVh] = useState(() => (typeof window === "undefined" ? 800 : window.innerHeight));
  useEffect(() => {
    const on = () => setVh(window.innerHeight);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  const wide = typeof window !== "undefined" && window.innerWidth >= 1024;
  // Desktop: the chart, the risk and the next action fit on one 1366x768 screen.
  const chartH = presentation ? Math.max(300, Math.min(460, vh - 380)) : wide ? Math.max(240, Math.min(380, vh - 420)) : undefined;
  const pidRef = useRef(pid);
  pidRef.current = pid;

  const s = state.data;
  // Two possible futures: the confirmed dinner, and the dinner with one change.
  const dinnerFc = useForecast(pid, dinner && !change ? { ladder, horizon_min: 240, meal: dinner.meal } : null);
  const wi = useWhatIf(pid, dinner && change ? { ladder, base_meal: dinner.meal, scenario: change.scenario } : null);
  const futures: Futures | null = dinner
    ? change && wi.data
      ? { baseline: wi.data.baseline, scenario: wi.data.scenario, baselineLabel: t("futures.asPlanned"), scenarioLabel: wi.isPlaceholderData ? t("whatif.computing") : change.label }
      : dinnerFc.data
        ? { baseline: dinnerFc.data, baselineLabel: t("futures.withDinner") }
        : null
    : null;
  const shownFc: Forecast | null = futures?.baseline ?? s?.forecast ?? null;
  // Fresh id for the forecast on screen (same inputs, same numbers) if the server has forgotten the old one.
  const refreshShown = async (): Promise<string | null> => {
    if (dinner && change) return (await wi.refetch()).data?.baseline.forecast_id ?? null;
    if (dinner) return (await dinnerFc.refetch()).data?.forecast_id ?? null;
    return (await state.refetch()).data?.forecast.forecast_id ?? null;
  };

  // Reset transient views when the persona changes (a pending request for the old one is ignored).
  useEffect(() => {
    setGhost(null);
    setRevealed(null);
    setLearned(null);
    setPlaying(false);
    setRipple(null);
  }, [pid, ladder]);
  useEffect(() => setGhost(null), [dinner, change]);

  useEffect(() => {
    if (!ripple) return;
    const id = window.setTimeout(() => setRipple(null), 2400);
    return () => window.clearTimeout(id);
  }, [ripple]);

  const showChart = () => document.querySelector('[data-tour="river"]')?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const errText = (e: unknown) =>
    e instanceof ApiError && e.status === 429 ? t("errors.rateLimited", { s: e.retryAfter ?? 30 }) : e instanceof UnreachableError ? t("errors.network") : t("errors.generic");

  const doAdvance = async (minutes: number) => {
    if (!pid || advance.isPending) return;
    const at = pid;
    setGhost(futures?.scenario ?? shownFc);
    setRevealed(null);
    setLearned(null);
    try {
      await advance.mutateAsync({ minutes });
    } catch (e) {
      if (pidRef.current === at) {
        setPlaying(false);
        toast(errText(e), "error");
      }
    }
  };

  // Play: advance the replay 15 minutes at a time until paused or the replay ends.
  useEffect(() => {
    if (!playing) return;
    if (!canAdvance(s?.replay ?? null, 15)) {
      setPlaying(false);
      return;
    }
    const id = window.setTimeout(() => void doAdvance(15), 2200);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, s?.replay?.offset_min]);

  const doReveal = async () => {
    if (!pid || reveal.isPending) return;
    const at = pid;
    setPlaying(false);
    try {
      const res = await reveal.mutateAsync({ assimilate: false });
      if (pidRef.current === at) setRevealed(res);
    } catch (e) {
      if (pidRef.current === at) toast(errText(e), "error");
    }
  };

  const doLearn = async () => {
    if (!pid || reveal.isPending) return;
    const at = pid;
    const prev = futures?.scenario ?? shownFc;
    try {
      const res = await reveal.mutateAsync({ assimilate: true });
      if (pidRef.current !== at) return;
      setLearned(res);
      setGhost(prev);
      showChart();
      if (res.after) {
        if (res.after.safety && isUrgent(res.after.safety.level)) showSafety(res.after.safety);
        rippleSeq.current += 1;
        setRipple({ key: rippleSeq.current, t: res.reference.t, value: res.reference.value, before: res.after.band_before, after: res.after.band_after });
      }
    } catch (e) {
      if (pidRef.current === at) toast(errText(e), "error");
    }
  };

  const onAssimilated = (a: Assimilation, mgdl: number) => {
    setGhost(futures?.scenario ?? shownFc);
    showChart();
    rippleSeq.current += 1;
    setRipple({ key: rippleSeq.current, t: a.state.last_observation?.t ?? a.state.now, value: mgdl, before: a.band_before, after: a.band_after });
    // A safety result outranks success: only an ok reading gets the band-change toast.
    if (a.safety && isUrgent(a.safety.level)) return;
    const wc = widthChange(a);
    const d = direction(wc.h120.signed_pct);
    const h = wc.h120.horizon_min ? Math.round(wc.h120.horizon_min / 60) : 0;
    const o = { h, a: Math.round(wc.h120.before), b: Math.round(wc.h120.after), pct: signed(wc.h120.signed_pct) };
    const msg = h
      ? d === "same"
        ? t("reading.unchangedAt", o)
        : d === "narrower"
          ? t("reading.narrowerAt", o)
          : t("reading.widerAt", o)
      : d === "same"
        ? t("reading.unchangedNow", o)
        : d === "narrower"
          ? t("reading.narrowerNow", o)
          : t("reading.widerNow", o);
    toast(msg, d === "wider" ? "warn" : "success", 6500);
  };

  const fc = s?.forecast;
  const abstain = s && (s.abstain?.flag || fc?.abstain?.flag);
  const abstainReason = s?.abstain?.reason ?? fc?.abstain?.reason ?? null;
  const stageHighlight = highlight && (highlight.view === "stage" || highlight.view === "forecast") ? highlight : null;
  const reference = learned?.reference ?? revealed?.reference ?? null;
  const twoFutures = !!futures?.scenario;
  const chartTitle = twoFutures ? t("futures.title") : dinner ? t("futures.oneFuture") : t("stage.chartTitle");

  return (
    <div className={`stage stage-wave on-night pb-24 lg:pb-6 ${presentation ? "presentation" : ""}`}>
      <section aria-labelledby="stage-title" className="mx-auto max-w-[1440px] px-4 pt-3 sm:px-6">
        {/* Who is this + replay clock */}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1.5">
            <h1 id="stage-title" className="w-full text-sm font-extrabold tracking-tight text-marigold sm:w-auto sm:text-lg xl:text-xl">
              {t("stage.tonight")}
            </h1>
            {patients.data ? (
              <PersonaSelect patients={patients.data} active={pid} onPick={setPatient} />
            ) : patients.isError ? (
              <ErrorState tone="night" message={t("errors.network")} onRetry={() => void patients.refetch()} />
            ) : (
              <div className="skeleton-night h-10 w-56" />
            )}
          </div>
          <ReplayBar
            replay={s?.replay ?? null}
            fallbackNow={s?.now}
            busy={advance.isPending}
            playing={playing}
            onAdvance={(m) => void doAdvance(m)}
            onTogglePlay={() => setPlaying((p) => !p)}
          />
        </div>

        {/* What might happen */}
        <div className="mt-3">
          {s ? (
            <SummaryStrip
              state={s}
              risk={shownFc?.p_high ?? null}
              riskContext={dinner ? t("risk.withDinner") : t("risk.noNewMeal")}
              onWhy={() => shownFc && openWhy(shownFc.forecast_id, undefined, undefined, refreshShown)}
              onAdd={() => setAddOpen(true)}
            />
          ) : state.isError ? (
            <ErrorState tone="night" message={t("stage.loadError")} onRetry={() => void state.refetch()} />
          ) : (
            <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="skeleton-night h-24" />
              ))}
            </div>
          )}
        </div>

        {/* What can I explore: chart (8) + actions (4) */}
        <div className="mt-3 grid gap-3 lg:grid-cols-12">
          <div className="min-w-0 space-y-3 lg:col-span-8">
            <div className="rounded-4xl border border-night-line/50 bg-night-2/40 px-1 pb-2 pt-2 sm:px-3" data-tour="river">
              <div className="flex flex-wrap items-center justify-between gap-2 px-2 pb-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-bold text-moon">{chartTitle}</h2>
                  <div role="radiogroup" aria-label={t("body.toggle.label")} className="flex rounded-full border border-night-line/70 p-0.5" data-stage-view>
                    {(["body", "chart"] as const).map((v) => {
                      const on = (v === "body") === bodyMode;
                      const Icon = v === "body" ? PersonStanding : Activity;
                      return (
                        <button
                          key={v}
                          type="button"
                          role="radio"
                          aria-checked={on}
                          onClick={() => setStageView(v)}
                          className={`inline-flex min-h-[32px] items-center gap-1 rounded-full px-3 text-xs font-semibold ${on ? "bg-marigold text-night" : "text-moon-2 hover:text-moon"}`}
                          data-stage-view-option={v}
                        >
                          <Icon size={14} aria-hidden />
                          {t(`body.toggle.${v}`)}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  {(state.isFetching || dinnerFc.isFetching || wi.isFetching) && (
                    <span className="inline-flex items-center gap-1.5 text-xs text-moon-3" role="status">
                      <Loader2 size={14} className="animate-spin" aria-hidden />
                      <span className="hidden sm:inline">{t("stage.updating")}</span>
                    </span>
                  )}
                  {!bodyMode && (
                    <>
                      <div role="radiogroup" aria-label={t("stage.range")} className="flex rounded-full border border-night-line/70 p-0.5">
                        {RANGES.map((r) => (
                          <button
                            key={r}
                            type="button"
                            role="radio"
                            aria-checked={range === r}
                            onClick={() => setRange(r)}
                            className={`num min-h-[32px] rounded-full px-2.5 text-xs font-semibold ${range === r ? "bg-moon text-night" : "text-moon-2 hover:text-moon"}`}
                          >
                            {t("stage.rangeHours", { n: r })}
                          </button>
                        ))}
                      </div>
                      <button type="button" onClick={() => setTable((v) => !v)} aria-pressed={table} className="btn-night h-9 min-h-0 px-2.5 text-xs" title={t("chartTable.toggle")}>
                        <Table2 size={15} aria-hidden />
                        <span className="sr-only sm:not-sr-only">{t("chartTable.toggleShort")}</span>
                      </button>
                    </>
                  )}
                  {shownFc && (
                    <button type="button" onClick={() => openWhy(shownFc.forecast_id, undefined, undefined, refreshShown)} className="btn-night h-9 min-h-0 px-3 text-xs">
                      <HelpCircle size={15} aria-hidden />
                      {t("common.why")}
                    </button>
                  )}
                </div>
              </div>
              {bodyMode ? (
                s ? (
                  <div className="px-1 pb-1 sm:px-0">
                    <BodyBoundary onError={() => setBodyFailed(true)}>
                    <Suspense fallback={<BodySkeleton />}>
                      <BodyView
                        pid={pid}
                        ladder={ladder}
                        state={s}
                        dinner={dinner}
                        change={change}
                        riskBaseline={shownFc?.p_high ?? null}
                        riskScenario={futures?.scenario?.p_high ?? null}
                        presentation={presentation}
                      />
                    </Suspense>
                    </BodyBoundary>
                  </div>
                ) : state.isError ? null : (
                  <BodySkeleton />
                )
              ) : s ? (
                <GlucoseRiver
                  state={s}
                  rangeHours={range}
                  futures={futures}
                  ghost={ghost}
                  reference={reference}
                  highlight={stageHighlight}
                  ripple={ripple}
                  pending={state.isPlaceholderData || dinnerFc.isFetching || wi.isFetching}
                  height={chartH}
                />
              ) : state.isError ? null : (
                <div className="skeleton-night h-[268px] sm:h-[360px]" aria-busy="true" />
              )}
              {bodyFailed && stageView !== "chart" && <p className="px-2 pt-1 text-xs text-moon-3" role="note">{t("body.fallbackChart")}</p>}
              {!bodyMode && (
                <div className="mt-1 px-2">
                  <Legend two={twoFutures} />
                </div>
              )}
              {!bodyMode && table && s && (
                <div className="mt-2 px-1">
                  <ChartTable state={s} futures={futures} rangeHours={range} />
                </div>
              )}
            </div>
            {dinner && change && <DifferenceStrip w={wi.isPlaceholderData ? null : (wi.data ?? null)} loading={wi.isFetching} change={change} dinner={dinner} />}
            {s && abstain && <AbstainCard reason={abstainReason} onAdd={() => setAddOpen(true)} />}
          </div>

          <div className="flex min-w-0 flex-col gap-3 lg:col-span-4">
            <button type="button" className="btn-marigold hidden h-12 w-full text-base lg:inline-flex" onClick={() => setAddOpen(true)} data-tour="add-reading">
              <Plus size={18} aria-hidden />
              {t("actions.add")}
            </button>
            <DinnerPanel state={s} dinner={dinner} change={change} />
            {s && (
              <LearnPanel
                state={s}
                reveal={revealed ?? learned}
                revealing={reveal.isPending && !revealed}
                learning={reveal.isPending && !!revealed}
                learned={learned}
                onReveal={() => void doReveal()}
                onLearn={() => void doLearn()}
                onDismiss={() => {
                  setRevealed(null);
                  setLearned(null);
                  setGhost(null);
                }}
                onAdvance={(m) => void doAdvance(m)}
                advancing={advance.isPending}
              />
            )}
          </div>
        </div>

        {/* How much to trust it */}
        <div className="mt-3 grid gap-3 pb-4 md:grid-cols-2 xl:grid-cols-4">
          {shownFc && (
            <section className="stage-card p-4" aria-labelledby="rel-title">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 id="rel-title" className="text-sm font-bold text-moon">
                  {t("risk.reliabilityTitle")}
                </h2>
                <EvidenceChip status="validated" tone="night" />
              </div>
              <div className="mt-1.5">
                <ReliabilityLine prob={shownFc.p_high} />
              </div>
            </section>
          )}
          <LowEvidencePanel prob={shownFc?.p_low} />
          {s && <NextCheck time={s.next_best_prick.time} gain={s.next_best_prick.expected_gain_pct} replayNow={s.replay?.now ?? s.now} />}
          <ExperimentPanel state={s} ladder={ladder} onLadder={setLadder} busy={state.isFetching} />
        </div>
      </section>

      {/* Mobile: one primary action */}
      <div className="no-print fixed inset-x-0 bottom-0 z-30 border-t border-night-line bg-night/95 px-4 pb-[max(env(safe-area-inset-bottom),10px)] pt-2.5 backdrop-blur-md lg:hidden">
        <button type="button" className="btn-marigold h-12 w-full text-base" onClick={() => setAddOpen(true)}>
          <Plus size={18} aria-hidden />
          {t("actions.add")}
        </button>
      </div>

      <AddReadingSheet open={addOpen} onClose={() => setAddOpen(false)} patientId={pid} ladder={ladder} replayNow={s?.replay?.now ?? s?.now ?? null} onAssimilated={onAssimilated} />
    </div>
  );
}
