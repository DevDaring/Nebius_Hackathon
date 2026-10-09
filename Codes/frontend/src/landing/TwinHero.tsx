// Sign-in page animation (lazy chunk, WebGL only): a dressed person slowly revolves, a clownfish of
// light circles him and passes through his heart, and from there he dissolves into his glass
// digital twin - organs, blood, glucose and insulin flowing - before folding back into the person.
import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { FLOWS, HEAD, HEART, INTESTINE, LIVER, MUSCLES, PANCREAS, STOMACH, VESSELS } from "@/body/anatomy";
import { ellipsoidGeometry, limbGeometry, organTubeGeometry, pathLut, vesselGeometry } from "@/body/three/geometry";
import { depthOnlyMaterial, glowMaterial } from "@/body/three/materials";
import {
  FISH_TEX,
  auraMaterial,
  dissolveDust,
  dustMaterial,
  fishMaterial,
  fishTexture,
  glowOrganMaterial,
  glowPointsMaterial,
  haloMaterial,
  holoGlassMaterial,
  STATUE_PARTS,
  loadStatue,
  statueMaterial,
  type StatueGeos,
} from "./heroAssets";
import { FISH_KEYS, REVEAL_CENTER, START_AT, STILL_AT, fishOpacity, fishParam, pulseAt, revealAt, twinAmount } from "./timeline";

/** Where the figure stands, in canvas pixels: horizontal centre, top of the head, soles. */
export interface StageBox {
  x: number;
  top: number;
  bottom: number;
}

const FIT_LOW = -0.03;
const FIT_HIGH = 1.79;
const TILT = 0.075;
const SPIN = 0.2; // rad/s: one slow revolution every ~31 s
const BRAIN_Z = 0.02; // the statue's head sits a little forward of the spine
const noRaycast = () => undefined;

