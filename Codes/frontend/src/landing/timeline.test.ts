import { describe, expect, it } from "vitest";
import { CYCLE, FISH_KEYS, R_MAX, REVEAL_CENTER, STILL_AT, T_BACK, T_GROW, T_HIT, T_SHRINK, fishOpacity, fishParam, loopTime, pulseAt, revealAt, twinAmount } from "./timeline";

describe("sign-in animation timeline", () => {
  it("stays dressed until the fish reaches the heart, then reveals the twin and folds back", () => {
    expect(revealAt(0)).toBe(0);
    expect(revealAt(T_HIT - 0.01)).toBe(0);
    expect(revealAt(T_HIT + 0.01)).toBeGreaterThan(0);
    expect(revealAt(T_HIT + T_GROW + 0.1)).toBe(R_MAX);
    expect(revealAt(T_BACK - 0.1)).toBe(R_MAX);
    expect(revealAt(T_BACK + T_SHRINK + 0.1)).toBe(0);
    expect(revealAt(CYCLE + T_HIT + T_GROW + 0.1)).toBe(R_MAX); // loops
  });

  it("grows and shrinks monotonically (no flicker at the dissolve front)", () => {
    let prev = 0;
    for (let c = T_HIT; c <= T_HIT + T_GROW; c += 0.05) {
      const r = revealAt(c);
      expect(r).toBeGreaterThanOrEqual(prev);
      prev = r;
    }
    prev = R_MAX;
    for (let c = T_BACK; c <= T_BACK + T_SHRINK; c += 0.05) {
      const r = revealAt(c);
      expect(r).toBeLessThanOrEqual(prev + 1e-9);
      prev = r;
    }
  });

  it("the fish is inside the heart exactly when the dissolve starts", () => {
    const hit = FISH_KEYS.find((k) => k[0] === T_HIT);
    expect(hit).toBeDefined();
    const [, x, y, z] = hit!;
    expect(Math.hypot(x - REVEAL_CENTER[0], y - REVEAL_CENTER[1], z - REVEAL_CENTER[2])).toBeLessThan(0.05);
    expect(pulseAt(T_HIT)).toBeCloseTo(0, 9);
    expect(pulseAt(T_HIT - 0.1)).toBeNull();
  });

  it("keyframes cover one loop in order and the fish is invisible at the seam", () => {
    expect(FISH_KEYS[0][0]).toBe(0);
    expect(FISH_KEYS[FISH_KEYS.length - 1][0]).toBe(CYCLE);
    for (let i = 1; i < FISH_KEYS.length; i++) expect(FISH_KEYS[i][0]).toBeGreaterThan(FISH_KEYS[i - 1][0]);
    expect(fishOpacity(0)).toBe(0);
    expect(fishOpacity(CYCLE - 1e-6)).toBeLessThan(1e-3);
    expect(fishOpacity(T_HIT)).toBe(1);
    expect(fishParam(0)).toBe(0);
    expect(fishParam(CYCLE / 2)).toBeGreaterThan(0);
    expect(fishParam(CYCLE - 1e-6)).toBeCloseTo(1, 3);
  });

  it("the reduced-motion still shows half person, half twin", () => {
    const a = twinAmount(STILL_AT);
    expect(a).toBeGreaterThan(0.25);
    expect(a).toBeLessThan(0.75);
    expect(loopTime(-1)).toBeCloseTo(CYCLE - 1);
  });
});
