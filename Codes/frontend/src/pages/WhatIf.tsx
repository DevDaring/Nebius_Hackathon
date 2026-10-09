import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Clock, Footprints, HelpCircle, Loader2, Pin, Repeat, RotateCcw, Scale, Scale3d, X } from "lucide-react";
import type { Lang, MealInput, Scenario, WhatIf as WhatIfResult } from "@/api/types";
import { useActivePatientId, useFoodSwaps, useTwinState, useWhatIf } from "@/api/hooks";
import { CompareChart } from "@/charts/CompareChart";
import { ErrorState, PageHeader } from "@/components/ui";
import { SimulationLabel } from "@/components/evidence";
import { peakDelta } from "@/lib/evidence";
import { useApp } from "@/store/app";
import { mealName, signed, swapLabel } from "@/lib/format";

const MAX_SAVED = 3;
const PIN_COLORS = ["rgb(var(--teal))", "rgb(var(--coral-night))", "rgb(var(--violet-night))"];

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

function ScenarioCard({ icon, title, active, children, value }: { icon: ReactNode; title: string; active: boolean; children: ReactNode; value: string }) {
  return (
    <section className={`card p-5 transition ${active ? "border-marigold-ink/60 ring-2 ring-marigold/40" : ""}`} aria-label={title}>
      <header className="mb-3 flex items-center justify-between gap-2">
        <span className="flex items-center gap-2.5">
          <span className={`inline-flex h-9 w-9 items-center justify-center rounded-full ${active ? "bg-marigold text-night" : "bg-paper-2 text-ink-2"}`}>{icon}</span>
          <h2 className="font-bold">{title}</h2>
        </span>
        <span className={`text-sm font-semibold ${active ? "text-marigold-ink" : "text-ink-3"}`}>{value}</span>
      </header>
      {children}
    </section>
  );
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick} className={`chip ${on ? "border-ink bg-ink text-paper" : "border-line bg-card text-ink hover:bg-paper-2"}`}>
      {children}
    </button>
  );
}

const FALLBACK_MEAL: MealInput = { carbs: 75, fibre: 6, protein: 15, fat: 14, minutes_from_now: 30 };

