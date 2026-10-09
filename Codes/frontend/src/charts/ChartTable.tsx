import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TwinState } from "@/api/types";
import { formatClock, mealName, parseTime } from "@/lib/format";
import type { Futures } from "./GlucoseRiver";
import { nearestIndex, toPoints, validatedHorizon } from "./util";

/**
 * Text equivalent of the glucose river for keyboard and screen-reader users: one row every 30
 * minutes with the twin's most likely value, its 90% band, the scenario (if any) and the events.
 */
export function ChartTable({ state, futures, rangeHours = 12 }: { state: TwinState; futures?: Futures | null; rangeHours?: number }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const rows = useMemo(() => {
    const now = parseTime(state.now).getTime();
    const past = toPoints(state.history.virtual_cgm);
    const main = toPoints((futures?.baseline ?? state.forecast)?.traj);
    const scen = toPoints(futures?.scenario?.traj);
    const vh = now + validatedHorizon(futures?.baseline ?? state.forecast) * 60_000;
    const start = now - rangeHours * 3600_000;
    const end = main.length ? main[main.length - 1].t : now;
    const out: { t: number; phase: "past" | "forecast" | "exploratory"; q50: number; q05: number; q95: number; s?: { q50: number; q05: number; q95: number }; events: string[] }[] = [];
    const step = 30 * 60_000;
    for (let tt = Math.ceil(start / step) * step; tt <= end; tt += step) {
      const src = tt <= now ? past : main;
      if (!src.length) continue;
      const p = src[nearestIndex(src, tt)];
      if (Math.abs(p.t - tt) > 20 * 60_000) continue;
      const events: string[] = [];
      for (const r of state.history.readings ?? []) {
        const rt = parseTime(r.t).getTime();
        if (r.kind !== "cgm" && Math.abs(rt - tt) < 15 * 60_000) events.push(`${t(r.kind === "lab" ? "stage.lab" : "stage.fingerprick")} ${Math.round(r.value)}`);
      }
      for (const m of state.history.meals ?? []) {
        const mt = parseTime(m.t).getTime();
        if (Math.abs(mt - tt) < 15 * 60_000) events.push(`${mealName(t, m.name)} (${t("stage.carbsG", { n: Math.round(m.carbs) })})`);
      }
      const sp = tt > now && scen.length ? scen[nearestIndex(scen, tt)] : undefined;
      out.push({
        t: tt,
        phase: tt <= now ? "past" : tt > vh ? "exploratory" : "forecast",
        q50: p.q50,
        q05: p.q05,
        q95: p.q95,
        s: sp ? { q50: sp.q50, q05: sp.q05, q95: sp.q95 } : undefined,
        events,
      });
    }
    return out;
  }, [state, futures, rangeHours, t]);

  const hasScenario = !!futures?.scenario;
  return (
    <div className="max-h-80 overflow-auto rounded-2xl border border-night-line/60" tabIndex={0} role="region" aria-label={t("chartTable.title")}>
      <table className="w-full min-w-[420px] border-separate border-spacing-0 text-left text-xs text-moon">
        <caption className="sr-only">{t("chartTable.caption")}</caption>
        <thead className="sticky top-0 bg-night-2">
          <tr className="text-moon-2">
            <th scope="col" className="px-3 py-2 font-semibold">{t("chartTable.time")}</th>
            <th scope="col" className="px-3 py-2 font-semibold">{t("chartTable.phase")}</th>
            <th scope="col" className="px-3 py-2 font-semibold">{hasScenario ? futures?.baselineLabel : t("stage.median")}</th>
            {hasScenario && <th scope="col" className="px-3 py-2 font-semibold">{futures?.scenarioLabel}</th>}
            <th scope="col" className="px-3 py-2 font-semibold">{t("chartTable.events")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.t} className="odd:bg-night-2/40">
              <th scope="row" className="num px-3 py-1.5 font-semibold">{formatClock(new Date(r.t), lang)}</th>
              <td className="px-3 py-1.5 text-moon-2">{t(`chartTable.${r.phase}`)}</td>
              <td className="num px-3 py-1.5">
                {Math.round(r.q50)} <span className="text-moon-3">({Math.round(r.q05)}–{Math.round(r.q95)})</span>
              </td>
              {hasScenario && (
                <td className="num px-3 py-1.5">
                  {r.s ? (
                    <>
                      {Math.round(r.s.q50)} <span className="text-moon-3">({Math.round(r.s.q05)}–{Math.round(r.s.q95)})</span>
                    </>
                  ) : (
                    "—"
                  )}
                </td>
              )}
              <td className="px-3 py-1.5 text-moon-2">{r.events.join(" · ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
