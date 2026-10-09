import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { HEAD, SHELL_ELLIPSOIDS, SHELL_LIMBS, TORSO_DEPTH, TORSO_PROFILE, type Ellipsoid, type Limb, type TubeSpec, type V3 } from "../anatomy";

const v3 = (p: V3) => new THREE.Vector3(p[0], p[1], p[2]);
const UP = new THREE.Vector3(0, 1, 0);

/** Tapered capsule (lathe with hemispherical ends) from a to b. */
export function limbGeometry(l: Limb, radial = 28): THREE.BufferGeometry {
  const a = v3(l.a);
  const b = v3(l.b);
  const len = a.distanceTo(b);
  const pts: THREE.Vector2[] = [];
  const cap = 8;
  for (let i = 0; i <= cap; i++) {
    const th = -Math.PI / 2 + (i / cap) * (Math.PI / 2);
    pts.push(new THREE.Vector2(Math.max(1e-4, l.ra * Math.cos(th)), l.ra * Math.sin(th)));
  }
  const mid = 6;
  for (let i = 1; i < mid; i++) {
    const u = i / mid;
    pts.push(new THREE.Vector2(l.ra + (l.rb - l.ra) * u, len * u));
  }
  for (let i = 0; i <= cap; i++) {
    const th = (i / cap) * (Math.PI / 2);
    pts.push(new THREE.Vector2(Math.max(1e-4, l.rb * Math.cos(th)), len + l.rb * Math.sin(th)));
  }
  const g = new THREE.LatheGeometry(pts, radial);
  const q = new THREE.Quaternion().setFromUnitVectors(UP, b.clone().sub(a).normalize());
  g.applyQuaternion(q);
  g.translate(a.x, a.y, a.z);
  return g;
}

export function ellipsoidGeometry(e: Ellipsoid, w = 32, h = 22): THREE.BufferGeometry {
  const g = new THREE.SphereGeometry(1, w, h);
  g.scale(e.r[0], e.r[1], e.r[2]);
  if (e.rz) g.rotateZ(e.rz);
  g.translate(e.c[0], e.c[1], e.c[2]);
  return g;
}

function torsoGeometry(): THREE.BufferGeometry {
  const spline = new THREE.SplineCurve(TORSO_PROFILE.map(([r, y]) => new THREE.Vector2(r, y)));
  const pts = spline.getPoints(64).map((p) => new THREE.Vector2(Math.max(1e-4, p.x), p.y));
  const g = new THREE.LatheGeometry(pts, 64);
  g.scale(1, 1, TORSO_DEPTH);
  return g;
}

/** The glass silhouette: torso, head, neck, limbs, hands and feet merged into one geometry. */
export function bodyShellGeometry(): THREE.BufferGeometry {
  const parts = [torsoGeometry(), ...SHELL_ELLIPSOIDS.map((e) => ellipsoidGeometry(e, e === HEAD ? 40 : 28, e === HEAD ? 28 : 18)), ...SHELL_LIMBS.map((l) => limbGeometry(l))];
  const merged = mergeGeometries(parts, false);
  parts.forEach((p) => p.dispose());
  merged.computeBoundingSphere();
  return merged;
}

export function curveOf(points: V3[]): THREE.CatmullRomCurve3 {
  return new THREE.CatmullRomCurve3(points.map(v3), false, "catmullrom", 0.5);
}

/** Tube whose radius varies along its length (organs), optionally flattened and closed at the ends. */
export function organTubeGeometry(spec: TubeSpec, segs = 96, radial = 20, closeEnds = true): THREE.BufferGeometry {
  const curve = curveOf(spec.points);
  const g = new THREE.TubeGeometry(curve, segs, 1, radial, false);
  const pos = g.attributes.position as THREE.BufferAttribute;
  const c = new THREE.Vector3();
  const p = new THREE.Vector3();
  const squash = spec.squashY ?? 1;
  for (let i = 0; i <= segs; i++) {
    const u = i / segs;
    curve.getPointAt(u, c);
    const end = closeEnds ? Math.pow(Math.sin(Math.PI * (0.015 + 0.97 * u)), 0.32) : 1;
    const r = spec.radius(u) * end;
    for (let j = 0; j <= radial; j++) {
      const k = i * (radial + 1) + j;
      p.fromBufferAttribute(pos, k).sub(c).multiplyScalar(r);
      p.y *= squash;
      pos.setXYZ(k, c.x + p.x, c.y + p.y, c.z + p.z);
    }
  }
  pos.needsUpdate = true;
  g.computeVertexNormals();
  g.computeBoundingBox();
  return g;
}

export function vesselGeometry(points: V3[], r: number): THREE.BufferGeometry {
  return new THREE.TubeGeometry(curveOf(points), 72, r, 6, false);
}

/** Equal-arc-length look-up table for moving particles along a path. */
export function pathLut(points: V3[], n = 120): Float32Array {
  const pts = curveOf(points).getSpacedPoints(n);
  const out = new Float32Array((n + 1) * 3);
  pts.forEach((q, i) => out.set([q.x, q.y, q.z], i * 3));
  return out;
}