export default function WhatIfPage() {
  const { t, i18n } = useTranslation();
  const pid = useActivePatientId();
  const ladder = useApp((s) => s.ladder);
  const seed = useApp((s) => s.whatIfSeed);
  const draft = useApp((s) => s.mealDraft);
  const openWhy = useApp((s) => s.openWhy);
  const swaps = useFoodSwaps(i18n.language as Lang);
  const state = useTwinState(pid, ladder);

  // Base meal: from the meal flow if there is one, else the person's largest recent evening meal.
  const base: MealInput = useMemo(() => {
    if (seed?.base) return seed.base;
    if (draft?.meal) return draft.meal;
    const meals = state.data?.history.meals ?? [];
    const evening = meals.filter((m) => new Date(m.t).getHours() >= 18);
    const pick = (evening.length ? evening : meals).reduce<(typeof meals)[number] | null>((a, m) => (!a || m.carbs > a.carbs ? m : a), null);
    if (pick) return { name: pick.name, carbs: pick.carbs, fibre: pick.fibre, protein: pick.protein, fat: pick.fat, minutes_from_now: 30 };
    return { ...FALLBACK_MEAL, name: t("whatif.usualDinner") };
  }, [seed, draft, state.data, t]);
  const fromPhoto = !!(seed?.base ?? draft?.meal) && !!draft;

  const init = seed?.scenario ?? {};
  const [swapKey, setSwapKey] = useState<string | null>(init.swap ? `${init.swap.from}>${init.swap.to}` : null);
  const [scale, setScale] = useState<number>(init.carb_scale ?? 1);
  const [walk, setWalk] = useState<number>(init.walk_min ?? 0);
  const [walkAfter, setWalkAfter] = useState<number>(init.walk_after_min ?? 10);
  const [shift, setShift] = useState<number>(init.shift_min ?? 0);

  const itemIds = new Set((base.items ?? []).map((i) => i.food_id));
  const availableSwaps = (swaps.data ?? []).filter((s) => itemIds.size === 0 || itemIds.has(s.from));
  const [allSwaps, setAllSwaps] = useState(false);
  const SWAP_PREVIEW = 6;
  const shownSwaps =
    allSwaps || availableSwaps.length <= SWAP_PREVIEW + 2
      ? availableSwaps
      : [
          ...availableSwaps.slice(0, SWAP_PREVIEW),
          // keep the selected swap visible even when the list is collapsed
          ...availableSwaps.slice(SWAP_PREVIEW).filter((x) => `${x.from}>${x.to}` === swapKey),
        ];

  const scenario: Scenario = useMemo(() => {
    const sc: Scenario = {};
    const parts: string[] = [];
    if (swapKey) {
      const [from, to] = swapKey.split(">");
      const sw = swaps.data?.find((s) => s.from === from && s.to === to);
      sc.swap = { from, to, from_qty: sw?.from_qty, to_qty: sw?.to_qty };
      parts.push(sw?.label_en ?? `${from} → ${to}`);
    }
    if (scale !== 1) {
      sc.carb_scale = scale;
      parts.push(`${Math.round(scale * 100)}% carbs`);
    }
    if (walk > 0) {
      sc.walk_min = walk;
      sc.walk_after_min = walkAfter;
      parts.push(`${walk}-min walk`);
    }
    if (shift !== 0) {
      sc.shift_min = shift;
      parts.push(`${shift > 0 ? "+" : ""}${shift} min`);
    }
    if (parts.length) sc.label = parts.join(", ");
    return sc;
  }, [swapKey, scale, walk, walkAfter, shift, swaps.data]);
  const changed = Object.keys(scenario).length > 0;

  const body = useDebounced(pid ? { ladder, base_meal: base, scenario } : null, 320);
  const q = useWhatIf(pid, body);
  const w = q.data;

  const reset = () => {
    setSwapKey(null);
    setScale(1);
    setWalk(0);
    setWalkAfter(10);
    setShift(0);
  };

  const pts = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v * 100))}`;
  const peak = w ? peakDelta(w) : { mean: 0, lo: null, hi: null };
  const [saved, setSaved] = useState<{ key: string; label: string; w: WhatIfResult }[]>([]);
  const resultRef = useRef<HTMLDivElement>(null);
  const describe = (): string => {
    const parts: string[] = [];
    if (swapKey) {
      const [from, to] = swapKey.split(">");
      const sw = swaps.data?.find((x) => x.from === from && x.to === to);
      parts.push(sw ? swapLabel(sw, i18n.language).text : `${from} → ${to}`);
    }
    if (scale !== 1) parts.push(t("whatif.portionValue", { pct: Math.round(scale * 100) }));
    if (walk > 0) parts.push(t("whatif.walkValue", { n: walk }));
    if (shift !== 0) parts.push(shift < 0 ? t("whatif.earlier", { n: -shift }) : t("whatif.later", { n: shift }));
    return parts.join(" + ");
  };
  const pin = () => {
    if (!w || saved.length >= MAX_SAVED) return;
    const key = JSON.stringify(scenario);
    if (saved.some((x) => x.key === key)) return;
    setSaved((ss) => [...ss, { key, label: describe(), w }]);
  };
  // A changed base meal makes saved comparisons meaningless.
  useEffect(() => setSaved([]), [pid, base.carbs, base.name]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader
        title={t("whatif.title")}
        subtitle={t("whatif.subtitle")}
        right={
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-paper-2 px-3.5 py-2 text-sm font-semibold">
              {fromPhoto && <span className="mr-1 text-marigold-ink">{t("whatif.fromPhoto")} ·</span>}
              {t("whatif.baseMeal", { name: base.name ? mealName(t, base.name) : t("whatif.usualDinner"), carbs: Math.round(base.carbs) })}
            </span>
            {changed && (
              <button type="button" className="btn-ghost h-10 min-h-0" onClick={reset}>
                <RotateCcw size={15} aria-hidden />
                {t("whatif.reset")}
              </button>
            )}
          </div>
        }
      />

      {/* Mobile: the result stays pinned while the controls are edited. */}
      {changed && (
        <div className="sticky top-16 z-20 -mx-4 mb-4 border-b border-night-line bg-night/95 px-4 py-2 text-moon backdrop-blur-md lg:hidden" aria-live="polite">
          {w ? (
            <p className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm">
              <span className="font-bold">{describe()}</span>
              {w.too_small_to_call ? (
                <span className="text-moon-2">{t("whatif.tooSmall")}</span>
              ) : (
                <span className="num text-moon-2">
                  {t("futures.peakShort", { d: signed(peak.mean) })} · {t("futures.riskShort", { d: pts(w.delta_p_high.mean) })}
                </span>
              )}
              {q.isFetching && <Loader2 size={13} className="animate-spin text-marigold" aria-hidden />}
            </p>
          ) : (
            <p className="text-sm text-moon-2">{t("whatif.computing")}</p>
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,400px)_1fr] xl:grid-cols-[minmax(0,440px)_1fr]">
        {/* ---------------- scenario controls ---------------- */}
        <div className="space-y-4" data-tour="whatif-cards">
          <p className="eyebrow text-ink-3">{t("whatif.groupFood")}</p>
          <ScenarioCard icon={<Repeat size={17} aria-hidden />} title={t("whatif.swapCard")} active={!!swapKey} value={swapKey ? "" : t("whatif.swapNone")}>
            <div className="flex flex-wrap gap-2">
              <Chip on={!swapKey} onClick={() => setSwapKey(null)}>
                {t("whatif.swapNone")}
              </Chip>
              {swaps.isLoading && <span className="skeleton h-9 w-40" />}
              {shownSwaps.map((s) => {
                const k = `${s.from}>${s.to}`;
                return (
                  <Chip key={k} on={swapKey === k} onClick={() => setSwapKey(k)}>
                    <span lang={swapLabel(s, i18n.language).english ? "en" : undefined}>{swapLabel(s, i18n.language).text}</span>
                  </Chip>
                );
              })}
              {availableSwaps.length > shownSwaps.length && (
                <button type="button" className="chip border-dashed border-ink-3/50 text-ink-2 hover:bg-paper-2" onClick={() => setAllSwaps(true)}>
                  {t("whatif.showAllSwaps", { n: availableSwaps.length })}
                </button>
              )}
              {allSwaps && availableSwaps.length > SWAP_PREVIEW + 2 && (
                <button type="button" className="chip border-dashed border-ink-3/50 text-ink-2 hover:bg-paper-2" onClick={() => setAllSwaps(false)}>
                  {t("whatif.showFewerSwaps")}
                </button>
              )}
            </div>
            {itemIds.size === 0 && <p className="mt-3 text-xs text-ink-3">{t("whatif.swapHint")}</p>}
          </ScenarioCard>

          <ScenarioCard icon={<Scale size={17} aria-hidden />} title={t("whatif.portionCard")} active={scale !== 1} value={t("whatif.portionValue", { pct: Math.round(scale * 100) })}>
            <label htmlFor="portion" className="sr-only">
              {t("whatif.portionCard")}
            </label>
            <input
              id="portion"
              type="range"
              min={0.25}
              max={1.5}
              step={0.05}
              value={scale}
              onChange={(e) => setScale(Number(e.target.value))}
              aria-valuetext={t("whatif.portionValue", { pct: Math.round(scale * 100) })}
              className="h-11 w-full cursor-pointer accent-[rgb(var(--marigold-ink))]"
            />
            <div className="mt-1 flex flex-wrap gap-2">
              {[0.5, 0.75, 1, 1.25].map((v) => (
                <Chip key={v} on={scale === v} onClick={() => setScale(v)}>
                  <span className="num">{Math.round(v * 100)}%</span>
                </Chip>
              ))}
            </div>
          </ScenarioCard>

          <p className="eyebrow pt-2 text-ink-3">{t("whatif.groupActivity")}</p>
          <ScenarioCard icon={<Footprints size={17} aria-hidden />} title={t("whatif.walkCard")} active={walk > 0} value={walk ? t("whatif.walkValue", { n: walk }) : t("whatif.walkNone")}>
            <div className="flex flex-wrap gap-2">
              {[0, 10, 15, 20, 30].map((v) => (
                <Chip key={v} on={walk === v} onClick={() => setWalk(v)}>
                  {v === 0 ? t("whatif.walkNone") : t("common.minutesShort", { n: v })}
                </Chip>
              ))}
            </div>
            {walk > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {[0, 10, 30].map((v) => (
                  <Chip key={v} on={walkAfter === v} onClick={() => setWalkAfter(v)}>
                    {t("whatif.walkAfter", { n: v })}
                  </Chip>
                ))}
              </div>
            )}
          </ScenarioCard>

          <p className="eyebrow pt-2 text-ink-3">{t("whatif.groupTiming")}</p>
          <ScenarioCard
            icon={<Clock size={17} aria-hidden />}
            title={t("whatif.timingCard")}
            active={shift !== 0}
            value={shift === 0 ? t("whatif.same") : shift < 0 ? t("whatif.earlier", { n: -shift }) : t("whatif.later", { n: shift })}
          >
            <div className="flex flex-wrap gap-2">
              {[-60, -30, 0, 30, 60].map((v) => (
                <Chip key={v} on={shift === v} onClick={() => setShift(v)}>
                  {v === 0 ? t("whatif.same") : v < 0 ? t("whatif.earlier", { n: -v }) : t("whatif.later", { n: v })}
                </Chip>
              ))}
            </div>
          </ScenarioCard>
        </div>

        {/* ---------------- curves + result (sticky beside the controls) ---------------- */}
        <div className="order-first lg:order-none lg:sticky lg:top-20 lg:self-start" ref={resultRef}>
          <section className="stage on-night rounded-4xl p-4 sm:p-5" aria-labelledby="wi-chart">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id="wi-chart" className="text-lg font-bold text-moon">
                {changed ? t("futures.title") : t("whatif.baseline")}
              </h2>
              <div className="flex items-center gap-2">
                {q.isFetching && <Loader2 size={14} className="animate-spin text-marigold" aria-label={t("whatif.computing")} />}
                <SimulationLabel />
              </div>
            </div>
            <div className="mt-2">
              {w ? (
                <CompareChart
                  baseline={w.baseline}
                  scenario={changed ? w.scenario : null}
                  pending={q.isFetching}
                  baselineLabel={t("whatif.baseline")}
                  scenarioLabel={t("whatif.scenario")}
                  pinned={saved.map((x, i) => ({ key: x.key, label: x.label, forecast: x.w.scenario, color: PIN_COLORS[i % PIN_COLORS.length] }))}
                />
              ) : q.isError ? (
                <ErrorState tone="night" message={t("errors.generic")} onRetry={() => void q.refetch()} />
              ) : (
                <div className="skeleton-night h-[240px] sm:h-[320px]" aria-busy="true" />
              )}
            </div>
            <p className="mt-1 text-xs text-moon-2">{t("whatif.caption")}</p>

            <div className="mt-3" aria-live="polite">
              {!changed ? (
                <p className="stage-card p-4 text-sm text-moon-2">{t("whatif.noChange")}</p>
              ) : w ? (
                <div className="stage-card grid gap-3 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
                  {w.too_small_to_call ? (
                    <div className="sm:col-span-2">
                      <p className="inline-flex items-center gap-2 text-xl font-extrabold text-moon">
                        <Scale3d size={18} className="text-moon-3" aria-hidden />
                        {t("whatif.tooSmall")}
                      </p>
                      <p className="text-sm text-moon-2">{t("whatif.tooSmallBody")}</p>
                      <p className="num mt-1 text-xs text-moon-3">{t("whatif.interval", { lo: pts(w.delta_p_high.lo), hi: pts(w.delta_p_high.hi) })}</p>
                    </div>
                  ) : (
                    <>
                      <div>
                        <p className="eyebrow text-moon-3">{t("futures.peakLabel")}</p>
                        <p className={`num text-2xl font-extrabold ${peak.mean < 0 ? "text-teal" : "text-coral-night"}`}>
                          {signed(peak.mean)} <span className="text-sm font-semibold text-moon-2">{t("common.mgdl")}</span>
                        </p>
                        {peak.lo !== null && peak.hi !== null && <p className="num text-xs text-moon-3">{t("futures.peakInterval", { lo: signed(peak.lo), hi: signed(peak.hi) })}</p>}
                      </div>
                      <div>
                        <p className="eyebrow text-moon-3">{t("futures.riskLabel")}</p>
                        <p className={`num text-2xl font-extrabold ${w.delta_p_high.mean < 0 ? "text-teal" : "text-coral-night"}`}>
                          {pts(w.delta_p_high.mean)} <span className="text-sm font-semibold text-moon-2">{t("futures.points")}</span>
                        </p>
                        <p className="num text-xs text-moon-3">{t("whatif.interval", { lo: pts(w.delta_p_high.lo), hi: pts(w.delta_p_high.hi) })}</p>
                      </div>
                    </>
                  )}
                  <div className="flex flex-wrap gap-2 sm:justify-end">
                    <button type="button" className="btn-night h-10 min-h-0 px-3 text-sm" disabled={saved.length >= MAX_SAVED || q.isFetching} onClick={pin}>
                      <Pin size={15} aria-hidden />
                      {t("whatif.pin")}
                    </button>
                    <button type="button" className="btn-night h-10 min-h-0 px-3 text-sm" onClick={() => openWhy(w.scenario.forecast_id, undefined, undefined, async () => (await q.refetch()).data?.scenario.forecast_id ?? null)}>
                      <HelpCircle size={15} aria-hidden />
                      {t("common.why")}
                    </button>
                  </div>
                  {saved.length >= MAX_SAVED && <p className="text-xs text-moon-3 sm:col-span-3">{t("whatif.maxSaved", { n: MAX_SAVED })}</p>}
                </div>
              ) : null}
            </div>

            {saved.length > 0 && (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[420px] border-separate border-spacing-0 text-left text-sm text-moon">
                  <caption className="sr-only">{t("whatif.compareTitle")}</caption>
                  <thead>
                    <tr className="text-xs text-moon-3">
                      <th scope="col" className="px-2 py-1.5 font-semibold">{t("whatif.compareTitle")}</th>
                      <th scope="col" className="px-2 py-1.5 font-semibold">{t("futures.peakLabel")}</th>
                      <th scope="col" className="px-2 py-1.5 font-semibold">{t("futures.riskLabel")}</th>
                      <th scope="col" className="px-2 py-1.5"><span className="sr-only">{t("common.remove")}</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {saved.map((x, i) => {
                      const pk = peakDelta(x.w);
                      return (
                        <tr key={x.key} className="border-t border-night-line">
                          <th scope="row" className="px-2 py-1.5 font-semibold">
                            <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: PIN_COLORS[i % PIN_COLORS.length] }} aria-hidden />
                            {x.label}
                          </th>
                          <td className="num px-2 py-1.5">{x.w.too_small_to_call ? t("whatif.tooSmall") : `${signed(pk.mean)} ${t("common.mgdl")}`}</td>
                          <td className="num px-2 py-1.5">
                            {pts(x.w.delta_p_high.mean)} <span className="text-xs text-moon-3">({pts(x.w.delta_p_high.lo)} … {pts(x.w.delta_p_high.hi)})</span>
                          </td>
                          <td className="px-2 py-1.5 text-right">
                            <button type="button" onClick={() => setSaved((ss) => ss.filter((y) => y.key !== x.key))} className="rounded-full p-1.5 text-moon-3 hover:bg-night-3 hover:text-moon" aria-label={`${t("common.remove")}: ${x.label}`}>
                              <X size={14} aria-hidden />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