/* ---------------- assets ---------------- */
function build(pixelRatio: number, statue: StatueGeos) {
  const center = new THREE.Vector3(...REVEAL_CENTER);
  // One block of marble: skin polished, clothes a touch greyer, hair and shoes matte.
  const cloth: Record<(typeof STATUE_PARTS)[number], THREE.ShaderMaterial> = {
    body: statueMaterial("#efe9df", center, { polish: 0.26 }),
    male_casualsuit01: statueMaterial("#e4dfd6", center, { polish: 0.16 }),
    shoes01: statueMaterial("#dcd6cb", center, { polish: 0.2 }),
    short02: statueMaterial("#d6d0c5", center, { polish: 0.08, veins: 0.15 }),
    "low-poly": statueMaterial("#f2eee6", center, { polish: 0.3 }),
  };
  const dust = { geo: dissolveDust(statue, 2600), mat: dustMaterial(center, pixelRatio) };

  // The twin inside: the same body in glass, organs, vessels, spine, flows.
  const shell = statue.glass;
  const vesselsOf = (idx: number[]) => mergeGeometries(idx.map((i) => vesselGeometry(VESSELS[i].points, VESSELS[i].r * 1.15)), false);
  const vertebrae = mergeGeometries(
    Array.from({ length: 17 }, (_, i) => ellipsoidGeometry({ c: [0, 0.93 + i * 0.032, -0.074 + 0.012 * Math.sin(i / 3)], r: [0.017, 0.011, 0.014] }, 12, 8)),
    false,
  );
  const twin = {
    shell,
    heart: ellipsoidGeometry({ ...HEART, c: [0, 0, 0] }, 28, 20),
    lungR: ellipsoidGeometry({ c: [0.078, 1.275, -0.006], r: [0.058, 0.098, 0.056], rz: 0.08 }, 24, 18),
    lungL: ellipsoidGeometry({ c: [-0.078, 1.275, -0.006], r: [0.058, 0.098, 0.056], rz: -0.08 }, 24, 18),
    brain: ellipsoidGeometry({ c: [0, 1.612, BRAIN_Z], r: [0.062, 0.058, 0.07] }, 28, 20),
    stomach: organTubeGeometry(STOMACH, 96, 22),
    liver: organTubeGeometry(LIVER, 64, 24),
    pancreas: organTubeGeometry(PANCREAS, 48, 16),
    intestine: organTubeGeometry(INTESTINE, 420, 10, false),
    muscles: mergeGeometries(MUSCLES.map((m) => limbGeometry(m, 20)), false),
    arteries: vesselsOf([0, 1, 2, 3, 4, 5, 6]),
    veins: vesselsOf([7, 8]),
    portal: vesselsOf([9, 10]),
    spine: vertebrae,
  };
  const organ = {
    depth: depthOnlyMaterial(),
    glass: holoGlassMaterial(),
    aura: auraMaterial(),
    heart: glowOrganMaterial("#ff6b7a", 0.35),
    lungs: glowOrganMaterial("#7fb4ff", 0.12, 0.25),
    brain: glowOrganMaterial("#a78bfa", 0.2, 0.55),
    stomach: glowOrganMaterial("#f2a33a", 0.22),
    liver: glowOrganMaterial("#2bb3a3", 0.22),
    pancreas: glowOrganMaterial("#e9c88e", 0.22),
    intestine: glowOrganMaterial("#f2a33a", 0.18, 0.35),
    muscles: glowOrganMaterial("#5ea8ff", 0.04),
    arteries: glowOrganMaterial("#ff6b6b", 0.5),
    veins: glowOrganMaterial("#7d8cff", 0.5),
    portal: glowOrganMaterial("#f2a33a", 0.5),
    spine: glowOrganMaterial("#c9d6ff", 0.25),
  };

  // Flow particles: blood to the limbs (coral), glucose from the gut (gold), insulin (cream).
  const flowColor = (id: string) => new THREE.Color(id === "insulin" ? "#fff1d6" : id === "portal" || id === "hepatic" ? "#f7b24a" : "#ff7466");
  const luts = FLOWS.map((f) => pathLut(f.points, 160));
  const counts = FLOWS.map((f) => Math.round(f.count * 1.6));
  const nFlow = counts.reduce((s, c) => s + c, 0);
  const flowGeo = new THREE.BufferGeometry();
  const fPos = new Float32Array(nFlow * 3);
  const fAlpha = new Float32Array(nFlow);
  const fColor = new Float32Array(nFlow * 3);
  const fSize = new Float32Array(nFlow);
  const fPath = new Uint8Array(nFlow);
  const fPhase = new Float32Array(nFlow);
  const fSpeed = new Float32Array(nFlow);
  const fJit = new Float32Array(nFlow * 3);
  let k = 0;
  FLOWS.forEach((f, pi) => {
    const col = flowColor(f.id);
    for (let j = 0; j < counts[pi]; j++, k++) {
      fPath[k] = pi;
      fPhase[k] = (j * 0.618034) % 1;
      fSpeed[k] = 0.16 + Math.random() * 0.1;
      fSize[k] = 0.7 + Math.random() * 0.6;
      fColor.set([col.r, col.g, col.b], k * 3);
      for (let d = 0; d < 3; d++) fJit[k * 3 + d] = (Math.random() - 0.5) * 0.007;
    }
  });
  flowGeo.setAttribute("position", new THREE.BufferAttribute(fPos, 3).setUsage(THREE.DynamicDrawUsage));
  flowGeo.setAttribute("aAlpha", new THREE.BufferAttribute(fAlpha, 1).setUsage(THREE.DynamicDrawUsage));
  flowGeo.setAttribute("aColor", new THREE.BufferAttribute(fColor, 3));
  flowGeo.setAttribute("aSize", new THREE.BufferAttribute(fSize, 1));
  flowGeo.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.9, 0), 1.3);
  const flows = { geo: flowGeo, mat: glowPointsMaterial(pixelRatio, 0.017), luts, path: fPath, phase: fPhase, speed: fSpeed, jit: fJit, n: nFlow };

  // Neurons twinkling inside the brain.
  const nN = 70;
  const nPos = new Float32Array(nN * 3);
  const nSeed = new Float32Array(nN);
  for (let i = 0; i < nN; i++) {
    const u = new THREE.Vector3().randomDirection().multiplyScalar(Math.cbrt(Math.random()) * 0.85);
    nPos.set([u.x * 0.06, 1.612 + u.y * 0.055, BRAIN_Z + u.z * 0.066], i * 3);
    nSeed[i] = Math.random();
  }
  const neuronGeo = new THREE.BufferGeometry();
  neuronGeo.setAttribute("position", new THREE.BufferAttribute(nPos, 3));
  neuronGeo.setAttribute("aAlpha", new THREE.BufferAttribute(new Float32Array(nN), 1).setUsage(THREE.DynamicDrawUsage));
  neuronGeo.setAttribute("aColor", new THREE.BufferAttribute(new Float32Array(nN * 3).fill(0).map((_, i) => [0.82, 0.76, 1][i % 3]), 3));
  neuronGeo.setAttribute("aSize", new THREE.BufferAttribute(new Float32Array(nN).fill(0.8), 1));
  neuronGeo.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 1.6, 0), 0.2);
  const neurons = { geo: neuronGeo, mat: glowPointsMaterial(pixelRatio, 0.012), seed: nSeed, n: nN };

  // Halos and the pulse that leaves the heart.
  const quad = new THREE.PlaneGeometry(1, 1);
  const halos = {
    heart: haloMaterial("#ff7a85"),
    brain: haloMaterial("#a78bfa"),
    gut: haloMaterial("#f2a33a"),
    pulse: haloMaterial("#9fdcff", true),
  };
  const floor = glowMaterial(new THREE.Color("#5fb7ff"), false);
  const floorRing = new THREE.MeshBasicMaterial({ color: new THREE.Color("#b8d8ff"), transparent: true, opacity: 0.18, depthWrite: false, side: THREE.DoubleSide });
  const floorWave = new THREE.MeshBasicMaterial({ color: new THREE.Color("#9fdcff"), transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide });

  // The fish, its trail and the sparkles it sheds.
  const fishTex = fishTexture();
  const fish = { geo: new THREE.PlaneGeometry(1, 1, 40, 4), mat: fishMaterial(fishTex), tex: fishTex };
  const trailN = 40;
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(trailN * 3), 3).setUsage(THREE.DynamicDrawUsage));
  trailGeo.setAttribute("aAlpha", new THREE.BufferAttribute(new Float32Array(trailN), 1).setUsage(THREE.DynamicDrawUsage));
  trailGeo.setAttribute("aColor", new THREE.BufferAttribute(new Float32Array(trailN * 3).map((_, i) => [0.55, 0.85, 1][i % 3]), 3));
  trailGeo.setAttribute("aSize", new THREE.BufferAttribute(new Float32Array(trailN).map((_, i) => 1.5 * (1 - i / trailN) + 0.35), 1));
  const sparkN = 56;
  const sparkGeo = new THREE.BufferGeometry();
  sparkGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(sparkN * 3), 3).setUsage(THREE.DynamicDrawUsage));
  sparkGeo.setAttribute("aAlpha", new THREE.BufferAttribute(new Float32Array(sparkN), 1).setUsage(THREE.DynamicDrawUsage));
  sparkGeo.setAttribute("aColor", new THREE.BufferAttribute(new Float32Array(sparkN * 3).map((_, i) => (Math.floor(i / 3) % 5 === 0 ? [1, 0.9, 0.72] : [0.7, 0.9, 1])[i % 3]), 3));
  sparkGeo.setAttribute("aSize", new THREE.BufferAttribute(new Float32Array(sparkN).map(() => 0.5 + Math.random() * 0.9), 1));
  const trail = {
    geo: trailGeo,
    spark: sparkGeo,
    mat: glowPointsMaterial(pixelRatio, 0.02),
    sparkMat: glowPointsMaterial(pixelRatio, 0.014),
    hist: Array.from({ length: trailN }, () => new THREE.Vector3(0, -10, 0)),
    sp: Array.from({ length: sparkN }, () => ({ p: new THREE.Vector3(0, -10, 0), v: new THREE.Vector3(), age: Math.random() * 2, life: 1 })),
  };
  [trailGeo, sparkGeo].forEach((g) => (g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 1, 0), 10)));

  const fishCurve = new THREE.CatmullRomCurve3(
    FISH_KEYS.map(([, x, y, z]) => new THREE.Vector3(x, y, z)),
    false,
    "centripetal",
  );

  const dispose = () => {
    // statue geometries are shared (module cache): the renderer re-uploads them if the scene mounts again
    Object.values(cloth).forEach((m) => m.dispose());
    dust.geo.dispose();
    dust.mat.dispose();
    Object.entries(twin).forEach(([k, g]) => k !== "shell" && g.dispose());
    Object.values(organ).forEach((m) => m.dispose());
    [flowGeo, neuronGeo, trailGeo, sparkGeo, quad, fish.geo].forEach((g) => g.dispose());
    [flows.mat, neurons.mat, trail.mat, trail.sparkMat, fish.mat, floor, floorRing, floorWave, ...Object.values(halos)].forEach((m) => m.dispose());
    fishTex.dispose();
  };
  return { center, statue, cloth, dust, twin, organ, flows, neurons, quad, halos, floor, floorRing, floorWave, fish, trail, fishCurve, dispose };
}
type Assets = ReturnType<typeof build>;

