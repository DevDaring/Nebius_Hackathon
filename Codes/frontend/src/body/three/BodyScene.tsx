// The 3-D glass body (three.js via @react-three/fiber). Loaded as its own chunk only when WebGL works.
import { useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { BodyPart } from "@/lib/body";
import { PALETTE, at, auraIntensity, clamp01, glucoseColor, muscleIntensity, organIntensities, organValues } from "@/lib/body";
import { ANCHORS, FLOWS, HEART, INTESTINE, LIVER, MUSCLES, PANCREAS, STOMACH, VESSELS } from "../anatomy";
import type { CameraCmd, SceneProps } from "../types";
import { bodyShellGeometry, ellipsoidGeometry, limbGeometry, organTubeGeometry, pathLut, vesselGeometry } from "./geometry";
import { auraMaterial, depthOnlyMaterial, glassMaterial, glowMaterial, organMaterial, particleMaterial } from "./materials";

type Controls = THREE.EventDispatcher<{ start: object; end: object; change: object }> & {
  target: THREE.Vector3;
  autoRotate: boolean;
  autoRotateSpeed: number;
  minDistance: number;
  maxDistance: number;
  minPolarAngle: number;
  maxPolarAngle: number;
};

const TARGET = new THREE.Vector3(0, 0.9, 0);
const DIST = 3.35;
const DIST_COMPACT = 3.8;
const POLAR = 1.5;
const MIN_POLAR = 0.95;
const MAX_POLAR = 1.98;
const MIN_DIST = 0.85;
const MAX_DIST = 4.6;
const noRaycast = () => undefined;
const rgb = (c: readonly number[]) => new THREE.Color().setRGB(c[0] / 255, c[1] / 255, c[2] / 255, THREE.SRGBColorSpace);

function sphericalPos(target: THREE.Vector3, dist: number, polar: number, az: number) {
  return new THREE.Vector3().setFromSphericalCoords(dist, polar, az).add(target);
}

/* ---------------- assets (built once per canvas) ---------------- */
function buildAssets(pixelRatio: number) {
  const shell = bodyShellGeometry();
  const stomach = organTubeGeometry(STOMACH, 96, 22);
  const liver = organTubeGeometry(LIVER, 64, 24);
  const pancreas = organTubeGeometry(PANCREAS, 48, 16);
  const intestine = organTubeGeometry(INTESTINE, 420, 10, false);
  const heart = ellipsoidGeometry({ ...HEART, c: [0, 0, 0] }, 28, 20);
  const muscles = mergeGeometries(MUSCLES.map((m) => limbGeometry(m, 20)), false);
  const bloodVessels = mergeGeometries(VESSELS.filter((v) => v.part === "blood").map((v) => vesselGeometry(v.points, v.r)), false);
  const portalVessels = mergeGeometries(VESSELS.filter((v) => v.part !== "blood").map((v) => vesselGeometry(v.points, v.r)), false);
  const sb = stomach.boundingBox!;

  const mats = {
    depth: depthOnlyMaterial(),
    glass: glassMaterial(),
    aura: auraMaterial(),
    stomach: organMaterial(rgb(PALETTE.marigold), 1, [sb.min.y + 0.004, sb.max.y - 0.006]),
    intestine: organMaterial(rgb(PALETTE.marigold), 2),
    liver: organMaterial(rgb(PALETTE.teal)),
    pancreas: organMaterial(new THREE.Color("#E9C88E")),
    heart: organMaterial(rgb(PALETTE.teal)),
    muscles: organMaterial(rgb(PALETTE.marigold)),
    vessels: organMaterial(rgb(PALETTE.teal)),
    portal: organMaterial(rgb(PALETTE.marigold)),
  };
  mats.vessels.uniforms.uBase.value = 0.3;
  mats.muscles.uniforms.uCore.value = 0.04;

  const halo = (part: BodyPart | "muscle", pos: [number, number, number], size: number, color: THREE.Color) => ({
    part,
    pos,
    size,
    mat: glowMaterial(color),
  });
  const quad = new THREE.PlaneGeometry(1, 1);
  const halos = [
    halo("stomach", [0.06, 1.1, 0.04], 0.26, rgb(PALETTE.marigold)),
    halo("intestine", [0.0, 0.93, 0.04], 0.34, rgb(PALETTE.marigold)),
    halo("liver", [-0.07, 1.125, 0.02], 0.3, rgb(PALETTE.teal)),
    halo("pancreas", [0.03, 1.055, -0.02], 0.18, new THREE.Color("#E9C88E")),
    halo("blood", [0.024, 1.252, 0.03], 0.26, rgb(PALETTE.teal)),
    halo("muscle", [0.09, 0.68, 0.0], 0.26, rgb(PALETTE.marigold)),
    halo("muscle", [-0.09, 0.68, 0.0], 0.26, rgb(PALETTE.marigold)),
    halo("muscle", [0.1, 0.32, 0.0], 0.18, rgb(PALETTE.marigold)),
    halo("muscle", [-0.1, 0.32, 0.0], 0.18, rgb(PALETTE.marigold)),
  ];

  // Flow particles along vessel paths.
  const luts = FLOWS.map((f) => pathLut(f.points));
  const total = FLOWS.reduce((s, f) => s + f.count, 0);
  const positions = new Float32Array(total * 3);
  const alphas = new Float32Array(total);
  const colors = new Float32Array(total * 3);
  const pathOf = new Uint8Array(total);
  const rank = new Float32Array(total);
  const phase = new Float32Array(total);
  const jitter = new Float32Array(total * 3);
  let k = 0;
  FLOWS.forEach((f, pi) => {
    for (let j = 0; j < f.count; j++, k++) {
      pathOf[k] = pi;
      rank[k] = (j + 0.5) / f.count;
      phase[k] = (j * 0.618034) % 1;
      jitter[k * 3] = (Math.random() - 0.5) * 0.008;
      jitter[k * 3 + 1] = (Math.random() - 0.5) * 0.008;
      jitter[k * 3 + 2] = (Math.random() - 0.5) * 0.008;
    }
  });
  const pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
  pGeo.setAttribute("aAlpha", new THREE.BufferAttribute(alphas, 1).setUsage(THREE.DynamicDrawUsage));
  pGeo.setAttribute("aColor", new THREE.BufferAttribute(colors, 3).setUsage(THREE.DynamicDrawUsage));
  pGeo.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.85, 0), 1.2);
  const particles = { geo: pGeo, mat: particleMaterial(pixelRatio), luts, pathOf, rank, phase, jitter, total };

  // Leader lines from organs to their labels.
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(20 * 2 * 3), 3).setUsage(THREE.DynamicDrawUsage));
  lineGeo.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.85, 0), 2);
  const lineMat = new THREE.LineBasicMaterial({ color: new THREE.Color("#b8bde4"), transparent: true, opacity: 0.4, depthTest: false });

  const floorMat = glowMaterial(rgb(PALETTE.teal), false);
  floorMat.uniforms.uOpacity.value = 0.55;
  const ringMat = new THREE.MeshBasicMaterial({ color: new THREE.Color("#b8bde4"), transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide });

  const geos = { shell, stomach, liver, pancreas, intestine, heart, muscles, bloodVessels, portalVessels, quad };
  const dispose = () => {
    Object.values(geos).forEach((g) => g.dispose());
    Object.values(mats).forEach((m) => m.dispose());
    halos.forEach((h) => h.mat.dispose());
    pGeo.dispose();
    particles.mat.dispose();
    lineGeo.dispose();
    lineMat.dispose();
    floorMat.dispose();
    ringMat.dispose();
  };
  return { geos, mats, halos, particles, lineGeo, lineMat, floorMat, ringMat, dispose };
}
type Assets = ReturnType<typeof buildAssets>;

