// Geometry and shaders of the sign-in animation: a stone statue of a dressed man (MakeHuman, CC0) posed
// on the twin's skeleton (src/body/anatomy.ts), so the stone dissolves into a glass copy of the same body.
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { MeshSurfaceSampler } from "three/examples/jsm/math/MeshSurfaceSampler.js";
import { ADDITIVE } from "@/body/three/materials";
import { FISH_BANDS, FISH_BODY, FISH_DORSAL, FISH_PECTORAL, FISH_TAIL } from "@/components/fishShape";

/* ---------------- shared GLSL ---------------- */
const NOISE = /* glsl */ `
  float hash3(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
  float vnoise(vec3 x) {
    vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash3(i), hash3(i + vec3(1.0, 0.0, 0.0)), f.x), mix(hash3(i + vec3(0.0, 1.0, 0.0)), hash3(i + vec3(1.0, 1.0, 0.0)), f.x), f.y),
               mix(mix(hash3(i + vec3(0.0, 0.0, 1.0)), hash3(i + vec3(1.0, 0.0, 1.0)), f.x), mix(hash3(i + vec3(0.0, 1.0, 1.0)), hash3(i + vec3(1.0, 1.0, 1.0)), f.x), f.y), f.z);
  }`;
/** Distance from the heart with a ragged, organic front (body-local coordinates). */
const REVEAL = /* glsl */ `
  uniform vec3 uRevC; uniform float uRevR;
  ${NOISE}
  float revDist(vec3 p) { return distance(p, uRevC) + (vnoise(p * 13.0) * 0.7 + vnoise(p * 43.0) * 0.3 - 0.5) * 0.16; }`;

const revealUniforms = (center: THREE.Vector3) => ({ uRevC: { value: center }, uRevR: { value: 0 } });

/* ---------------- the statue (MakeHuman CC0, built by scripts/landing/build_statue.py) ---------------- */
/** Mesh names in public/models/statue.json: the dressed statue parts and the bare body used as glass. */
export const STATUE_PARTS = ["body", "male_casualsuit01", "shoes01", "short02", "low-poly"] as const;
export type StatuePart = (typeof STATUE_PARTS)[number];
export type StatueGeos = Record<StatuePart | "glass", THREE.BufferGeometry>;

interface StatueManifest {
  bbox: [number[], number[]];
  meshes: Record<string, { vertices: string; indexOffset: number; indexCount: number }> & {
    _vertices: Record<string, { offset: number; count: number }>;
  };
}

/** Decode the compact binary: uint16-quantised positions and int16 normals per vertex set, uint16 indices. */
export function decodeStatue(man: StatueManifest, buf: ArrayBuffer): StatueGeos {
  const [lo, hi] = man.bbox;
  const sets: Record<string, { pos: THREE.BufferAttribute; nor: THREE.BufferAttribute }> = {};
  for (const [key, m] of Object.entries(man.meshes._vertices)) {
    const q = new Uint16Array(buf, m.offset, m.count * 3);
    const n = new Int16Array(buf, m.offset + m.count * 6, m.count * 3);
    const pos = new Float32Array(m.count * 3);
    const nor = new Float32Array(m.count * 3);
    for (let i = 0; i < pos.length; i++) {
      const ax = i % 3;
      pos[i] = lo[ax] + (q[i] / 65535) * (hi[ax] - lo[ax]);
      nor[i] = n[i] / 32767;
    }
    sets[key] = { pos: new THREE.BufferAttribute(pos, 3), nor: new THREE.BufferAttribute(nor, 3) };
  }
  const out = {} as StatueGeos;
  for (const name of [...STATUE_PARTS, "glass"] as const) {
    const m = man.meshes[name];
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", sets[m.vertices].pos);
    g.setAttribute("normal", sets[m.vertices].nor);
    g.setIndex(new THREE.BufferAttribute(new Uint16Array(buf, m.indexOffset, m.indexCount), 1));
    g.computeBoundingSphere();
    out[name] = g;
  }
  return out;
}