/* ---------------- camera: fit the figure into the stage box ---------------- */
function fitCamera(camera: THREE.PerspectiveCamera, w: number, h: number, box: StageBox) {
  const span = Math.max(60, box.bottom - box.top);
  const worldH = ((FIT_HIGH - FIT_LOW) * h) / span;
  const dist = worldH / (2 * Math.tan((camera.fov * Math.PI) / 360));
  const mid = (FIT_LOW + FIT_HIGH) / 2;
  camera.position.set(0, mid + Math.sin(TILT) * dist, Math.cos(TILT) * dist);
  camera.lookAt(0, mid, 0);
  camera.setViewOffset(w, h, w / 2 - box.x, h / 2 - (box.top + box.bottom) / 2, w, h);
  camera.updateProjectionMatrix();
}

/** Rough half-width of the body at height y (to dim the fish while it swims behind him). */
const halfWidth = (y: number) => (y > 1.47 ? 0.1 : y > 0.74 ? 0.27 : 0.17);
const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

/* ---------------- the scene ---------------- */
function Scene({
  box,
  boxKey,
  reducedMotion,
  stillAt,
  statue,
  onFirstFrame,
}: {
  box: React.MutableRefObject<StageBox | null>;
  boxKey: number;
  reducedMotion: boolean;
  stillAt: number | null;
  statue: StatueGeos;
  onFirstFrame?: () => void;
}) {
  const gl = useThree((s) => s.gl);
  const invalidate = useThree((s) => s.invalidate);
  const a: Assets = useMemo(() => build(gl.getPixelRatio(), statue), [gl, statue]);
  const clock = useRef<number | null>(null);
  const first = useRef(onFirstFrame);
  first.current = onFirstFrame;
  useEffect(() => () => a.dispose(), [a]);
  useEffect(() => invalidate(), [boxKey, invalidate]);

  const body = useRef<THREE.Group>(null);
  const heart = useRef<THREE.Group>(null);
  const lungs = useRef<THREE.Group>(null);
  const fishMesh = useRef<THREE.Mesh>(null);
  const heartHalo = useRef<THREE.Mesh>(null);
  const wave = useRef<THREE.Mesh>(null);
  const tmp = useMemo(
    () => ({ p: new THREE.Vector3(), prev: new THREE.Vector3(), n1: new THREE.Vector3(), n2: new THREE.Vector3(), dir: new THREE.Vector3(), q: new THREE.Quaternion(), z: new THREE.Vector3(0, 0, 1), tail: new THREE.Vector3() }),
    [],
  );
  const fishState = useRef({ angle: 0, flip: 1, flipS: 1, init: false });
  const heartColor = useMemo(() => ({ beat: new THREE.Color("#ff7a85"), flash: new THREE.Color("#9fdcff") }), []);
  const floorColor = useMemo(() => ({ human: new THREE.Color("#ffcf8a"), twin: new THREE.Color("#5fd0ff") }), []);

  useFrame((state, delta) => {
    const dt = Math.min(delta, 0.05);
    // The loop clock starts at the first frame on screen and advances by capped frame time, so a slow
    // first frame (shaders compiling) or a hiccup slows the story briefly instead of skipping it.
    if (clock.current === null) {
      clock.current = START_AT;
      first.current?.();
    } else clock.current += Math.min(delta, 0.1);
    const t = stillAt ?? (reducedMotion ? STILL_AT : clock.current);
    const { camera, size } = state;
    const cam = camera as THREE.PerspectiveCamera;
    fitCamera(cam, size.width, size.height, box.current ?? { x: size.width / 2, top: size.height * 0.06, bottom: size.height * 0.94 });

    const R = revealAt(t);
    const tw = twinAmount(t);
    const time = state.clock.elapsedTime;
    if (body.current) body.current.rotation.y = reducedMotion ? 0.55 : -0.35 + t * SPIN;

    // dissolve
    for (const m of Object.values(a.cloth)) m.uniforms.uRevR.value = R;
    a.dust.mat.uniforms.uRevR.value = R;
    a.dust.mat.uniforms.uTime.value = time;

    // twin
    const O = a.organ;
    const beat = reducedMotion ? 0.4 : Math.pow(Math.max(0, Math.sin(time * Math.PI * 2 * 1.05)), 8);
    const breath = reducedMotion ? 0 : Math.sin(time * 1.25);
    const show = Math.pow(tw, 0.6);
    O.glass.uniforms.uTime.value = time;
    O.glass.uniforms.uAmount.value = 0.35 + 0.65 * show;
    O.aura.uniforms.uTime.value = time;
    O.aura.uniforms.uIntensity.value = 0.55 * smooth(0.82, 1, tw);
    O.heart.uniforms.uIntensity.value = show * (0.75 + 0.5 * beat);
    O.lungs.uniforms.uIntensity.value = show * (0.3 + 0.06 * breath);
    O.brain.uniforms.uIntensity.value = show * 0.55;
    O.stomach.uniforms.uIntensity.value = show * 0.6;
    O.liver.uniforms.uIntensity.value = show * 0.6;
    O.pancreas.uniforms.uIntensity.value = show * 0.5;
    O.intestine.uniforms.uIntensity.value = show * 0.42;
    O.muscles.uniforms.uIntensity.value = show * 0.1;
    O.arteries.uniforms.uIntensity.value = show * (0.5 + 0.2 * beat);
    O.veins.uniforms.uIntensity.value = show * 0.45;
    O.portal.uniforms.uIntensity.value = show * 0.5;
    O.spine.uniforms.uIntensity.value = show * 0.26;
    for (const m of [O.brain, O.lungs, O.intestine]) m.uniforms.uTime.value = time;
    if (heart.current) heart.current.scale.setScalar(1 + 0.08 * beat);
    if (lungs.current) lungs.current.scale.set(1 + 0.025 * breath, 1 + 0.035 * breath, 1 + 0.03 * breath);

    // pulse from the heart when the fish passes through
    const pulse = reducedMotion ? null : pulseAt(t);
    const H = a.halos;
    const flash = pulse !== null ? Math.pow(1 - pulse, 3) : 0;
    H.heart.uniforms.uOpacity.value = show * (0.28 + 0.35 * beat) + 0.75 * flash;
    H.heart.uniforms.uSize.value = 0.26 + 0.08 * beat + 0.16 * flash;
    H.heart.uniforms.uColor.value.copy(heartColor.beat).lerp(heartColor.flash, flash);
    H.brain.uniforms.uOpacity.value = show * 0.2;
    H.brain.uniforms.uSize.value = 0.3;
    H.gut.uniforms.uOpacity.value = show * 0.16;
    H.gut.uniforms.uSize.value = 0.42;
    H.pulse.uniforms.uOpacity.value = pulse !== null ? 0.8 * Math.pow(1 - pulse, 1.6) * Math.min(1, pulse * 8) : 0;
    H.pulse.uniforms.uRadius.value = 0.03 + (pulse ?? 0) * 0.46;
    H.pulse.uniforms.uSize.value = 3.2;
    if (wave.current) {
      const p = pulse ?? 0;
      wave.current.scale.setScalar(0.3 + p * 1.6);
      a.floorWave.opacity = pulse !== null ? 0.5 * (1 - p) : 0;
    }
    a.floor.uniforms.uColor.value.copy(floorColor.human).lerp(floorColor.twin, tw);
    a.floor.uniforms.uOpacity.value = 0.42 + 0.25 * tw;

    // flows
    const F = a.flows;
    const fp = F.geo.attributes.position as THREE.BufferAttribute;
    const fa = F.geo.attributes.aAlpha as THREE.BufferAttribute;
    for (let i = 0; i < F.n; i++) {
      if (!reducedMotion) F.phase[i] = (F.phase[i] + dt * F.speed[i] * (1 + 0.6 * beat)) % 1;
      const lut = F.luts[F.path[i]];
      const nPts = lut.length / 3 - 1;
      const x = F.phase[i] * nPts;
      const j = Math.floor(x);
      const f = x - j;
      const j2 = Math.min(nPts, j + 1);
      fp.setXYZ(
        i,
        lut[j * 3] + (lut[j2 * 3] - lut[j * 3]) * f + F.jit[i * 3],
        lut[j * 3 + 1] + (lut[j2 * 3 + 1] - lut[j * 3 + 1]) * f + F.jit[i * 3 + 1],
        lut[j * 3 + 2] + (lut[j2 * 3 + 2] - lut[j * 3 + 2]) * f + F.jit[i * 3 + 2],
      );
      const fade = Math.min(1, F.phase[i] / 0.06, (1 - F.phase[i]) / 0.1);
      fa.setX(i, show * fade * 0.95);
    }
    fp.needsUpdate = true;
    fa.needsUpdate = true;
    const na = a.neurons.geo.attributes.aAlpha as THREE.BufferAttribute;
    for (let i = 0; i < a.neurons.n; i++) {
      const s = a.neurons.seed[i];
      na.setX(i, show * (0.15 + 0.85 * Math.pow(Math.max(0, Math.sin(time * (1.5 + s * 2.5) + s * 40)), 10)));
    }
    na.needsUpdate = true;

    // fish
    const fm = fishMesh.current;
    if (fm) {
      const st = fishState.current;
      a.fishCurve.getPoint(fishParam(t), tmp.p);
      tmp.p.y += Math.sin(t * 2.4) * 0.018;
      tmp.p.x += Math.sin(t * 1.7 + 1) * 0.012;
      if (!st.init) {
        a.fishCurve.getPoint(fishParam(t - 0.05), tmp.prev);
        st.init = true;
      }
      // heading on screen
      tmp.n1.copy(tmp.prev).project(cam);
      tmp.n2.copy(tmp.p).project(cam);
      const aspect = size.width / Math.max(1, size.height);
      const dx = (tmp.n2.x - tmp.n1.x) * aspect;
      const dy = tmp.n2.y - tmp.n1.y;
      const moving = Math.hypot(dx, dy) > 1e-5;
      if (moving && Math.abs(dx) > 0.15 * Math.abs(dy) + 1e-5) st.flip = dx < 0 ? -1 : 1;
      if (moving) {
        const target = st.flip > 0 ? Math.atan2(dy, dx) : Math.atan2(-dy, -dx);
        const clamped = Math.max(-0.75, Math.min(0.75, target));
        st.angle += (clamped - st.angle) * (reducedMotion ? 1 : Math.min(1, dt * 5));
      }
      st.flipS += (st.flip - st.flipS) * (reducedMotion ? 1 : Math.min(1, dt * 4));
      fm.position.copy(tmp.p);
      tmp.q.setFromAxisAngle(tmp.z, st.angle);
      fm.quaternion.copy(cam.quaternion).multiply(tmp.q);
      const fw = 0.29 * (FISH_TEX.w / (120 * FISH_TEX.scale));
      fm.scale.set(fw * (Math.abs(st.flipS) < 0.08 ? Math.sign(st.flipS || 1) * 0.08 : st.flipS), (fw * FISH_TEX.h) / FISH_TEX.w, 1);
      // dim while behind the dressed body; fade at the canvas edges
      const behind = smooth(0.0, -0.14, tmp.p.z) * (1 - smooth(halfWidth(tmp.p.y), halfWidth(tmp.p.y) + 0.1, Math.abs(tmp.p.x))) * (tmp.p.y < 1.75 ? 1 : 0);
      const edge = smooth(1.02, 0.8, Math.abs(tmp.n2.x)) * smooth(1.02, 0.86, Math.abs(tmp.n2.y));
      const op = fishOpacity(t) * (1 - 0.82 * behind * (1 - tw)) * edge * (0.88 + 0.12 * Math.sin(time * 2.3));
      a.fish.mat.uniforms.uOpacity.value = op;
      a.fish.mat.uniforms.uTime.value = time;
      // trail from the tail
      tmp.dir.copy(tmp.p).sub(tmp.prev);
      if (tmp.dir.lengthSq() > 1e-10) tmp.dir.normalize();
      tmp.tail.copy(tmp.p).addScaledVector(tmp.dir, -0.11);
      const T = a.trail;
      if (!reducedMotion) {
        const v = T.hist.pop();
        if (v) T.hist.unshift(v.copy(tmp.tail));
      } else T.hist.forEach((h, i) => h.copy(tmp.tail).addScaledVector(tmp.dir, -0.012 * i));
      const tp = T.geo.attributes.position as THREE.BufferAttribute;
      const ta = T.geo.attributes.aAlpha as THREE.BufferAttribute;
      T.hist.forEach((h, i) => {
        tp.setXYZ(i, h.x, h.y, h.z);
        ta.setX(i, op * 0.5 * Math.pow(1 - i / T.hist.length, 1.7));
      });
      tp.needsUpdate = true;
      ta.needsUpdate = true;
      const sp = T.spark.attributes.position as THREE.BufferAttribute;
      const sa = T.spark.attributes.aAlpha as THREE.BufferAttribute;
      T.sp.forEach((s, i) => {
        s.age += dt;
        if (s.age > s.life && !reducedMotion) {
          s.age = 0;
          s.life = 1.1 + Math.random() * 1.3;
          s.p.copy(tmp.tail).add(new THREE.Vector3((Math.random() - 0.5) * 0.05, (Math.random() - 0.5) * 0.05, (Math.random() - 0.5) * 0.05));
          s.v.set((Math.random() - 0.5) * 0.08, 0.02 + Math.random() * 0.05, (Math.random() - 0.5) * 0.08).addScaledVector(tmp.dir, -0.04);
        }
        s.p.addScaledVector(s.v, dt);
        const life = Math.min(1, s.age / s.life);
        sp.setXYZ(i, s.p.x, s.p.y, s.p.z);
        sa.setX(i, op * 0.85 * Math.sin(Math.PI * life) * (0.6 + 0.4 * Math.sin(time * 9 + i)));
      });
      sp.needsUpdate = true;
      sa.needsUpdate = true;
      tmp.prev.copy(tmp.p);
    }
  });

  const T = a.twin;
  const O = a.organ;
  const C = a.cloth;
  return (
    <>
      {/* floor */}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.001, 0]} material={a.floor} raycast={noRaycast}>
        <planeGeometry args={[1.7, 1.7]} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.002, 0]} material={a.floorRing} raycast={noRaycast}>
        <ringGeometry args={[0.52, 0.526, 120]} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.002, 0]} material={a.floorRing} raycast={noRaycast}>
        <ringGeometry args={[0.7, 0.703, 120]} />
      </mesh>
      <mesh ref={wave} rotation-x={-Math.PI / 2} position={[0, 0.003, 0]} material={a.floorWave} raycast={noRaycast}>
        <ringGeometry args={[0.5, 0.515, 120]} />
      </mesh>

      <group ref={body}>
        {/* the statue (opaque stone, dissolves from the heart outward) */}
        {STATUE_PARTS.map((k) => (
          <mesh key={k} geometry={a.statue[k]} material={C[k]} raycast={noRaycast} />
        ))}

        {/* the twin inside (additive light, then the glass front surface) */}
        <mesh geometry={T.muscles} material={O.muscles} renderOrder={1} raycast={noRaycast} />
        <mesh geometry={T.spine} material={O.spine} renderOrder={1} raycast={noRaycast} />
        <group ref={lungs} position={[0, 1.275, 0]}>
          <group position={[0, -1.275, 0]}>
            <mesh geometry={T.lungR} material={O.lungs} renderOrder={1} raycast={noRaycast} />
            <mesh geometry={T.lungL} material={O.lungs} renderOrder={1} raycast={noRaycast} />
          </group>
        </group>
        <mesh geometry={T.arteries} material={O.arteries} renderOrder={2} raycast={noRaycast} />
        <mesh geometry={T.veins} material={O.veins} renderOrder={2} raycast={noRaycast} />
        <mesh geometry={T.portal} material={O.portal} renderOrder={2} raycast={noRaycast} />
        <mesh geometry={T.intestine} material={O.intestine} renderOrder={3} raycast={noRaycast} />
        <mesh geometry={T.pancreas} material={O.pancreas} renderOrder={3} raycast={noRaycast} />
        <mesh geometry={T.liver} material={O.liver} renderOrder={3} raycast={noRaycast} />
        <mesh geometry={T.stomach} material={O.stomach} renderOrder={3} raycast={noRaycast} />
        <mesh geometry={T.brain} material={O.brain} renderOrder={3} raycast={noRaycast} />
        <group ref={heart} position={HEART.c}>
          <mesh geometry={T.heart} material={O.heart} renderOrder={4} raycast={noRaycast} />
        </group>
        <mesh ref={heartHalo} geometry={a.quad} material={a.halos.heart} position={[HEART.c[0], HEART.c[1], HEART.c[2] + 0.02]} renderOrder={5} raycast={noRaycast} frustumCulled={false} />
        <mesh geometry={a.quad} material={a.halos.brain} position={[0, HEAD.c[1] + 0.02, 0]} renderOrder={5} raycast={noRaycast} frustumCulled={false} />
        <mesh geometry={a.quad} material={a.halos.gut} position={[0.01, 1.0, 0.03]} renderOrder={5} raycast={noRaycast} frustumCulled={false} />
        <points geometry={a.flows.geo} material={a.flows.mat} renderOrder={6} raycast={noRaycast} frustumCulled={false} />
        <points geometry={a.neurons.geo} material={a.neurons.mat} renderOrder={6} raycast={noRaycast} frustumCulled={false} />
        <mesh geometry={T.shell} material={O.depth} renderOrder={10} raycast={noRaycast} />
        <mesh geometry={T.shell} material={O.glass} renderOrder={11} raycast={noRaycast} />
        <mesh geometry={T.shell} material={O.aura} renderOrder={12} raycast={noRaycast} />

        {/* dust leaving the clothes at the dissolve front */}
        <points geometry={a.dust.geo} material={a.dust.mat} renderOrder={13} raycast={noRaycast} frustumCulled={false} />
      </group>

      {/* pulse wave and the fish of light (always on top) */}
      <mesh geometry={a.quad} material={a.halos.pulse} position={REVEAL_CENTER} renderOrder={20} raycast={noRaycast} frustumCulled={false} />
      <points geometry={a.trail.geo} material={a.trail.mat} renderOrder={21} raycast={noRaycast} frustumCulled={false} />
      <points geometry={a.trail.spark} material={a.trail.sparkMat} renderOrder={21} raycast={noRaycast} frustumCulled={false} />
      <mesh ref={fishMesh} geometry={a.fish.geo} material={a.fish.mat} renderOrder={22} raycast={noRaycast} frustumCulled={false} />
    </>
  );
}