/* ---------------- camera rig ---------------- */
function Rig({ cmd, reducedMotion, compact, onInteract }: { cmd: CameraCmd | null; reducedMotion: boolean; compact: boolean; onInteract?: () => void }) {
  const controls = useThree((s) => s.controls) as unknown as Controls | null;
  const camera = useThree((s) => s.camera);
  const invalidate = useThree((s) => s.invalidate);
  const goal = useRef<{ pos: THREE.Vector3; target: THREE.Vector3 } | null>(null);
  const spin = useRef(!reducedMotion);
  const idle = useRef<number | undefined>(undefined);
  const interact = useRef(onInteract);
  interact.current = onInteract;

  const dom = useThree((s) => s.gl.domElement);
  useEffect(() => {
    // Phones: one-finger vertical swipes still scroll the page; horizontal drags turn the body, pinch zooms.
    if (controls) dom.style.touchAction = compact ? "pan-y" : "none";
  }, [controls, dom, compact]);

  useEffect(() => {
    if (!controls) return;
    const start = () => {
      goal.current = null;
      spin.current = false;
      window.clearTimeout(idle.current);
      interact.current?.();
    };
    const end = () => {
      window.clearTimeout(idle.current);
      if (reducedMotion) return;
      idle.current = window.setTimeout(() => {
        spin.current = true;
        invalidate();
      }, 12_000);
    };
    controls.addEventListener("start", start);
    controls.addEventListener("end", end);
    return () => {
      controls.removeEventListener("start", start);
      controls.removeEventListener("end", end);
      window.clearTimeout(idle.current);
    };
  }, [controls, reducedMotion, invalidate]);

  useEffect(() => {
    if (!cmd || !controls) return;
    const tgt = controls.target.clone();
    const off = camera.position.clone().sub(tgt);
    const sph = new THREE.Spherical().setFromVector3(off);
    const dist0 = compact ? DIST_COMPACT : DIST;
    spin.current = false;
    window.clearTimeout(idle.current);
    let g: { pos: THREE.Vector3; target: THREE.Vector3 } | null = null;
    switch (cmd.kind) {
      case "front":
        g = { target: TARGET.clone(), pos: sphericalPos(TARGET, dist0, POLAR, 0) };
        break;
      case "side":
        g = { target: TARGET.clone(), pos: sphericalPos(TARGET, dist0, POLAR, Math.PI / 2) };
        break;
      case "back":
        g = { target: TARGET.clone(), pos: sphericalPos(TARGET, dist0, POLAR, Math.PI) };
        break;
      case "reset":
        g = { target: TARGET.clone(), pos: sphericalPos(TARGET, dist0, POLAR, 0) };
        spin.current = !reducedMotion;
        break;
      case "follow": {
        const t = new THREE.Vector3(0.005, 1.03, 0.02);
        g = { target: t, pos: sphericalPos(t, compact ? 1.75 : 1.3, 1.42, 0.38) };
        break;
      }
      case "focus": {
        const a = ANCHORS[cmd.part].at;
        const t = new THREE.Vector3(a[0], a[1], a[2]);
        g = { target: t, pos: sphericalPos(t, compact ? 1.25 : 1.05, Math.min(MAX_POLAR, Math.max(MIN_POLAR, sph.phi)), sph.theta) };
        break;
      }
      case "rotate": {
        const phi = Math.min(MAX_POLAR, Math.max(MIN_POLAR, sph.phi + cmd.dPolar));
        g = { target: tgt, pos: sphericalPos(tgt, sph.radius, phi, sph.theta + cmd.dAz) };
        break;
      }
      case "zoom": {
        const r = Math.min(MAX_DIST, Math.max(MIN_DIST, sph.radius * cmd.factor));
        g = { target: tgt, pos: sphericalPos(tgt, r, sph.phi, sph.theta) };
        break;
      }
    }
    goal.current = g;
    invalidate();
    // Only a new command (seq) moves the camera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cmd?.seq, controls]);

  useFrame((_, dt) => {
    if (!controls) return;
    controls.autoRotate = spin.current && !goal.current;
    const g = goal.current;
    if (g) {
      const k = reducedMotion ? 1 : 1 - Math.exp(-Math.min(dt, 0.1) * 5);
      camera.position.lerp(g.pos, k);
      controls.target.lerp(g.target, k);
      if (camera.position.distanceTo(g.pos) < 0.003 && controls.target.distanceTo(g.target) < 0.003) {
        camera.position.copy(g.pos);
        controls.target.copy(g.target);
        goal.current = null;
      }
    }
    if (goal.current || controls.autoRotate) invalidate();
  });
  return null;
}

/* ---------------- labels ---------------- */
function Labels({ labels, selected, onSelect, compact, presentation, a }: Pick<SceneProps, "labels" | "selected" | "onSelect" | "compact" | "presentation"> & { a: Assets }) {
  const groups = useRef<Record<string, THREE.Group | null>>({});
  const els = useRef<Record<string, HTMLButtonElement | null>>({});
  const sizes = useRef<Record<string, { w: number; h: number }>>({});
  const controls = useThree((s) => s.controls) as unknown as Controls | null;
  const invalidate = useThree((s) => s.invalidate);
  const right = useMemo(() => new THREE.Vector3(), []);
  const tmp = useMemo(() => new THREE.Vector3(), []);
  const work = useMemo(() => Array.from({ length: 12 }, () => ({ part: "" as BodyPart, side: 1, x: 0, y: 0, z: 0, w: 0, h: 0 })), []);

  // Measure the label boxes after they render (text, language and size change their width).
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      for (const l of labels) {
        const el = els.current[l.part];
        if (el) sizes.current[l.part] = { w: el.offsetWidth, h: el.offsetHeight };
      }
      invalidate();
    });
    return () => cancelAnimationFrame(id);
  }, [labels, presentation, compact, invalidate]);

  useFrame(({ camera, size }) => {
    right.setFromMatrixColumn(camera.matrixWorld, 0);
    right.y = 0;
    if (right.lengthSq() < 1e-6) right.set(1, 0, 0);
    right.normalize();
    const tgt = controls?.target ?? TARGET;
    const dist = camera.position.distanceTo(tgt);
    const off = (compact ? 0.2 : 0.29) * Math.min(1, Math.max(0.42, dist / (compact ? DIST_COMPACT : DIST)));
    const pad = 6;
    // 1) ideal spot beside the body, in screen space
    const n = Math.min(labels.length, work.length);
    for (let i = 0; i < n; i++) {
      const l = labels[i];
      const an = ANCHORS[l.part];
      tmp.set(0, an.labelY, 0).addScaledVector(right, an.side * off).project(camera);
      const sz = sizes.current[l.part] ?? { w: compact ? 110 : 140, h: compact ? 28 : 32 };
      const wk = work[i];
      wk.part = l.part;
      wk.side = an.side;
      wk.x = ((tmp.x + 1) / 2) * size.width;
      wk.y = ((1 - tmp.y) / 2) * size.height;
      wk.z = tmp.z;
      wk.w = sz.w;
      wk.h = sz.h;
      // 2) keep the whole box inside the canvas
      if (wk.side < 0 && wk.x - wk.w < pad) wk.x = wk.w + pad;
      if (wk.side > 0 && wk.x + wk.w > size.width - pad) wk.x = size.width - pad - wk.w;
    }
    // 3) stack each column without overlaps
    for (const side of [-1, 1]) {
      const col = work.slice(0, n).filter((w) => w.side === side).sort((p, q) => p.y - q.y);
      for (let i = 1; i < col.length; i++) {
        const min = col[i - 1].y + (col[i - 1].h + col[i].h) / 2 + 3;
        if (col[i].y < min) col[i].y = min;
      }
      // keep clear of the toolbar (phones) at the top and the honesty banner at the bottom
      const top = compact ? 48 : pad;
      const bottom = size.height - 40;
      if (col[0] && col[0].y - col[0].h / 2 < top) {
        let push = top - (col[0].y - col[0].h / 2);
        for (let i = 0; i < col.length && push > 0; i++) {
          col[i].y += push;
          const next = col[i + 1];
          push = next ? col[i].y + (col[i].h + next.h) / 2 + 3 - next.y : 0;
        }
      }
      const last = col[col.length - 1];
      if (last && last.y + last.h / 2 > bottom) {
        let shift = last.y + last.h / 2 - bottom;
        for (let i = col.length - 1; i >= 0 && shift > 0; i--) {
          col[i].y -= shift;
          const prev = col[i - 1];
          shift = prev ? prev.y + (prev.h + col[i].h) / 2 + 3 - col[i].y : 0;
        }
      }
    }
    // 4) back to world space; leader lines from the organ to the label's inner edge
    const pos = a.lineGeo.attributes.position as THREE.BufferAttribute;
    let k = 0;
    for (let i = 0; i < n; i++) {
      const wk = work[i];
      tmp.set((wk.x / size.width) * 2 - 1, 1 - (wk.y / size.height) * 2, wk.z).unproject(camera);
      const g = groups.current[wk.part];
      if (g) g.position.copy(tmp);
      const an = ANCHORS[wk.part];
      pos.setXYZ(k * 2, an.at[0], an.at[1], an.at[2]);
      pos.setXYZ(k * 2 + 1, tmp.x, tmp.y, tmp.z);
      k++;
    }
    for (let i = k; i < 20; i++) {
      pos.setXYZ(i * 2, 0, -10, 0);
      pos.setXYZ(i * 2 + 1, 0, -10, 0);
    }
    pos.needsUpdate = true;
  });
  const fs = presentation ? (compact ? 12 : 14) : compact ? 10 : 11.5;
  return (
    <>
      <lineSegments geometry={a.lineGeo} material={a.lineMat} renderOrder={30} raycast={noRaycast} frustumCulled={false} />
      {labels.map((l) => {
        const side = ANCHORS[l.part].side;
        const on = selected === l.part;
        return (
          <group key={l.part} ref={(el) => (groups.current[l.part] = el)}>
            <Html zIndexRange={[24, 10]} style={{ pointerEvents: "none" }}>
              <button
                ref={(el) => (els.current[l.part] = el)}
                type="button"
                tabIndex={-1}
                onClick={() => onSelect(l.part)}
                data-body-label={l.part}
                className={`pointer-events-auto block ${compact ? "max-w-[7.4rem]" : "max-w-[11rem]"} rounded-lg border px-1.5 py-[1px] text-left leading-[1.18] shadow-lg backdrop-blur-sm transition-colors ${
                  on ? "border-marigold bg-night/90" : "border-night-line/70 bg-night/70 hover:border-marigold/70"
                }`}
                style={{ transform: side < 0 ? "translate(-100%, -50%)" : "translate(0, -50%)", fontSize: fs }}
              >
                <span className="flex items-center gap-1 font-semibold text-moon">
                  <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: l.color }} aria-hidden />
                  <span className="truncate">{l.name}</span>
                </span>
                <span className="num block whitespace-nowrap text-moon-2">
                  <span className="font-bold text-moon">{l.value}</span> <span style={{ fontSize: fs - 1.5 }}>{l.unit}</span>
                </span>
              </button>
            </Html>
          </group>
        );
      })}
    </>
  );
}