let statue: Promise<StatueGeos> | null = null;
/** Fetch the statue once per page (about 0.7 MB, cached by the browser). */
export function loadStatue(base = "/models/"): Promise<StatueGeos> {
  statue ??= Promise.all([
    fetch(`${base}statue.json`).then((r) => (r.ok ? (r.json() as Promise<StatueManifest>) : Promise.reject(new Error(`statue.json ${r.status}`)))),
    fetch(`${base}statue.bin`).then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(`statue.bin ${r.status}`)))),
  ]).then(([man, buf]) => decodeStatue(man, buf));
  statue.catch(() => (statue = null));
  return statue;
}

/** Points on the clothes and skin; they peel off as the dissolve front passes. */
export function dissolveDust(geos: StatueGeos, count: number) {
  const all = STATUE_PARTS.map((k) => geos[k]).map((g) => {
    return g.clone();
  });
  const merged = mergeGeometries(all, false);
  all.forEach((g) => g.dispose());
  const sampler = new MeshSurfaceSampler(new THREE.Mesh(merged)).build();
  const pos = new Float32Array(count * 3);
  const nor = new Float32Array(count * 3);
  const seed = new Float32Array(count);
  const p = new THREE.Vector3();
  const n = new THREE.Vector3();
  for (let i = 0; i < count; i++) {
    sampler.sample(p, n);
    pos.set([p.x, p.y, p.z], i * 3);
    nor.set([n.x, n.y, n.z], i * 3);
    seed[i] = Math.random();
  }
  merged.dispose();
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("aNormal", new THREE.BufferAttribute(nor, 3));
  g.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.9, 0), 1.4);
  return g;
}

/* ---------------- materials ---------------- */

/**
 * Carved marble under a night stage: wrapped key light (stone lets a little light through), cool fill,
 * sky ambient, a polished highlight, faint veins and a blue rim. Fragments inside the reveal radius are
 * discarded; the dissolve front glows like a scan edge.
 */
