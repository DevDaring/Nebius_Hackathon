import * as THREE from "three";

/**
 * Additive light on a transparent canvas: colour is added, the canvas alpha is left alone, so the
 * glow composites over the page's night background instead of turning the body into a dark cut-out.
 */
export const ADDITIVE = {
  blending: THREE.CustomBlending,
  blendEquation: THREE.AddEquation,
  blendSrc: THREE.OneFactor,
  blendDst: THREE.OneFactor,
  blendSrcAlpha: THREE.ZeroFactor,
  blendDstAlpha: THREE.OneFactor,
  // built-in materials (sprites, floor) multiply their colour by alpha before it is added
  premultipliedAlpha: true,
} as const;

/** Cheap glass: fresnel rim + soft key-light sheen, no transmission pass (fast on phones and SwiftShader). */
export function glassMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthFunc: THREE.LessEqualDepth,
    uniforms: {
      uTint: { value: new THREE.Color("#5b6cc9") },
      uRim: { value: new THREE.Color("#cfd8ff") },
      uOpacity: { value: 1 },
      uTime: { value: 0 },
    },
    vertexShader: /* glsl */ `
      varying vec3 vN; varying vec3 vV; varying float vY;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal);
        vV = normalize(-mv.xyz);
        vY = position.y;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uTint; uniform vec3 uRim; uniform float uOpacity; uniform float uTime;
      varying vec3 vN; varying vec3 vV; varying float vY;
      void main() {
        vec3 n = normalize(vN); vec3 v = normalize(vV);
        float f = 1.0 - abs(dot(n, v));
        float rim = pow(f, 3.0);
        vec3 l = normalize(vec3(-0.45, 0.75, 0.55));
        float spec = pow(max(dot(reflect(-l, n), v), 0.0), 28.0) * 0.55;
        float spec2 = pow(max(dot(reflect(-normalize(vec3(0.6, -0.2, 0.4)), n), v), 0.0), 18.0) * 0.18;
        float sheen = 0.035 * smoothstep(0.35, 1.0, f) * (0.5 + 0.5 * sin(vY * 34.0 - uTime * 0.5));
        vec3 col = mix(uTint, uRim, rim) + vec3(spec + spec2) + sheen;
        float a = (0.018 + rim * 0.66 + spec * 0.55 + spec2 * 0.35 + sheen) * uOpacity;
        gl_FragColor = vec4(col, clamp(a, 0.0, 0.92));
        #include <colorspace_fragment>
      }`,
  });
}

/** Writes the glass body's depth only, so the glass shows its front surface without inner seams. */
export function depthOnlyMaterial() {
  return new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: true, transparent: true });
}