/* ---------------- the body ---------------- */
function Body(p: SceneProps) {
  const { view, scales, live, reducedMotion } = p;
  const gl = useThree((s) => s.gl);
  const invalidate = useThree((s) => s.invalidate);
  const a = useMemo(() => buildAssets(gl.getPixelRatio()), [gl]);
  useEffect(() => () => a.dispose(), [a]);
  const mix = useRef(live.current.mixTarget);
  const heartRef = useRef<THREE.Mesh>(null);
  const tmpColor = useMemo(() => new THREE.Color(), []);
  const marigold = useMemo(() => rgb(PALETTE.marigold), []);
  const teal = useMemo(() => rgb(PALETTE.teal), []);
  const insulinColor = useMemo(() => new THREE.Color("#FFF1D6"), []);

  useEffect(() => invalidate(), [view, scales, p.selected, p.labels, p.playing, invalidate]);

  useFrame((state, delta) => {
    const L = live.current;
    const dt = Math.min(delta, 0.1);
    const time = state.clock.elapsedTime;
    const target = view.scenario ? L.mixTarget : 0;
    if (mix.current !== target) {
      const step = dt / 0.38;
      mix.current = Math.abs(target - mix.current) <= step ? target : mix.current + Math.sign(target - mix.current) * step;
    }
    const m = mix.current;
    const tf = L.tf;
    const vals = organValues(view, tf, m);
    const n = organIntensities(vals, scales);
    const bq = (s: { q50: number[] } | undefined) => at(s?.q50, tf);
    const g0 = bq(view.baseline.blood);
    const g = view.scenario ? g0 + (bq(view.scenario.blood) - g0) * m : g0;
    const lc0 = at(view.baseline.learned_correction, tf);
    const lc = view.scenario ? lc0 + (at(view.scenario.learned_correction, tf) - lc0) * m : lc0;
    const blood = rgb(glucoseColor(g));
    const sel = p.selected;
    const base = (part: BodyPart, b = 0.16) => (sel === part ? 0.55 : b);
    const M = a.mats;

    for (const mat of Object.values(M)) if ("uniforms" in mat && mat.uniforms.uTime) mat.uniforms.uTime.value = time;
    M.stomach.uniforms.uIntensity.value = 0.12 + 0.88 * n.stomach;
    M.stomach.uniforms.uFill.value = n.stomach;
    M.stomach.uniforms.uBase.value = base("stomach");
    M.intestine.uniforms.uIntensity.value = 0.1 + 0.9 * n.intestine;
    M.intestine.uniforms.uFill.value = n.intestine;
    M.intestine.uniforms.uBase.value = base("intestine", 0.13);
    M.portal.uniforms.uIntensity.value = 0.2 + 0.9 * n.gut_to_blood;
    M.portal.uniforms.uBase.value = base("gut_to_blood", 0.25);
    // Liver: teal while releasing glucose, marigold while taking it up (smooth around zero).
    const lf = clamp01((vals.liver + 0.05) / 0.1);
    M.liver.uniforms.uColor.value.copy(marigold).lerp(teal, lf);
    M.liver.uniforms.uIntensity.value = 0.08 + 0.92 * n.liver;
    M.liver.uniforms.uBase.value = base("liver", 0.2);
    M.pancreas.uniforms.uIntensity.value = 0.06 + 0.55 * n.pancreas;
    M.pancreas.uniforms.uBase.value = base("pancreas", 0.18);
    const mi = muscleIntensity(n);
    const exShare = clamp01(n.exercise_uptake / Math.max(1e-3, n.exercise_uptake + 0.45 * n.insulin_uptake));
    M.muscles.uniforms.uColor.value.copy(teal).lerp(marigold, exShare);
    // Insulin-driven uptake gives a soft teal glow; muscles working (exercise) light up marigold.
    M.muscles.uniforms.uIntensity.value = 0.03 + 0.3 * 0.45 * n.insulin_uptake + 0.72 * n.exercise_uptake;
    M.muscles.uniforms.uBase.value = sel === "exercise_uptake" || sel === "insulin_uptake" ? 0.4 : 0.06;
    M.vessels.uniforms.uColor.value.copy(blood);
    M.vessels.uniforms.uIntensity.value = 0.35 + 0.3 * n.insulin;
    M.vessels.uniforms.uBase.value = base("blood", 0.28);
    const beat = reducedMotion ? 0 : Math.pow(Math.max(0, Math.sin(time * Math.PI * 2 * 1.1)), 6);
    M.heart.uniforms.uColor.value.copy(blood);
    M.heart.uniforms.uIntensity.value = 0.6 + 0.35 * beat;
    M.heart.uniforms.uBase.value = base("blood", 0.25);
    if (heartRef.current) heartRef.current.scale.setScalar(1 + 0.05 * beat);
    M.aura.uniforms.uIntensity.value = 0.12 + 0.9 * auraIntensity(vals.unexplained, lc, scales.unexplained);

    // halos
    a.halos.forEach((h) => {
      const v = h.part === "muscle" ? Math.max(n.exercise_uptake, 0.3 * mi) : h.part === "blood" ? 0.45 + 0.3 * beat : n[h.part as keyof typeof n] ?? 0;
      const u = h.mat.uniforms;
      if (h.part === "liver") u.uColor.value.copy(M.liver.uniforms.uColor.value);
      if (h.part === "blood") u.uColor.value.copy(blood);
      if (h.part === "muscle") u.uColor.value.copy(M.muscles.uniforms.uColor.value);
      u.uOpacity.value = (h.part === "muscle" ? 0.01 + 0.24 * v * v : 0.04 + 0.4 * v * v) + (sel === h.part ? 0.12 : 0);
      u.uSize.value = h.size * (0.75 + 0.55 * v);
    });

    // particles
    const P = a.particles;
    const pos = P.geo.attributes.position as THREE.BufferAttribute;
    const al = P.geo.attributes.aAlpha as THREE.BufferAttribute;
    const co = P.geo.attributes.aColor as THREE.BufferAttribute;
    const flowN = FLOWS.map((f) => {
      if (f.id === "hepatic") return clamp01(Math.max(n.gut_to_blood * 0.85, vals.liver > 0 ? n.liver : 0));
      if (f.id.startsWith("leg")) return clamp01(Math.max(n.exercise_uptake, 0.6 * n.insulin_uptake));
      if (f.id.startsWith("arm")) return clamp01(Math.max(0.6 * n.insulin_uptake, 0.5 * n.exercise_uptake));
      return Math.max(...f.drivers.map((d) => n[d]));
    });
    for (let i = 0; i < P.total; i++) {
      const pi = P.pathOf[i];
      const fn = flowN[pi];
      const density = fn < 0.03 ? 0 : 0.12 + 0.88 * fn;
      const visible = P.rank[i] < density;
      if (!reducedMotion) P.phase[i] = (P.phase[i] + dt * (0.06 + 0.42 * fn)) % 1;
      const lut = P.luts[pi];
      const nPts = lut.length / 3 - 1;
      const x = P.phase[i] * nPts;
      const j = Math.floor(x);
      const f = x - j;
      const j2 = Math.min(nPts, j + 1);
      pos.setXYZ(
        i,
        lut[j * 3] + (lut[j2 * 3] - lut[j * 3]) * f + P.jitter[i * 3],
        lut[j * 3 + 1] + (lut[j2 * 3 + 1] - lut[j * 3 + 1]) * f + P.jitter[i * 3 + 1],
        lut[j * 3 + 2] + (lut[j2 * 3 + 2] - lut[j * 3 + 2]) * f + P.jitter[i * 3 + 2],
      );
      const fade = Math.min(1, P.phase[i] / 0.08, (1 - P.phase[i]) / 0.12);
      al.setX(i, visible ? fade * (0.35 + 0.65 * fn) : 0);
      const c = FLOWS[pi].kind === "insulin" ? insulinColor : marigold;
      tmpColor.copy(c);
      co.setXYZ(i, tmpColor.r, tmpColor.g, tmpColor.b);
    }
    pos.needsUpdate = true;
    al.needsUpdate = true;
    co.needsUpdate = true;

    const transitioning = mix.current !== target;
    // Render on demand: keep animating only while playing or crossfading (the rig adds rotation).
    if (L.playing || transitioning) invalidate();
  });

  const handlers = (part: BodyPart) => ({
    onClick: (e: ThreeEvent<MouseEvent>) => {
      e.stopPropagation();
      if (e.delta > 6) return;
      p.onSelect(part);
    },
    onDoubleClick: (e: ThreeEvent<MouseEvent>) => {
      e.stopPropagation();
      p.onFocus?.(part);
    },
    onPointerOver: (e: ThreeEvent<PointerEvent>) => {
      e.stopPropagation();
      document.body.style.cursor = "pointer";
    },
    onPointerOut: () => {
      document.body.style.cursor = "";
    },
  });

  const G = a.geos;
  const M = a.mats;
  return (
    <>
      {/* floor reflection */}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.001, 0]} material={a.floorMat} raycast={noRaycast} renderOrder={0}>
        <planeGeometry args={[1.5, 1.5]} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.002, 0]} material={a.ringMat} raycast={noRaycast} renderOrder={0}>
        <ringGeometry args={[0.5, 0.505, 96]} />
      </mesh>

      {/* inside: organs, vessels, muscles, flows (additive), drawn before the glass */}
      <mesh geometry={G.muscles} material={M.muscles} renderOrder={1} {...handlers("exercise_uptake")} />
      <mesh geometry={G.bloodVessels} material={M.vessels} renderOrder={2} {...handlers("blood")} />
      <mesh geometry={G.portalVessels} material={M.portal} renderOrder={2} {...handlers("gut_to_blood")} />
      <mesh geometry={G.intestine} material={M.intestine} renderOrder={3} {...handlers("intestine")} />
      <mesh geometry={G.pancreas} material={M.pancreas} renderOrder={3} {...handlers("pancreas")} />
      <mesh geometry={G.liver} material={M.liver} renderOrder={3} {...handlers("liver")} />
      <mesh geometry={G.stomach} material={M.stomach} renderOrder={4} {...handlers("stomach")} />
      <group position={HEART.c}>
        <mesh ref={heartRef} geometry={G.heart} renderOrder={4} material={M.heart} {...handlers("blood")} />
      </group>
      {a.halos.map((h, i) => (
        <mesh key={i} geometry={G.quad} position={h.pos} material={h.mat} renderOrder={5} raycast={noRaycast} frustumCulled={false} />
      ))}
      <points geometry={a.particles.geo} material={a.particles.mat} renderOrder={6} raycast={noRaycast} frustumCulled={false} />

      {/* glass: depth pre-pass, then the front surface only (no inner seams), then the aura */}
      <mesh geometry={G.shell} material={M.depth} renderOrder={10} raycast={noRaycast} />
      <mesh geometry={G.shell} material={M.glass} renderOrder={11} raycast={noRaycast} />
      <mesh geometry={G.shell} material={M.aura} renderOrder={12} raycast={noRaycast} scale={[1.07, 1.012, 1.1]} position={[0, -0.01, 0]} />

      <Labels labels={p.labels} selected={p.selected} onSelect={p.onSelect} compact={p.compact} presentation={p.presentation} a={a} />
    </>
  );
}