export default function TwinHero({
  box,
  boxKey,
  reducedMotion,
  stillAt = null,
  onReady,
  onLost,
}: {
  box: React.MutableRefObject<StageBox | null>;
  boxKey: number;
  reducedMotion: boolean;
  /** Freeze the loop at this time (seconds), e.g. for screenshots. */
  stillAt?: number | null;
  onReady?: () => void;
  onLost?: () => void;
}) {
  const lost = useRef(onLost);
  lost.current = onLost;
  const [statue, setStatue] = useState<StatueGeos | null>(null);
  useEffect(() => {
    let live = true;
    loadStatue().then(
      (g) => live && setStatue(g),
      () => live && lost.current?.(),
    );
    return () => {
      live = false;
    };
  }, []);
  if (!statue) return null;
  return (
    <Canvas
      dpr={[1, 1.5]}
      frameloop={reducedMotion || stillAt !== null ? "demand" : "always"}
      camera={{ fov: 24, near: 0.1, far: 80, position: [0, 1, 8] }}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      onCreated={({ gl }) => {
        gl.setClearColor(0x000000, 0);
        gl.domElement.addEventListener("webglcontextlost", (e) => {
          e.preventDefault();
          lost.current?.();
        });
      }}
      style={{ pointerEvents: "none" }}
      aria-hidden
    >
      <Scene box={box} boxKey={boxKey} reducedMotion={reducedMotion || stillAt !== null} stillAt={stillAt} statue={statue} onFirstFrame={onReady} />
    </Canvas>
  );
}
