import type { TFunction } from "i18next";
import type { ReplayClock, TwinState } from "@/api/types";
import { formatClock, parseTime } from "./format";

/** The replay clock of a state, or a fallback built from state.now when the state has none. */
export function replayOf(state: Pick<TwinState, "now" | "replay"> | null | undefined): ReplayClock | null {
  if (!state) return null;
  if (state.replay) return state.replay;
  return null;
}

/** Localised replay label: "Replay · day 7 · 7:30 pm". Never confused with the wall clock. */
export function replayLabel(t: TFunction, lang: string, replay: ReplayClock | null, fallbackNow?: string): string {
  if (replay) return t("replay.label", { day: replay.day, time: formatClock(replay.now, lang) });
  if (fallbackNow) return t("replay.labelNoDay", { time: formatClock(fallbackNow, lang) });
  return t("replay.title");
}

/** Minutes left on the replay before the clock reaches its end. */
export function replayRemaining(replay: ReplayClock | null): number {
  if (!replay) return 0;
  return Math.max(0, replay.max_offset_min - replay.offset_min);
}

/** Can the clock still advance by `minutes`? */
export function canAdvance(replay: ReplayClock | null, minutes: number): boolean {
  if (!replay) return false;
  return replay.offset_min + minutes <= replay.max_offset_min;
}

/** Minutes between two contract times (b - a). */
export function minutesBetween(a: string, b: string): number {
  return Math.round((parseTime(b).getTime() - parseTime(a).getTime()) / 60_000);
}

/** ISO local time (no offset suffix) for `minutesAgo` before a replay now. */
export function isoMinusMinutes(nowIso: string, minutesAgo: number): string {
  const d = new Date(parseTime(nowIso).getTime() - minutesAgo * 60_000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:00`;
}
