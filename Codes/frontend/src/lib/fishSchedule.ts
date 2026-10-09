/**
 * Scheduling for the decorative blue clownfish (src/components/ClownfishLayer.tsx). Pure and
 * timer-injectable so it can be unit-tested. The fish carries no meaning: it never reflects
 * glucose, risk, confidence, safety or model activity, and it is never shown while anything
 * clinically important (a safety alert) is on screen.
 */

export const MIN_GAP_MS = 45_000;
export const MAX_GAP_MS = 90_000;
export const MIN_PASS_MS = 5_000;
export const MAX_PASS_MS = 8_000;
/** About one pass in four is a small school. */
export const SCHOOL_CHANCE = 0.25;
/** Element budget: never more than three animated fish. */
export const MAX_FISH = 3;

export type Rand = () => number;

const clamp01 = (x: number) => (Number.isFinite(x) ? Math.min(1, Math.max(0, x)) : 0);

/** Wait before the next pass: 45–90 s. */
export const nextGapMs = (rand: Rand) => Math.round(MIN_GAP_MS + clamp01(rand()) * (MAX_GAP_MS - MIN_GAP_MS));

/** Length of one pass: 5–8 s. */
export const passDurationMs = (rand: Rand) => Math.round(MIN_PASS_MS + clamp01(rand()) * (MAX_PASS_MS - MIN_PASS_MS));

/** One fish usually; a school of 2 or 3 about one pass in four. */
export function schoolSize(rand: Rand): 1 | 2 | 3 {
  if (clamp01(rand()) >= SCHOOL_CHANCE) return 1;
  return clamp01(rand()) < 0.5 ? 2 : 3;
}

export interface FishSpec {
  /** Start delay inside the pass (ms). */
  delayMs: number;
  /** Vertical position inside the band, 0 (top) .. 1 (bottom). */
  lane: number;
  /** Relative size 0.75 .. 1. */
  scale: number;
}
export interface PassPlan {
  durationMs: number;
  direction: "ltr" | "rtl";
  fish: FishSpec[];
}

/** A complete pass: all fish finish inside 8 s (each school member starts at most 600 ms later). */
export function planPass(rand: Rand): PassPlan {
  const n = schoolSize(rand);
  const durationMs = passDurationMs(rand);
  const direction = clamp01(rand()) < 0.5 ? "ltr" : "rtl";
  const fish: FishSpec[] = [];
  for (let i = 0; i < Math.min(n, MAX_FISH); i++) {
    fish.push({
      delayMs: i === 0 ? 0 : Math.round(150 + clamp01(rand()) * 450),
      lane: i === 0 ? 0.5 : Math.round((0.2 + clamp01(rand()) * 0.6) * 100) / 100,
      scale: i === 0 ? 1 : Math.round((0.75 + clamp01(rand()) * 0.2) * 100) / 100,
    });
  }
  // Keep the whole pass within the 5–8 s budget including the school's start offsets.
  const lastStart = Math.max(...fish.map((f) => f.delayMs));
  return { durationMs: Math.max(MIN_PASS_MS, Math.min(durationMs, MAX_PASS_MS - lastStart)), direction, fish };
}

/** Everything that can switch the fish off. Any single reason is enough. */
export interface FishConditions {
  /** Profile setting "Background fish animation". */
  userEnabled: boolean;
  /** GET /api/capabilities features.fish.enabled (true when the backend does not say). */
  backendEnabled: boolean;
  reducedMotion: boolean;
  /** A safety alert is on screen. */
  safetyAlert: boolean;
  /** Presentation mode or a report / print view. */
  presentationOrReport: boolean;
  /** document.hidden */
  hidden: boolean;
  /** Viewport narrower than 768 px. */
  smallScreen: boolean;
  /** navigator.hardwareConcurrency <= 2 or data saver on. */
  constrained: boolean;
}

export function fishAllowed(c: FishConditions): boolean {
  return c.userEnabled && c.backendEnabled && !c.reducedMotion && !c.safetyAlert && !c.presentationOrReport && !c.hidden && !c.smallScreen && !c.constrained;
}

/** Low-power heuristics: two or fewer logical cores, or the browser's data saver. */
export function isConstrainedDevice(nav: { hardwareConcurrency?: number; connection?: { saveData?: boolean } } | undefined): boolean {
  if (!nav) return false;
  const cores = nav.hardwareConcurrency;
  if (typeof cores === "number" && cores > 0 && cores <= 2) return true;
  return !!nav.connection?.saveData;
}

type TimerFns = {
  setTimeout: (fn: () => void, ms: number) => unknown;
  clearTimeout: (id: unknown) => void;
};

/**
 * Runs passes every 45–90 s while active. pause() cancels the pending timer (tab hidden, alert,
 * setting off); resume() starts a fresh 45–90 s wait. stop() cleans up for good (unmount).
 */
export function createFishScheduler(opts: { rand: Rand; onPass: (p: PassPlan) => void; timers?: TimerFns }) {
  const timers: TimerFns = opts.timers ?? {
    setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
    clearTimeout: (id) => globalThis.clearTimeout(id as ReturnType<typeof setTimeout>),
  };
  let pending: unknown = null;
  let running = false;
  let stopped = false;

  const clear = () => {
    if (pending !== null) timers.clearTimeout(pending);
    pending = null;
  };
  const schedule = () => {
    clear();
    if (!running || stopped) return;
    pending = timers.setTimeout(() => {
      pending = null;
      if (!running || stopped) return;
      opts.onPass(planPass(opts.rand));
      schedule();
    }, nextGapMs(opts.rand));
  };

  return {
    resume() {
      if (stopped || running) return;
      running = true;
      schedule();
    },
    pause() {
      running = false;
      clear();
    },
    stop() {
      stopped = true;
      running = false;
      clear();
    },
    get active() {
      return running && !stopped;
    },
    get hasPendingTimer() {
      return pending !== null;
    },
  };
}
