import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  MAX_FISH,
  MAX_GAP_MS,
  MAX_PASS_MS,
  MIN_GAP_MS,
  MIN_PASS_MS,
  createFishScheduler,
  fishAllowed,
  isConstrainedDevice,
  nextGapMs,
  passDurationMs,
  planPass,
  schoolSize,
  type FishConditions,
} from "./fishSchedule";

/** Deterministic pseudo-random sequence (mulberry32). */
function seeded(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const constant = (v: number) => () => v;

describe("fish timing", () => {
  it("waits 45–90 s between passes", () => {
    expect(nextGapMs(constant(0))).toBe(MIN_GAP_MS);
    expect(nextGapMs(constant(0.999999))).toBeLessThanOrEqual(MAX_GAP_MS);
    const r = seeded(1);
    for (let i = 0; i < 500; i++) {
      const g = nextGapMs(r);
      expect(g).toBeGreaterThanOrEqual(45_000);
      expect(g).toBeLessThanOrEqual(90_000);
    }
  });
  it("each pass lasts 5–8 s including school offsets", () => {
    expect(passDurationMs(constant(0))).toBe(MIN_PASS_MS);
    expect(passDurationMs(constant(1))).toBe(MAX_PASS_MS);
    const r = seeded(7);
    for (let i = 0; i < 500; i++) {
      const p = planPass(r);
      const end = Math.max(...p.fish.map((f) => f.delayMs)) + p.durationMs;
      expect(p.durationMs).toBeGreaterThanOrEqual(5_000);
      expect(end).toBeLessThanOrEqual(8_000);
      expect(p.fish.length).toBeGreaterThanOrEqual(1);
      expect(p.fish.length).toBeLessThanOrEqual(MAX_FISH);
      for (const f of p.fish) {
        expect(f.lane).toBeGreaterThanOrEqual(0);
        expect(f.lane).toBeLessThanOrEqual(1);
      }
    }
  });
  it("shows a school of 2–3 about one pass in four", () => {
    expect(schoolSize(constant(0.9))).toBe(1);
    const r = seeded(42);
    let schools = 0;
    const N = 4000;
    for (let i = 0; i < N; i++) {
      const n = schoolSize(r);
      expect([1, 2, 3]).toContain(n);
      if (n > 1) schools += 1;
    }
    expect(schools / N).toBeGreaterThan(0.2);
    expect(schools / N).toBeLessThan(0.3);
  });
});

describe("when the fish may appear", () => {
  const on: FishConditions = {
    userEnabled: true,
    backendEnabled: true,
    reducedMotion: false,
    safetyAlert: false,
    presentationOrReport: false,
    hidden: false,
    smallScreen: false,
    constrained: false,
  };
  it("is allowed only when nothing switches it off", () => {
    expect(fishAllowed(on)).toBe(true);
    for (const k of Object.keys(on) as (keyof FishConditions)[]) {
      const flipped = { ...on, [k]: !on[k] };
      expect(fishAllowed(flipped), k).toBe(false);
    }
  });
  it("detects constrained devices", () => {
    expect(isConstrainedDevice({ hardwareConcurrency: 2 })).toBe(true);
    expect(isConstrainedDevice({ hardwareConcurrency: 8, connection: { saveData: true } })).toBe(true);
    expect(isConstrainedDevice({ hardwareConcurrency: 8 })).toBe(false);
    expect(isConstrainedDevice({})).toBe(false);
    expect(isConstrainedDevice(undefined)).toBe(false);
  });
});

describe("scheduler", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("runs a pass after 45–90 s, then schedules the next", () => {
    const passes: number[] = [];
    const s = createFishScheduler({ rand: constant(0), onPass: (p) => passes.push(p.fish.length) });
    s.resume();
    vi.advanceTimersByTime(44_999);
    expect(passes).toHaveLength(0);
    vi.advanceTimersByTime(1);
    expect(passes).toHaveLength(1);
    vi.advanceTimersByTime(45_000);
    expect(passes).toHaveLength(2);
    s.stop();
  });
  it("pauses (tab hidden) without leaving a timer, and resumes", () => {
    const onPass = vi.fn();
    const s = createFishScheduler({ rand: constant(0), onPass });
    s.resume();
    vi.advanceTimersByTime(30_000);
    s.pause();
    expect(s.hasPendingTimer).toBe(false);
    vi.advanceTimersByTime(200_000);
    expect(onPass).not.toHaveBeenCalled();
    s.resume();
    vi.advanceTimersByTime(45_000);
    expect(onPass).toHaveBeenCalledTimes(1);
    s.stop();
  });
  it("stop() is final and clears every timer (unmount / navigation)", () => {
    const onPass = vi.fn();
    const s = createFishScheduler({ rand: constant(0), onPass });
    s.resume();
    s.stop();
    s.resume();
    expect(s.active).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(500_000);
    expect(onPass).not.toHaveBeenCalled();
  });
});