/** Faint outer aura (back faces, additive), for what the physiology model cannot explain. */
export function auraMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    ...ADDITIVE,
    side: THREE.BackSide,
    uniforms: { uColor: { value: new THREE.Color("#b9b2ff") }, uIntensity: { value: 0 }, uTime: { value: 0 } },
    vertexShader: /* glsl */ `
      varying vec3 vN; varying vec3 vV; varying float vY;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); vY = position.y;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor; uniform float uIntensity; uniform float uTime;
      varying vec3 vN; varying vec3 vV; varying float vY;
      void main() {
        float f = 1.0 - abs(dot(normalize(vN), normalize(vV)));
        float g = pow(f, 3.0) * uIntensity * (0.75 + 0.25 * sin(vY * 9.0 + uTime * 1.3));
        gl_FragColor = vec4(uColor * g * 0.9, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}

/**
 * Glowing organ. fillMode 0 = whole organ, 1 = filled from the bottom up to `uFill` (stomach),
 * 2 = filled along the tube's length (intestine).
 */
export function organMaterial(color: THREE.ColorRepresentation, fillMode: 0 | 1 | 2 = 0, yRange: [number, number] = [0, 1]) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    ...ADDITIVE,
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uIntensity: { value: 0 },
      uBase: { value: 0.16 },
      uCore: { value: 0.22 },
      uFill: { value: 0 },
      uFillMode: { value: fillMode },
      uYMin: { value: yRange[0] },
      uYMax: { value: yRange[1] },
      uTime: { value: 0 },
    },
    vertexShader: /* glsl */ `
      varying vec3 vN; varying vec3 vV; varying vec3 vP; varying float vU;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); vP = position; vU = uv.x;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor; uniform float uIntensity; uniform float uBase; uniform float uFill; uniform float uCore;
      uniform int uFillMode; uniform float uYMin; uniform float uYMax; uniform float uTime;
      varying vec3 vN; varying vec3 vV; varying vec3 vP; varying float vU;
      void main() {
        float f = 1.0 - abs(dot(normalize(vN), normalize(vV)));
        float rim = pow(f, 1.5);
        float shape = uCore + (1.0 - uCore) * rim;
        float lit;
        if (uFillMode == 1) {
          float level = mix(uYMin, uYMax, clamp(uFill, 0.0, 1.0)) + 0.0025 * sin(vP.x * 140.0 + uTime * 2.2);
          float m = smoothstep(level + 0.004, level - 0.004, vP.y);
          float line = (1.0 - smoothstep(0.0, 0.004, abs(vP.y - level))) * step(0.02, uFill);
          lit = uBase + uIntensity * (0.12 + 0.95 * m) + line * 0.7;
        } else if (uFillMode == 2) {
          float m = smoothstep(uFill + 0.03, uFill - 0.03, vU);
          float pulse = 0.85 + 0.15 * sin(vU * 160.0 - uTime * 3.0);
          lit = uBase + uIntensity * (0.1 + 0.95 * m * pulse);
        } else {
          lit = uBase + uIntensity * 0.9;
        }
        gl_FragColor = vec4(uColor * shape * lit, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}

/**
 * Soft round glow (a bloom look without a post-processing pass). billboard = faces the camera
 * (organ halos); otherwise a flat disc in its own plane (the floor reflection).
 */
export function glowMaterial(color: THREE.ColorRepresentation, billboard = true) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    ...ADDITIVE,
    uniforms: { uColor: { value: new THREE.Color(color) }, uOpacity: { value: 0 }, uSize: { value: 1 } },
    vertexShader: billboard
      ? /* glsl */ `
      uniform float uSize; varying vec2 vUv;
      void main() {
        vUv = uv;
        vec4 mv = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
        mv.xy += position.xy * uSize;
        gl_Position = projectionMatrix * mv;
      }`
      : /* glsl */ `
      varying vec2 vUv;
      void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor; uniform float uOpacity; varying vec2 vUv;
      void main() {
        float r = length(vUv - 0.5) * 2.0;
        float a = exp(-r * r * 4.0) * (1.0 - smoothstep(0.75, 1.0, r));
        gl_FragColor = vec4(uColor * a * uOpacity, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}

/** Flow particles: per-point colour and alpha, size attenuated with distance. */
export function particleMaterial(pixelRatio: number) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    ...ADDITIVE,
    uniforms: { uSize: { value: 0.017 }, uScale: { value: 600 * pixelRatio } },
    vertexShader: /* glsl */ `
      attribute float aAlpha; attribute vec3 aColor;
      uniform float uSize; uniform float uScale;
      varying float vA; varying vec3 vC;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = max(1.5, uSize * uScale / -mv.z);
        vA = aAlpha; vC = aColor;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      varying float vA; varying vec3 vC;
      void main() {
        vec2 d = gl_PointCoord - 0.5;
        float r = length(d);
        float a = smoothstep(0.5, 0.0, r);
        a = a * a * vA;
        if (a < 0.01) discard;
        gl_FragColor = vec4(vC * a * 1.15, 1.0);
        #include <colorspace_fragment>
      }`,
  });
}
