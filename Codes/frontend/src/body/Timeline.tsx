import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Pause, Play, SkipForward, UtensilsCrossed } from "lucide-react";
import { formatClock } from "@/lib/format";
import { N_STEPS, glucoseColor, isExploratory, lastValidatedIndex, minutesAt, rgbCss } from "@/lib/body";

/**
 * Scrubber from now to +4 h (49 steps of 5 min) with Play/Pause. The part beyond the validated
 * 2 h is shaded and labelled exploratory. A glucose ribbon (q50, coloured by range) runs along it.
 */
export function Timeline({
  times,
  idx,
  onIdx,
  playing,
  onTogglePlay,
  reducedMotion,
  validatedMin,
  mealIdx,
  blood,
  presentation,
}: {
  times: string[];
  idx: number;
  onIdx: (i: number) => void;
  playing: boolean;
  onTogglePlay: () => void;
  reducedMotion: boolean;
  validatedMin: number;
  mealIdx: number | null;
  blood: number[];
  presentation: boolean;
}) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const n = Math.min(N_STEPS, times.length - 1);
  const vIdx = lastValidatedIndex(validatedMin, n);
  const pctAt = (i: number) => (i / n) * 100;
  const clock = (i: number) => formatClock(times[i] ?? times[0], i18n.language);
  const rel = (i: number) => (i === 0 ? t("body.time.now") : t("body.time.plusMin", { n: minutesAt(i) }));
  const explo = isExploratory(idx, validatedMin);
  const gradient = blood.length
    ? `linear-gradient(90deg, ${blood
        .filter((_, i) => i % 4 === 0 || i === blood.length - 1)
        .map((g, k, arr) => `${rgbCss(glucoseColor(g), 0.85)} ${((k / Math.max(1, arr.length - 1)) * 100).toFixed(1)}%`)
        .join(", ")})`
    : undefined;
  return (
    <div className="flex items-center gap-2.5 sm:gap-3" data-body-timeline>
      <button
        type="button"
        onClick={onTogglePlay}
        className="btn-marigold h-11 w-11 min-h-0 shrink-0 px-0"
        aria-label={reducedMotion ? t("body.time.step") : playing ? t("body.time.pause") : t("body.time.play")}
        title={reducedMotion ? t("body.time.step") : playing ? t("body.time.pause") : t("body.time.play")}
        data-body-play
      >
        {reducedMotion ? <SkipForward size={18} aria-hidden /> : playing ? <Pause size={18} aria-hidden /> : <Play size={18} aria-hidden />}
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <label htmlFor={id} className={`num font-bold text-moon ${presentation ? "text-base" : "text-sm"}`}>
            {clock(idx)} <span className="font-semibold text-moon-2">· {rel(idx)}</span>
          </label>
          <span className={`inline-flex items-center gap-1.5 text-[0.7rem] font-semibold ${explo ? "text-moon" : "text-moon-3"}`} data-body-exploratory={explo ? "on" : "off"}>
            <span
              className="inline-block h-2.5 w-4 rounded-sm border border-moon-3/60"
              style={{ background: "repeating-linear-gradient(45deg, rgb(150 157 208 / 0.6) 0 2px, transparent 2px 4px)" }}
              aria-hidden
            />
            {t("body.time.exploratory")}
          </span>
        </div>
        <div className="relative mt-1.5 h-9">
          {/* track: glucose ribbon + exploratory shading */}
          <div className="absolute inset-x-0 top-1/2 h-2.5 -translate-y-1/2 overflow-hidden rounded-full bg-night-3">
            <div className="absolute inset-0 opacity-80" style={{ background: gradient }} aria-hidden />
            <div
              className="absolute inset-y-0 right-0"
              style={{
                left: `${pctAt(vIdx)}%`,
                background: "repeating-linear-gradient(45deg, rgb(var(--night) / 0.62) 0 4px, rgb(var(--night) / 0.35) 4px 8px)",
              }}
              aria-hidden
            />
          </div>
          <span className="pointer-events-none absolute top-0 h-full w-px bg-moon-3/70" style={{ left: `${pctAt(vIdx)}%` }} aria-hidden />
          {mealIdx !== null && (
            <span
              className="pointer-events-none absolute -top-1 flex -translate-x-1/2 items-center justify-center rounded-full bg-marigold p-0.5 text-night shadow"
              style={{ left: `${pctAt(mealIdx)}%` }}
              title={t("body.time.meal")}
              data-body-meal-marker
            >
              <UtensilsCrossed size={11} aria-hidden />
            </span>
          )}
          <input
            id={id}
            type="range"
            min={0}
            max={n}
            step={1}
            value={idx}
            onChange={(e) => onIdx(Number(e.target.value))}
            aria-valuetext={`${clock(idx)}, ${rel(idx)}${explo ? `, ${t("body.time.exploratory")}` : ""}`}
            className="body-range absolute inset-0 h-full w-full cursor-pointer"
            data-body-scrubber
          />
        </div>
        <div className="relative h-4 text-[0.68rem] text-moon-3">
          {[0, 12, 24, 36, 48].map((i) => (
            <span key={i} className="num absolute top-0 whitespace-nowrap" style={{ left: `${pctAt(i)}%`, transform: i === 0 ? "none" : i === n ? "translateX(-100%)" : "translateX(-50%)" }}>
              {i === 0 ? t("body.time.now") : t("body.time.plusH", { n: i / 12 })}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