export function statueMaterial(color: string, center: THREE.Vector3, o: { veins?: number; polish?: number } = {}) {
  return new THREE.ShaderMaterial({
    uniforms: {
      ...revealUniforms(center),
      uColor: { value: new THREE.Color(color) },
      uVeins: { value: o.veins ?? 0.3 },
      uPolish: { value: o.polish ?? 0.22 },
      uEdge: { value: new THREE.Color("#8fd8ff") },
    },
    vertexShader: /* glsl */ `
      varying vec3 vL; varying vec3 vW; varying vec3 vN;
      void main() {
        vL = position;
        vec4 w = modelMatrix * vec4(position, 1.0);
        vW = w.xyz;
        vN = normalize(mat3(modelMatrix) * normal);
        gl_Position = projectionMatrix * viewMatrix * w;
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor; uniform float uVeins; uniform float uPolish; uniform vec3 uEdge;
      varying vec3 vL; varying vec3 vW; varying vec3 vN;
      ${REVEAL}
      float veins(vec3 p) {
        float n = vnoise(p * 5.0) * 0.6 + vnoise(p * 13.0) * 0.3 + vnoise(p * 29.0) * 0.1;
        float s = abs(sin((p.y * 3.1 + p.x * 1.7 + p.z * 0.9 + n * 4.5) * 3.14159));
        return pow(1.0 - s, 14.0);
      }
      void main() {
        float k = revDist(vL) - uRevR;
        if (uRevR > 0.0 && k < 0.0) discard;
        vec3 n = normalize(vN);
        vec3 v = normalize(cameraPosition - vW);
        if (dot(n, v) < 0.0) n = -n;
        vec3 key = normalize(vec3(-0.5, 0.78, 0.8));
        vec3 fill = normalize(vec3(0.85, 0.2, 0.45));
        float wrap = 0.35;
        float dk = max(0.0, (dot(n, key) + wrap) / (1.0 + wrap));
        float df = max(dot(n, fill), 0.0);
        float hemi = 0.5 + 0.5 * n.y;
        vec3 amb = mix(vec3(0.05, 0.065, 0.1), vec3(0.16, 0.19, 0.27), hemi);
        float grain = 0.95 + 0.05 * vnoise(vL * 60.0);
        vec3 base = mix(uColor * grain, uColor * vec3(0.66, 0.68, 0.72), veins(vL) * uVeins);
        vec3 col = base * (amb + vec3(1.0, 0.94, 0.86) * dk * 0.95 + vec3(0.4, 0.55, 0.9) * df * 0.32);
        vec3 h = normalize(key + v);
        col += vec3(1.0, 0.97, 0.92) * pow(max(dot(n, h), 0.0), 46.0) * uPolish;
        float f = 1.0 - max(dot(n, v), 0.0);
        col += vec3(1.0, 0.86, 0.72) * pow(f, 2.0) * 0.05;   // light scattering in the stone
        col += vec3(0.3, 0.6, 1.0) * pow(f, 3.2) * 0.55;      // stage rim light
        if (uRevR > 0.0) {
          float edge = 1.0 - smoothstep(0.0, 0.04, k);
          float grid = max(step(0.82, fract(vL.y * 120.0)), step(0.82, fract((vL.x + vL.z) * 120.0)));
          float near = 1.0 - smoothstep(0.0, 0.11, k);
          col = mix(col, uEdge * 1.9, edge * 0.92) + uEdge * near * grid * 0.55;
        }
        gl_FragColor = vec4(col, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}

/** Particles that leave the clothes at the dissolve front (and return when the person re-forms). */
export function dustMaterial(center: THREE.Vector3, pixelRatio: number) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    ...ADDITIVE,
    uniforms: { ...revealUniforms(center), uTime: { value: 0 }, uSize: { value: 0.011 }, uScale: { value: 620 * pixelRatio } },
    vertexShader: /* glsl */ `
      attribute vec3 aNormal; attribute float aSeed;
      uniform float uTime; uniform float uSize; uniform float uScale;
      varying float vA; varying float vS;
      ${REVEAL}
      void main() {
        float k = uRevR - revDist(position);
        float life = k / 0.34;
        vA = (uRevR > 0.0 && life > 0.0 && life < 1.0) ? smoothstep(0.0, 0.06, life) * (1.0 - life) : 0.0;
        vS = aSeed;
        vec3 p = position + aNormal * k * (0.22 + 0.34 * aSeed) + vec3(0.0, k * (0.16 + 0.3 * aSeed), 0.0);
        p.x += sin(aSeed * 40.0 + uTime * 2.3) * 0.06 * k;
        p.z += cos(aSeed * 31.0 + uTime * 1.9) * 0.06 * k;
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        gl_PointSize = vA > 0.0 ? max(1.0, uSize * (0.5 + aSeed) * uScale / -mv.z) : 0.0;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      varying float vA; varying float vS;
      void main() {
        float r = length(gl_PointCoord - 0.5);
        float a = smoothstep(0.5, 0.0, r);
        a = a * a * vA;
        if (a < 0.01) discard;
        vec3 c = mix(vec3(0.55, 0.85, 1.0), vec3(1.0, 0.93, 0.78), step(0.78, vS));
        gl_FragColor = vec4(c * a * 1.4, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}

/** Holographic glass skin of the twin: fresnel rim, fine scan lines and a slow rising light band. */
export function holoGlassMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthFunc: THREE.LessEqualDepth,
    uniforms: { uTime: { value: 0 }, uAmount: { value: 0 }, uTint: { value: new THREE.Color("#4f6fd8") }, uRim: { value: new THREE.Color("#cfe6ff") } },
    vertexShader: /* glsl */ `
      varying vec3 vN; varying vec3 vV; varying vec3 vL;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); vL = position;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform float uTime; uniform float uAmount; uniform vec3 uTint; uniform vec3 uRim;
      varying vec3 vN; varying vec3 vV; varying vec3 vL;
      void main() {
        float f = 1.0 - abs(dot(normalize(vN), normalize(vV)));
        float rim = pow(f, 2.4);
        float scan = smoothstep(0.9, 1.0, 0.5 + 0.5 * sin(vL.y * 260.0 - uTime * 2.0)) * 0.09;
        float band = exp(-pow((fract(vL.y * 0.42 - uTime * 0.11) - 0.5) * 12.0, 2.0));
        vec3 l = normalize(vec3(-0.45, 0.75, 0.55));
        float spec = pow(max(dot(reflect(-l, normalize(vN)), normalize(vV)), 0.0), 26.0) * 0.5;
        vec3 col = mix(uTint, uRim, rim) + vec3(spec) + band * 0.25 * vec3(0.6, 0.85, 1.0);
        float a = (0.025 + rim * 0.72 + scan * (0.3 + f) + band * 0.12 * f + spec * 0.5) * uAmount;
        gl_FragColor = vec4(col, clamp(a, 0.0, 0.92));
        #include <colorspace_fragment>
      }`,
  });
}

/** Glowing organ (additive fresnel), with an optional slow shimmer. */
export function glowOrganMaterial(color: string, core = 0.22, shimmer = 0) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    ...ADDITIVE,
    uniforms: { uColor: { value: new THREE.Color(color) }, uIntensity: { value: 0 }, uCore: { value: core }, uShimmer: { value: shimmer }, uTime: { value: 0 } },
    vertexShader: /* glsl */ `
      varying vec3 vN; varying vec3 vV; varying vec3 vP;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); vP = position;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor; uniform float uIntensity; uniform float uCore; uniform float uShimmer; uniform float uTime;
      varying vec3 vN; varying vec3 vV; varying vec3 vP;
      ${NOISE}
      void main() {
        float f = 1.0 - abs(dot(normalize(vN), normalize(vV)));
        float shape = uCore + (1.0 - uCore) * pow(f, 1.5);
        float sh = 1.0 + uShimmer * (vnoise(vP * 90.0 + vec3(0.0, uTime * 1.4, 0.0)) - 0.5) * 2.0;
        gl_FragColor = vec4(uColor * shape * uIntensity * sh, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}

/** Soft additive points with per-point colour and alpha (blood, glucose, insulin, neurons, trail). */
export function glowPointsMaterial(pixelRatio: number, size = 0.016) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    ...ADDITIVE,
    uniforms: { uSize: { value: size }, uScale: { value: 620 * pixelRatio } },
    vertexShader: /* glsl */ `
      attribute float aAlpha; attribute vec3 aColor; attribute float aSize;
      uniform float uSize; uniform float uScale;
      varying float vA; varying vec3 vC;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = aAlpha > 0.003 ? max(1.2, uSize * aSize * uScale / -mv.z) : 0.0;
        vA = aAlpha; vC = aColor;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      varying float vA; varying vec3 vC;
      void main() {
        float r = length(gl_PointCoord - 0.5);
        float a = smoothstep(0.5, 0.0, r);
        a = a * a * vA;
        if (a < 0.01) discard;
        gl_FragColor = vec4(vC * a * 1.25, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}

/** Billboard glow disc or expanding ring (heart flash, pulse wave). */
export function haloMaterial(color: string, ring = false) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: !ring,
    ...ADDITIVE,
    uniforms: { uColor: { value: new THREE.Color(color) }, uOpacity: { value: 0 }, uSize: { value: 1 }, uRadius: { value: 0.3 } },
    vertexShader: /* glsl */ `
      uniform float uSize; varying vec2 vUv;
      void main() {
        vUv = uv;
        vec4 mv = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
        mv.xy += position.xy * uSize;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: ring
      ? /* glsl */ `
      uniform vec3 uColor; uniform float uOpacity; uniform float uRadius; varying vec2 vUv;
      void main() {
        float r = length(vUv - 0.5);
        float a = exp(-pow((r - uRadius) * 38.0, 2.0)) + 0.35 * exp(-pow((r - uRadius * 0.86) * 18.0, 2.0));
        gl_FragColor = vec4(uColor * a * uOpacity, 1.0);
        #include <colorspace_fragment>
      }`
      : /* glsl */ `
      uniform vec3 uColor; uniform float uOpacity; varying vec2 vUv;
      void main() {
        float r = length(vUv - 0.5) * 2.0;
        float a = exp(-r * r * 4.0) * (1.0 - smoothstep(0.75, 1.0, r));
        gl_FragColor = vec4(uColor * a * uOpacity, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}

/** Faint outer aura of the twin (back faces). */
export function auraMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    ...ADDITIVE,
    side: THREE.BackSide,
    uniforms: { uColor: { value: new THREE.Color("#9fb7ff") }, uIntensity: { value: 0 }, uTime: { value: 0 }, uPush: { value: 0.014 } },
    vertexShader: /* glsl */ `
      uniform float uPush;
      varying vec3 vN; varying vec3 vV; varying float vY;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position + normal * uPush, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); vY = position.y;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor; uniform float uIntensity; uniform float uTime;
      varying vec3 vN; varying vec3 vV; varying float vY;
      void main() {
        float f = 1.0 - abs(dot(normalize(vN), normalize(vV)));
        float g = pow(f, 3.0) * uIntensity * (0.75 + 0.25 * sin(vY * 9.0 - uTime * 1.6));
        gl_FragColor = vec4(uColor * g, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}

/* ---------------- the clownfish of light ---------------- */
export const FISH_TEX = { w: 640, h: 400, scale: 4.4 };

/** The NemoTwins clownfish outline drawn as glowing light on a transparent canvas. */
export function fishTexture(): THREE.CanvasTexture {
  const { w, h, scale } = FISH_TEX;
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  // Software canvas: some GPU-accelerated 2-D canvases drop shadowed strokes drawn before a clip.
  const g = c.getContext("2d", { willReadFrequently: true });
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  if (!g) return tex;
  g.translate((w - 120 * scale) / 2, (h - 64 * scale) / 2);
  g.scale(scale, scale);
  const body = new Path2D(FISH_BODY);
  const outline = [new Path2D(FISH_TAIL), new Path2D(FISH_DORSAL), body, new Path2D(FISH_PECTORAL)];
  // a breath of volume inside the outline
  const fill = g.createLinearGradient(0, 10, 0, 54);
  fill.addColorStop(0, "rgba(130,205,255,0.20)");
  fill.addColorStop(1, "rgba(70,130,255,0.05)");
  g.fillStyle = fill;
  outline.forEach((p) => g.fill(p));
  const stroke = (paths: Path2D[], width: number, color: string, blur: number) => {
    g.save();
    g.shadowColor = color;
    g.shadowBlur = blur;
    g.strokeStyle = color;
    g.lineWidth = width;
    g.lineJoin = "round";
    g.lineCap = "round";
    paths.forEach((p) => g.stroke(p));
    g.restore();
  };
  stroke(outline, 2.2, "rgba(80,170,255,0.38)", 30);
  stroke(outline, 1.0, "rgba(150,215,255,0.85)", 12);
  stroke(outline, 0.42, "rgba(242,250,255,1)", 0);
  // the three pale bands, clipped to the body
  g.save();
  g.clip(body);
  const bands = FISH_BANDS.map((d) => new Path2D(d));
  g.fillStyle = "rgba(225,242,255,0.16)";
  bands.forEach((p) => g.fill(p));
  stroke(bands, 0.8, "rgba(160,220,255,0.75)", 10);
  stroke(bands, 0.32, "rgba(240,250,255,0.95)", 0);
  g.restore();
  // the eye
  g.save();
  g.shadowColor = "rgba(200,235,255,1)";
  g.shadowBlur = 14;
  g.fillStyle = "rgba(245,252,255,1)";
  g.beginPath();
  g.arc(103, 27, 2.6, 0, Math.PI * 2);
  g.fill();
  g.restore();
  tex.needsUpdate = true;
  return tex;
}

/** The fish plane: additive, drawn on top, with a swimming wave toward the tail. */
export function fishMaterial(map: THREE.Texture) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: false,
    ...ADDITIVE,
    uniforms: { uMap: { value: map }, uOpacity: { value: 0 }, uTime: { value: 0 }, uAmp: { value: 0.045 } },
    vertexShader: /* glsl */ `
      uniform float uTime; uniform float uAmp; varying vec2 vUv;
      void main() {
        vUv = uv;
        vec3 p = position;
        float tail = smoothstep(0.78, 0.05, uv.x);
        p.y += sin(uTime * 9.0 - uv.x * 7.5) * uAmp * tail * tail;
        p.y += sin(uTime * 4.5 - uv.x * 3.0) * uAmp * 0.25;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
      }`,
    fragmentShader: /* glsl */ `
      uniform sampler2D uMap; uniform float uOpacity; varying vec2 vUv;
      void main() {
        vec4 c = texture2D(uMap, vUv);
        gl_FragColor = vec4(c.rgb * c.a * uOpacity * 1.25, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}
