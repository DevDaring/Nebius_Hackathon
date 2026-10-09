// Procedural anatomy of the stylised glass body, in metres (y up, feet at 0, ~1.70 m tall, facing +z).
// Plain numbers only (no three.js), so the 2-D fallback can draw the same body.
import type { OrganKey } from "@/api/types";
import type { BodyPart } from "@/lib/body";

export type V3 = [number, number, number];

/** Tapered capsule between two points (radius ra at a, rb at b). */
export interface Limb {
  a: V3;
  b: V3;
  ra: number;
  rb: number;
}
export interface Ellipsoid {
  c: V3;
  r: V3;
  /** rotation about z (radians) */
  rz?: number;
}

const mirror = (p: V3): V3 => [-p[0], p[1], p[2]];
const both = (l: Limb): Limb[] => [l, { ...l, a: mirror(l.a), b: mirror(l.b) }];

/** Torso profile for a lathe: [radius, y]. Depth is scaled by TORSO_DEPTH. */
export const TORSO_PROFILE: [number, number][] = [
  [0.001, 0.8],
  [0.07, 0.806],
  [0.128, 0.83],
  [0.158, 0.875],
  [0.166, 0.935],
  [0.152, 1.01],
  [0.137, 1.07],
  [0.142, 1.14],
  [0.158, 1.22],
  [0.172, 1.3],
  [0.176, 1.355],
  [0.16, 1.4],
  [0.115, 1.432],
  [0.06, 1.448],
  [0.001, 1.452],
];
export const TORSO_DEPTH = 0.64;

export const HEAD: Ellipsoid = { c: [0, 1.588, 0.004], r: [0.077, 0.104, 0.09] };
export const SHELL_ELLIPSOIDS: Ellipsoid[] = [
  HEAD,
  { c: [0.172, 1.362, -0.004], r: [0.058, 0.052, 0.056] },
  { c: [-0.172, 1.362, -0.004], r: [0.058, 0.052, 0.056] },
  { c: [0.303, 0.772, 0.024], r: [0.026, 0.058, 0.038], rz: 0.12 },
  { c: [-0.303, 0.772, 0.024], r: [0.026, 0.058, 0.038], rz: -0.12 },
  { c: [0.104, 0.032, 0.045], r: [0.038, 0.03, 0.098] },
  { c: [-0.104, 0.032, 0.045], r: [0.038, 0.03, 0.098] },
];
export const SHELL_LIMBS: Limb[] = [
  { a: [0, 1.4, -0.006], b: [0, 1.5, 0], ra: 0.05, rb: 0.045 }, // neck
  ...both({ a: [0.19, 1.355, -0.004], b: [0.246, 1.09, -0.012], ra: 0.047, rb: 0.037 }), // upper arms
  ...both({ a: [0.246, 1.09, -0.012], b: [0.292, 0.84, 0.018], ra: 0.037, rb: 0.027 }), // forearms
  ...both({ a: [0.086, 0.87, 0], b: [0.095, 0.49, 0.006], ra: 0.08, rb: 0.051 }), // thighs
  ...both({ a: [0.095, 0.49, 0.006], b: [0.102, 0.075, -0.012], ra: 0.051, rb: 0.03 }), // calves
];

/** Large muscles drawn as soft shells inside the glass. */
export const MUSCLES: Limb[] = [
  ...both({ a: [0.087, 0.82, 0.004], b: [0.094, 0.54, 0.008], ra: 0.064, rb: 0.044 }),
  ...both({ a: [0.097, 0.44, 0.0], b: [0.101, 0.2, -0.012], ra: 0.042, rb: 0.026 }),
  ...both({ a: [0.198, 1.31, -0.004], b: [0.238, 1.13, -0.01], ra: 0.036, rb: 0.03 }),
];

/* ---------------- organs ---------------- */
export const HEART: Ellipsoid = { c: [0.024, 1.252, 0.028], r: [0.042, 0.052, 0.038], rz: -0.45 };

