// Choreography of the sign-in page animation (pure numbers, no three.js, unit-tested).
// One loop: a clothed person revolves; a clownfish of light swims in, circles him and passes
// through his heart; from there the clothes dissolve and reveal the glass digital twin, which
// later folds back into the person.

export const CYCLE = 22; // seconds per loop
export const T_HIT = 7.6; // the fish is at the heart
export const T_GROW = 4.2; // dissolve: person -> twin
export const T_BACK = 18.0; // twin folds back into the person
export const T_SHRINK = 3.2;
export const R_MAX = 1.42; // reveal radius (m) that covers the whole body from the heart
export const REVEAL_CENTER: [number, number, number] = [0.0, 1.25, 0.02];
/** Where the loop starts when the first frame is on screen: the fish is about to reach the heart, so the
 * statue starts turning into the twin one second after the page appears. */
export const START_AT = T_HIT - 1.0;
/** The still frame shown when the visitor prefers reduced motion: half person, half twin. */
export const STILL_AT = T_HIT + 1.7;

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const easeInOut = (u: number) => {
  const x = clamp01(u);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};
/** Gentle at both ends, nearly constant speed in between (the front sweeps the body evenly). */
const easeSine = (u: number) => 0.5 - 0.5 * Math.cos(Math.PI * clamp01(u));

export const loopTime = (t: number) => ((t % CYCLE) + CYCLE) % CYCLE;

/** Radius (m) of the dissolve front around the heart: 0 = fully dressed, R_MAX = fully twin. */
export function revealAt(t: number): number {
  const c = loopTime(t);
  if (c < T_HIT) return 0;
  if (c < T_HIT + T_GROW) return 0.06 + (R_MAX - 0.06) * easeSine((c - T_HIT) / T_GROW);
  if (c < T_BACK) return R_MAX;
  if (c < T_BACK + T_SHRINK) return R_MAX * (1 - easeSine((c - T_BACK) / T_SHRINK));
  return 0;
}

/** 0..1 how much of the twin is showing (drives organ glow, aura and floor colour). */
export const twinAmount = (t: number) => clamp01(revealAt(t) / R_MAX);

/** 0..1 progress of the light pulse that leaves the heart when the fish passes through. */
export function pulseAt(t: number): number | null {
  const c = loopTime(t) - T_HIT;
  return c >= 0 && c < 1.6 ? c / 1.6 : null;
}

/**
 * Fish keyframes [time, x, y, z] in metres around the body (x right, y up, z toward the viewer).
 * It appears far behind the body, circles it, enters the chest from behind at T_HIT, comes out
 * toward the viewer, swims a lap around the twin and swims back into the distance.
 */
export const FISH_KEYS: [number, number, number, number][] = [
  [0.0, 0.75, 2.05, -3.2],
  [1.5, 0.38, 1.72, -1.45],
  [2.8, -0.46, 1.46, -0.38],
  [3.8, -0.56, 1.3, 0.45],
  [4.8, 0.08, 1.14, 0.72],
  [5.7, 0.6, 1.24, 0.16],
  [6.5, 0.42, 1.36, -0.46],
  [7.1, -0.1, 1.29, -0.44],
  [T_HIT, 0.0, 1.25, 0.0],
  [8.2, 0.18, 1.3, 0.56],
  [9.2, 0.56, 1.62, 0.48],
  [10.4, 0.24, 1.92, -0.22],
  [11.6, -0.5, 1.7, -0.26],
  [12.8, -0.6, 1.25, 0.36],
  [14.0, 0.0, 0.96, 0.66],
  [15.2, 0.6, 0.82, 0.14],
  [16.4, 0.44, 0.72, -0.5],
  [17.6, -0.36, 0.96, -0.55],
  [18.6, -0.6, 1.36, 0.1],
  [19.8, -0.4, 1.8, -0.9],
  [CYCLE, 0.2, 2.3, -3.2],
];

/** Segment index and fraction for loop time c (uniform Catmull-Rom parameter = (i + f) / (n - 1)). */
export function fishParam(t: number): number {
  const c = loopTime(t);
  const k = FISH_KEYS;
  let i = 0;
  while (i < k.length - 2 && c >= k[i + 1][0]) i++;
  const f = clamp01((c - k[i][0]) / (k[i + 1][0] - k[i][0]));
  return (i + f) / (k.length - 1);
}

/** Fish opacity: fades in from the distance, out again at the end of the loop. */
export function fishOpacity(t: number): number {
  const c = loopTime(t);
  return Math.min(easeInOut(c / 1.4), easeInOut((CYCLE - c) / 1.8));
}