export default function BodyScene(p: SceneProps) {
  const lost = useRef(p.onContextLost);
  lost.current = p.onContextLost;
  return (
    <Canvas
      dpr={[1, 1.75]}
      frameloop={p.active ? "demand" : "never"}
      camera={{ fov: 32, near: 0.05, far: 40, position: sphericalPos(TARGET, p.compact ? DIST_COMPACT : DIST, POLAR, 0).toArray() as [number, number, number] }}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      onCreated={({ gl }) => {
        gl.setClearColor(0x000000, 0);
        gl.domElement.addEventListener("webglcontextlost", (e) => {
          e.preventDefault();
          lost.current?.();
        });
        gl.domElement.setAttribute("aria-label", p.ariaLabel);
        gl.domElement.setAttribute("role", "img");
      }}
      style={{ touchAction: p.compact ? "pan-y" : "none" }}
    >
      <OrbitControls
        makeDefault
        target={TARGET.toArray() as [number, number, number]}
        enableDamping
        dampingFactor={0.08}
        enablePan={false}
        rotateSpeed={0.7}
        zoomSpeed={0.8}
        minDistance={MIN_DIST}
        maxDistance={MAX_DIST}
        minPolarAngle={MIN_POLAR}
        maxPolarAngle={MAX_POLAR}
        autoRotate={!p.reducedMotion}
        autoRotateSpeed={0.55}
      />
      <Rig cmd={p.cmd} reducedMotion={p.reducedMotion} compact={p.compact} onInteract={p.onInteract} />
      <Body {...p} />
    </Canvas>
  );
}
