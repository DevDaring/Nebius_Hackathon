// 2-D fallback of the glass body (no WebGL, or the user chose "Simple view"): the same organs,
// glow mapping, labels and panels, drawn as a front view in SVG.
import { useId, useMemo } from "react";
import type { BodyView, OrganKey } from "@/api/types";
import { PALETTE, at, auraIntensity, clamp01, glucoseColor, liverColor, mixRGB, muscleIntensity, organIntensities, organValues, rgbCss, type BodyPart } from "@/lib/body";
import { ANCHORS, FLOWS, HEAD, HEART, INTESTINE, LIVER, MUSCLES, PANCREAS, SHELL_ELLIPSOIDS, SHELL_LIMBS, STOMACH, TORSO_PROFILE, VESSELS, sampleCurve, type Limb, type TubeSpec, type V3 } from "./anatomy";
import type { SceneLabel } from "./types";

const W = 380;
const H = 480;
const S = 262; // px per metre
const X = (x: number) => W / 2 + x * S;
const Y = (y: number) => 14 + (1.72 - y) * S;
const pt = (p: V3) => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`;

function torsoPath(): string {
  const right = TORSO_PROFILE.map(([r, y]) => `${X(r).toFixed(1)},${Y(y).toFixed(1)}`);
  const left = TORSO_PROFILE.slice().reverse().map(([r, y]) => `${X(-r).toFixed(1)},${Y(y).toFixed(1)}`);
  return `M${right.join("L")}L${left.join("L")}Z`;
}

/** Outline polygon of a tube with varying radius (front projection). */
function tubePolygon(spec: TubeSpec, n = 40): string {
  const c = sampleCurve(spec.points, n);
  const L: string[] = [];
  const R: string[] = [];
  c.forEach((p, i) => {
    const a = c[Math.max(0, i - 1)];
    const b = c[Math.min(c.length - 1, i + 1)];
    const dx = X(b[0]) - X(a[0]);
    const dy = Y(b[1]) - Y(a[1]);
    const len = Math.hypot(dx, dy) || 1;
    const u = i / (c.length - 1);
    const r = spec.radius(u) * Math.pow(Math.sin(Math.PI * (0.015 + 0.97 * u)), 0.32) * S * (spec.squashY ?? 1);
    const nx = (-dy / len) * r;
    const ny = (dx / len) * r;
    L.push(`${(X(p[0]) + nx).toFixed(1)},${(Y(p[1]) + ny).toFixed(1)}`);
    R.push(`${(X(p[0]) - nx).toFixed(1)},${(Y(p[1]) - ny).toFixed(1)}`);
  });
  return `M${L.join("L")}L${R.reverse().join("L")}Z`;
}

const polyline = (pts: V3[], n = 40) => sampleCurve(pts, n).map(pt).join(" ");
const limbLine = (l: Limb, extra = 0, key?: string | number, props: React.SVGProps<SVGLineElement> = {}) => (
  <line key={key} x1={X(l.a[0])} y1={Y(l.a[1])} x2={X(l.b[0])} y2={Y(l.b[1])} strokeWidth={(l.ra + l.rb) * S + extra} strokeLinecap="round" {...props} />
);

export function BodySvg({
  view,
  scales,
  tf,
  showScenario,
  selected,
  onSelect,
  labels,
  reducedMotion,
  presentation,
  ariaLabel,
}: {
  view: BodyView;
  scales: Record<OrganKey, number>;
  tf: number;
  showScenario: boolean;
  selected: BodyPart | null;
  onSelect: (p: BodyPart) => void;
  labels: SceneLabel[];
  reducedMotion: boolean;
  presentation: boolean;
  ariaLabel: string;
}) {
  const uid = useId().replace(/:/g, "");
  const shapes = useMemo(
    () => ({
      torso: torsoPath(),
      stomach: tubePolygon(STOMACH),
      liver: tubePolygon(LIVER),
      pancreas: tubePolygon(PANCREAS),
      intestine: polyline(INTESTINE.points, 260),
      vessels: VESSELS.map((v) => ({ part: v.part, d: polyline(v.points), w: v.r * S * 2 })),
      flows: FLOWS.map((f) => ({ id: f.id, kind: f.kind, d: polyline(f.points, 60) })),
    }),
    [],
  );
  const mix = showScenario && view.scenario ? 1 : 0;
  const vals = organValues(view, tf, mix);
  const n = organIntensities(vals, scales);
  const v = mix ? view.scenario! : view.baseline;
  const g = at(v.blood.q50, tf);
  const blood = rgbCss(glucoseColor(g));
  const lc = at(v.learned_correction, tf);
  const aura = auraIntensity(vals.unexplained, lc, scales.unexplained);
  const mi = muscleIntensity(n);
  const exShare = clamp01(n.exercise_uptake / Math.max(1e-3, n.exercise_uptake + 0.45 * n.insulin_uptake));
  const muscleCol = rgbCss(mixRGB(PALETTE.teal, PALETTE.marigold, exShare));
  const mari = rgbCss(PALETTE.marigold);
  const glow = (x: number) => 0.18 + 0.82 * clamp01(x);
  const ring = (p: BodyPart) => (selected === p ? { stroke: "rgb(250 246 239)", strokeWidth: 1.4 } : {});
  const click = (p: BodyPart) => ({
    onClick: () => onSelect(p),
    "data-body-part": p,
    style: { cursor: "pointer", transition: "opacity 400ms, fill 400ms" } as React.CSSProperties,
  });
  const flowN: Record<string, number> = {
    portal: n.gut_to_blood,
    hepatic: Math.max(0.85 * n.gut_to_blood, vals.liver > 0 ? n.liver : 0),
    legR: Math.max(n.exercise_uptake, 0.6 * n.insulin_uptake),
    legL: Math.max(n.exercise_uptake, 0.6 * n.insulin_uptake),
    armR: Math.max(0.6 * n.insulin_uptake, 0.5 * n.exercise_uptake),
    armL: Math.max(0.6 * n.insulin_uptake, 0.5 * n.exercise_uptake),
    insulin: n.pancreas,
  };
  const fs = presentation ? 14 : 12;
  // stomach fill level (bottom up)
  const sy = STOMACH.points.map((p) => p[1]);
  const sMin = Math.min(...sy) - 0.035;
  const sMax = Math.max(...sy) + 0.03;
  const fillY = Y(sMin + (sMax - sMin) * clamp01(n.stomach));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-full w-full" role="img" aria-label={ariaLabel} data-body-svg>
      <defs>
        <filter id={`glow-${uid}`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id={`soft-${uid}`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="9" />
        </filter>
        <clipPath id={`fill-${uid}`}>
          <rect x={0} y={fillY} width={W} height={H} />
        </clipPath>
        <radialGradient id={`floor-${uid}`}>
          <stop offset="0%" stopColor="rgb(43 179 163)" stopOpacity="0.4" />
          <stop offset="100%" stopColor="rgb(43 179 163)" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse cx={X(0)} cy={Y(0)} rx={150} ry={16} fill={`url(#floor-${uid})`} />

      {/* aura */}
      <g opacity={0.15 + 0.6 * aura} filter={`url(#soft-${uid})`} aria-hidden>
        <path d={shapes.torso} fill="none" stroke="rgb(185 178 255)" strokeWidth={6} />
        <ellipse cx={X(HEAD.c[0])} cy={Y(HEAD.c[1])} rx={HEAD.r[0] * S} ry={HEAD.r[1] * S} fill="none" stroke="rgb(185 178 255)" strokeWidth={6} />
      </g>

      {/* glass silhouette: rim strokes, then the interior fill hides inner seams */}
      <g stroke="rgb(207 216 255)" strokeOpacity={0.75} fill="rgb(207 216 255)" aria-hidden>
        <path d={shapes.torso} strokeWidth={3} />
        {SHELL_ELLIPSOIDS.map((e, i) => (
          <ellipse key={i} cx={X(e.c[0])} cy={Y(e.c[1])} rx={e.r[0] * S + 1.5} ry={e.r[1] * S + 1.5} transform={e.rz ? `rotate(${(-e.rz * 180) / Math.PI} ${X(e.c[0])} ${Y(e.c[1])})` : undefined} />
        ))}
        {SHELL_LIMBS.map((l, i) => limbLine(l, 3, i, { stroke: "rgb(207 216 255)" }))}
      </g>
      <g fill="rgb(20 25 62)" stroke="rgb(20 25 62)" aria-hidden>
        <path d={shapes.torso} strokeWidth={0} />
        {SHELL_ELLIPSOIDS.map((e, i) => (
          <ellipse key={i} cx={X(e.c[0])} cy={Y(e.c[1])} rx={e.r[0] * S} ry={e.r[1] * S} transform={e.rz ? `rotate(${(-e.rz * 180) / Math.PI} ${X(e.c[0])} ${Y(e.c[1])})` : undefined} />
        ))}
        {SHELL_LIMBS.map((l, i) => limbLine(l, 0, i, { stroke: "rgb(20 25 62)" }))}
      </g>

      {/* muscles */}
      <g {...click("exercise_uptake")} role="presentation">
        {MUSCLES.map((l, i) => limbLine(l, 0, i, { stroke: muscleCol, strokeOpacity: 0.1 + 0.6 * mi, ...(selected === "exercise_uptake" ? { strokeOpacity: 0.85 } : {}) }))}
      </g>

      {/* vessels and flows */}
      {shapes.vessels.map((ves, i) => (
        <polyline key={i} points={ves.d} fill="none" stroke={ves.part === "blood" ? blood : mari} strokeOpacity={ves.part === "blood" ? 0.75 : glow(n.gut_to_blood)} strokeWidth={Math.max(1.4, ves.w)} strokeLinecap="round" {...click(ves.part)} />
      ))}
      {!reducedMotion &&
        shapes.flows.map((f) => {
          const fn = flowN[f.id] ?? 0;
          if (fn < 0.03) return null;
          return (
            <polyline
              key={f.id}
              points={f.d}
              fill="none"
              stroke={f.kind === "insulin" ? "rgb(255 241 214)" : mari}
              strokeWidth={2.4}
              strokeLinecap="round"
              strokeDasharray="1.5 10.5"
              opacity={0.3 + 0.7 * fn}
              className="body-flow"
              style={{ animationDuration: `${(2.6 / (0.25 + fn)).toFixed(2)}s` }}
              aria-hidden
            />
          );
        })}

      {/* organs */}
      <g {...click("intestine")}>
        <polyline points={shapes.intestine} fill="none" stroke={mari} strokeOpacity={0.22} strokeWidth={INTESTINE.radius(0) * 2 * S} strokeLinejoin="round" strokeLinecap="round" />
        <polyline
          points={shapes.intestine}
          fill="none"
          stroke={mari}
          strokeWidth={INTESTINE.radius(0) * 2 * S}
          strokeLinejoin="round"
          strokeLinecap="round"
          pathLength={1}
          strokeDasharray={`${clamp01(n.intestine).toFixed(3)} 1`}
          opacity={glow(n.intestine)}
          filter={`url(#glow-${uid})`}
        />
      </g>
      <g {...click("pancreas")}>
        <path d={shapes.pancreas} fill="rgb(247 230 200)" opacity={glow(n.pancreas)} filter={`url(#glow-${uid})`} {...ring("pancreas")} />
      </g>
      <g {...click("liver")}>
        <path d={shapes.liver} fill={rgbCss(liverColor(vals.liver))} opacity={glow(n.liver)} filter={`url(#glow-${uid})`} {...ring("liver")} />
      </g>
      <g {...click("stomach")}>
        <path d={shapes.stomach} fill={mari} opacity={0.22} {...ring("stomach")} />
        <path d={shapes.stomach} fill={mari} opacity={glow(n.stomach)} clipPath={`url(#fill-${uid})`} filter={`url(#glow-${uid})`} />
      </g>
      <g {...click("blood")}>
        <ellipse cx={X(HEART.c[0])} cy={Y(HEART.c[1])} rx={HEART.r[0] * S} ry={HEART.r[1] * S} transform={`rotate(${(-(HEART.rz ?? 0) * 180) / Math.PI} ${X(HEART.c[0])} ${Y(HEART.c[1])})`} fill={blood} opacity={0.85} filter={`url(#glow-${uid})`} {...ring("blood")} />
      </g>

      {/* labels */}
      {labels.map((l) => {
        const an = ANCHORS[l.part];
        const lx = X(an.side * 0.36);
        const ly = Y(an.labelY);
        const anchor = an.side < 0 ? "end" : "start";
        const on = selected === l.part;
        return (
          <g
            key={l.part}
            role="button"
            tabIndex={-1}
            aria-label={`${l.name}: ${l.value} ${l.unit}`}
            onClick={() => onSelect(l.part)}
            style={{ cursor: "pointer" }}
            data-body-label={l.part}
          >
            <line x1={X(an.at[0])} y1={Y(an.at[1])} x2={lx - an.side * 2} y2={ly} stroke="rgb(184 189 228)" strokeOpacity={0.45} strokeWidth={0.8} />
            <circle cx={X(an.at[0])} cy={Y(an.at[1])} r={1.8} fill={l.color} />
            <text x={lx} y={ly - 1.5} textAnchor={anchor} fontSize={fs} fontWeight={700} fill={on ? "rgb(var(--marigold))" : "rgb(var(--moon))"} style={{ fontFamily: "var(--font-ui)" }}>
              {l.name}
            </text>
            <text x={lx} y={ly + fs} textAnchor={anchor} fontSize={fs - 1} fill="rgb(184 189 228)" style={{ fontFamily: "var(--font-ui)" }}>
              <tspan fontWeight={700} fill="rgb(237 235 255)">
                {l.value}
              </tspan>{" "}
              {l.unit}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