export interface TubeSpec {
  points: V3[];
  /** radius along the tube, u in 0..1 */
  radius: (u: number) => number;
  /** scale of the cross-section in y (flattened organs) */
  squashY?: number;
}
export const STOMACH: TubeSpec = {
  points: [
    [0.028, 1.178, 0.0],
    [0.068, 1.162, 0.018],
    [0.092, 1.118, 0.03],
    [0.084, 1.068, 0.04],
    [0.052, 1.046, 0.045],
    [0.016, 1.054, 0.044],
    [-0.008, 1.07, 0.04],
  ],
  radius: (u) => 0.011 + 0.034 * Math.sin(Math.PI * Math.pow(u, 0.75)),
};
export const LIVER: TubeSpec = {
  points: [
    [-0.13, 1.1, 0.004],
    [-0.085, 1.13, 0.02],
    [-0.025, 1.142, 0.03],
    [0.04, 1.15, 0.03],
  ],
  radius: (u) => 0.012 + 0.05 * Math.pow(1 - u, 0.9),
  squashY: 0.72,
};
export const PANCREAS: TubeSpec = {
  points: [
    [-0.035, 1.03, -0.012],
    [0.0, 1.044, -0.026],
    [0.045, 1.058, -0.034],
    [0.088, 1.075, -0.032],
  ],
  radius: (u) => 0.008 + 0.014 * (1 - u),
  squashY: 0.8,
};

/** Small intestine: a coiled tube filling the lower abdomen. */
function coil(): V3[] {
  const pts: V3[] = [[0.0, 1.03, 0.035]];
  const rows = 5;
  for (let j = 0; j < rows; j++) {
    const y = 1.0 - j * 0.03;
    const dir = j % 2 === 0 ? 1 : -1;
    const n = 7;
    for (let i = 0; i <= n; i++) {
      const u = i / n;
      const x = dir * (-0.09 + 0.18 * u);
      const z = 0.035 + 0.018 * Math.sin(u * Math.PI * 3 + j);
      pts.push([x, y + 0.009 * Math.sin(u * Math.PI * 4 + j * 1.3), z]);
    }
  }
  pts.push([0.02, 0.85, 0.03]);
  return pts;
}
export const INTESTINE: TubeSpec = { points: coil(), radius: () => 0.0105 };

/* ---------------- vessels ---------------- */
export interface Vessel {
  points: V3[];
  r: number;
  part: BodyPart;
}
const arch: V3[] = [
  [0.018, 1.27, 0.012],
  [0.006, 1.33, -0.006],
  [-0.008, 1.315, -0.036],
];
const aortaDown: V3[] = [
  [-0.008, 1.315, -0.036],
  [0.004, 1.2, -0.052],
  [0.006, 1.05, -0.054],
  [0.003, 0.93, -0.046],
  [0.0, 0.895, -0.036],
];
const leg = (s: 1 | -1): V3[] => [
  [0.0, 0.895, -0.036],
  [s * 0.055, 0.85, -0.012],
  [s * 0.086, 0.74, 0.008],
  [s * 0.094, 0.52, 0.004],
  [s * 0.1, 0.3, -0.01],
  [s * 0.103, 0.1, -0.006],
];
const arm = (s: 1 | -1): V3[] => [
  [0.004, 1.33, -0.012],
  [s * 0.09, 1.37, -0.014],
  [s * 0.18, 1.355, -0.006],
  [s * 0.222, 1.2, -0.008],
  [s * 0.247, 1.08, -0.008],
  [s * 0.285, 0.87, 0.018],
];
const carotid = (s: 1 | -1): V3[] => [
  [s * 0.016, 1.33, -0.006],
  [s * 0.026, 1.46, 0.004],
  [s * 0.036, 1.56, 0.012],
];
const venaCava: V3[] = [
  [-0.028, 0.9, -0.024],
  [-0.034, 1.04, -0.03],
  [-0.032, 1.14, -0.024],
  [-0.012, 1.232, 0.006],
];
const portal: V3[] = [
  [0.004, 0.95, 0.036],
  [-0.02, 1.0, 0.03],
  [-0.042, 1.06, 0.022],
  [-0.068, 1.11, 0.012],
];
const hepatic: V3[] = [
  [-0.068, 1.12, 0.012],
  [-0.046, 1.16, 0.0],
  [-0.026, 1.205, 0.004],
  [0.008, 1.245, 0.022],
];
const splenic: V3[] = [
  [0.07, 1.066, -0.034],
  [0.02, 1.05, -0.02],
  [-0.02, 1.04, 0.006],
  [-0.03, 1.035, 0.024],
];

export const VESSELS: Vessel[] = [
  { points: [...arch, ...aortaDown.slice(1)], r: 0.0062, part: "blood" },
  { points: leg(1), r: 0.0046, part: "blood" },
  { points: leg(-1), r: 0.0046, part: "blood" },
  { points: arm(1), r: 0.0036, part: "blood" },
  { points: arm(-1), r: 0.0036, part: "blood" },
  { points: carotid(1), r: 0.0032, part: "blood" },
  { points: carotid(-1), r: 0.0032, part: "blood" },
  { points: venaCava, r: 0.0058, part: "blood" },
  { points: hepatic, r: 0.0045, part: "blood" },
  { points: portal, r: 0.0052, part: "gut_to_blood" },
  { points: splenic, r: 0.0035, part: "gut_to_blood" },
];

/* ---------------- flow particles ---------------- */
export type FlowKind = "glucose" | "insulin";
export interface FlowPath {
  id: string;
  points: V3[];
  /** which organ flows drive its density and speed */
  drivers: OrganKey[];
  count: number;
  kind: FlowKind;
}
const heart: V3 = [0.016, 1.258, 0.02];
export const FLOWS: FlowPath[] = [
  { id: "portal", points: [[0.0, 0.93, 0.04], ...portal, [-0.09, 1.12, 0.012]], drivers: ["gut_to_blood"], count: 70, kind: "glucose" },
  { id: "hepatic", points: [[-0.085, 1.118, 0.012], ...hepatic, heart], drivers: ["gut_to_blood", "liver"], count: 46, kind: "glucose" },
  { id: "legR", points: [heart, ...arch.slice(1), ...aortaDown.slice(1), ...leg(1).slice(1)], drivers: ["exercise_uptake", "insulin_uptake"], count: 58, kind: "glucose" },
  { id: "legL", points: [heart, ...arch.slice(1), ...aortaDown.slice(1), ...leg(-1).slice(1)], drivers: ["exercise_uptake", "insulin_uptake"], count: 58, kind: "glucose" },
  { id: "armR", points: [heart, ...arm(1)], drivers: ["insulin_uptake", "exercise_uptake"], count: 30, kind: "glucose" },
  { id: "armL", points: [heart, ...arm(-1)], drivers: ["insulin_uptake", "exercise_uptake"], count: 30, kind: "glucose" },
  { id: "insulin", points: [[0.09, 1.075, -0.032], ...splenic, ...portal.slice(2), ...hepatic.slice(1), heart], drivers: ["pancreas"], count: 40, kind: "insulin" },
];

/* ---------------- anchors (labels, focus, 2-D nodes) ---------------- */
export interface Anchor {
  /** where the organ is (leader line end, camera focus) */
  at: V3;
  /** label row height (m) and side: -1 = screen left, +1 = screen right */
  labelY: number;
  side: -1 | 1;
}
export const ANCHORS: Record<BodyPart, Anchor> = {
  unexplained: { at: [-0.05, 1.6, 0.06], labelY: 1.57, side: -1 },
  blood: { at: [0.024, 1.252, 0.05], labelY: 1.43, side: -1 },
  insulin: { at: [-0.006, 1.318, -0.01], labelY: 1.29, side: -1 },
  liver: { at: [-0.08, 1.125, 0.03], labelY: 1.15, side: -1 },
  gut_to_blood: { at: [-0.034, 1.04, 0.026], labelY: 1.01, side: -1 },
  insulin_uptake: { at: [-0.09, 0.68, 0.02], labelY: 0.72, side: -1 },
  stomach: { at: [0.074, 1.1, 0.04], labelY: 1.25, side: 1 },
  pancreas: { at: [0.05, 1.058, -0.02], labelY: 1.11, side: 1 },
  intestine: { at: [0.05, 0.93, 0.04], labelY: 0.97, side: 1 },
  exercise_uptake: { at: [0.1, 0.36, 0.02], labelY: 0.6, side: 1 },
};

/** Centripetal-free uniform Catmull-Rom sampling (enough for drawing the 2-D view). */
export function sampleCurve(points: V3[], n = 48): V3[] {
  if (points.length < 2) return points.slice();
  const out: V3[] = [];
  const P = [points[0], ...points, points[points.length - 1]];
  const segs = points.length - 1;
  for (let k = 0; k <= n; k++) {
    const t = (k / n) * segs;
    const i = Math.min(segs - 1, Math.floor(t));
    const f = t - i;
    const [p0, p1, p2, p3] = [P[i], P[i + 1], P[i + 2], P[i + 3]];
    const c = (a: number, b: number, cc: number, d: number) =>
      0.5 * (2 * b + (-a + cc) * f + (2 * a - 5 * b + 4 * cc - d) * f * f + (-a + 3 * b - 3 * cc + d) * f * f * f);
    out.push([c(p0[0], p1[0], p2[0], p3[0]), c(p0[1], p1[1], p2[1], p3[1]), c(p0[2], p1[2], p2[2], p3[2])]);
  }
  return out;
}
