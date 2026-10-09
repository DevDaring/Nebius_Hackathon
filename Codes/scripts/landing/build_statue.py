#!/usr/bin/env python3
"""Build the sign-in page statue (frontend/public/models/statue.{json,bin}) from MakeHuman CC0 assets.

A man of about 52, dressed in a shirt, jeans and leather shoes, posed so that his bones follow the
twin's procedural skeleton (frontend/src/body/anatomy.ts): the stone statue dissolves into a glass
copy of the same body with the twin's organs inside.

Inputs (all CC0 1.0, MakeHuman; not stored in this repository):
  * base mesh, skeleton, skin weights and macro targets from https://github.com/makehumancommunity/makehuman
    (makehuman/data/3dobjs/base.obj, rigs/default.mhskel, rigs/default_weights.mhw, targets/macrodetails/*)
  * clothes, hair and eyes from the MakeHuman system assets pack
    https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip

Usage:  python3.12 scripts/landing/build_statue.py <makehuman core dir> <system assets dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend" / "public" / "models"

AGE_OLD = (52 - 25) / (90 - 25)  # MakeHuman age: young = 25 y, old = 90 y
RACES = {"caucasian": 0.5, "asian": 0.25, "african": 0.25}
HEIGHT_M = 1.70
# Each limb bone is aimed at the twin's next joint (anatomy.ts SHELL_LIMBS, metres, +x side; -x mirrored):
# upper arm -> elbow, forearm -> wrist, thigh -> knee, shin -> ankle.
TWIN_AIM = {
    "upperarm01": (0.246, 1.09, -0.012),
    "lowerarm01": (0.292, 0.84, 0.018),
    "upperleg01": (0.095, 0.49, 0.006),
    "lowerleg01": (0.102, 0.075, -0.012),
}
CHAIN_END = {"upperarm01": "lowerarm01", "lowerarm01": "wrist", "upperleg01": "lowerleg01", "lowerleg01": "foot"}
SOCK_TOP_M = 0.11  # shoe-asset socks above this height sit inside the jeans and are dropped
CLOTHES = ["clothes/male_casualsuit01", "clothes/shoes01", "hair/short02", "eyes/low-poly"]


def read_obj(path: Path):
    verts, faces, groups, group = [], [], [], ""
    for line in path.read_text().splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("g "):
            group = line[2:].strip()
        elif line.startswith("f "):
            faces.append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
            groups.append(group)
    return np.array(verts, dtype=np.float64), faces, groups


def read_target(path: Path) -> tuple[np.ndarray, np.ndarray]:
    idx, d = [], []
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            p = line.split()
            idx.append(int(p[0]))
            d.append([float(x) for x in p[1:4]])
    return np.array(idx, dtype=np.int64), np.array(d, dtype=np.float64).reshape(-1, 3)


def triangulate(faces: list[list[int]]) -> np.ndarray:
    tris = []
    for f in faces:
        for k in range(1, len(f) - 1):
            tris.append([f[0], f[k], f[k + 1]])
    return np.array(tris, dtype=np.int64)


def rot_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k * (1 / (1 + c))


def read_mhclo(path: Path):
    refs, ws, offs, scales, deletes, obj = [], [], [], {}, [], None
    mode = None
    for line in path.read_text().splitlines():
        p = line.split()
        if not p or p[0].startswith("#"):
            continue
        if p[0] == "obj_file":
            obj = p[1]
        elif p[0] in ("x_scale", "y_scale", "z_scale"):
            scales["xyz".index(p[0][0])] = (int(p[1]), int(p[2]), float(p[3]))
        elif p[0] == "verts":
            mode = "verts"
        elif p[0] == "delete_verts":
            mode = "delete"
        elif mode == "verts" and p[0].lstrip("-").isdigit():
            if len(p) == 1:
                refs.append([int(p[0])] * 3), ws.append([1.0, 0, 0]), offs.append([0.0, 0, 0])
            else:
                refs.append([int(x) for x in p[:3]]), ws.append([float(x) for x in p[3:6]]), offs.append([float(x) for x in p[6:9]])
        elif mode == "delete":
            toks = line.split()
            i = 0
            while i < len(toks):
                if i + 2 < len(toks) and toks[i + 1] == "-":
                    deletes.extend(range(int(toks[i]), int(toks[i + 2]) + 1))
                    i += 3
                else:
                    deletes.append(int(toks[i]))
                    i += 1
        elif mode is None and p[0] not in ("uuid", "basemesh", "tag", "name", "material", "z_depth", "max_pole", "special_pose"):
            pass
    return obj, np.array(refs), np.array(ws), np.array(offs), scales, deletes


def normals(v: np.ndarray, tris: np.ndarray) -> np.ndarray:
    n = np.zeros_like(v)
    fn = np.cross(v[tris[:, 1]] - v[tris[:, 0]], v[tris[:, 2]] - v[tris[:, 0]])
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return n


def main(core: Path, assets: Path) -> None:
    V, faces, groups = read_obj(core / "3dobjs" / "base.obj")
    # Macro shape: male, ~52 years, mixed ancestry (weights sum to 1 per age band).
    for race, rw in RACES.items():
        for age, aw in (("young", 1 - AGE_OLD), ("old", AGE_OLD)):
            idx, d = read_target(core / "targets" / "macrodetails" / f"{race}-male-{age}.target")
            V[idx] += rw * aw * d
    for age, aw in (("young", 1 - AGE_OLD), ("old", AGE_OLD)):
        idx, d = read_target(core / "targets" / "macrodetails" / f"universal-male-{age}-averagemuscle-averageweight.target")
        V[idx] += aw * d
    rest = V.copy()
    body_faces = [f for f, g in zip(faces, groups, strict=True) if g == "body"]
    used0 = np.unique(triangulate(body_faces))
    lo0, hi0 = rest[used0, 1].min(), rest[used0, 1].max()
    s = HEIGHT_M / (hi0 - lo0)

    # Skeleton (joint positions from the shaped mesh) and pose: limbs along the twin's bones.
    sk = json.loads((core / "rigs" / "default.mhskel").read_text())
    J = {n: rest[idx].mean(0) for n, idx in sk["joints"].items()}
    bones = sk["bones"]
    order: list[str] = []
    while len(order) < len(bones):
        for b, info in bones.items():
            if b not in order and (info["parent"] is None or info["parent"] in order):
                order.append(b)
    G: dict[str, np.ndarray] = {}
    for b in order:
        info = bones[b]
        parent = G[info["parent"]] if info["parent"] else np.eye(4)
        L = np.eye(4)
        base, side = b.rsplit(".", 1) if "." in b else (b, "")
        if base in TWIN_AIM:
            h, t = J[info["head"]], J[bones[f"{CHAIN_END[base]}.{side}"]["head"]]  # this joint -> next real joint
            cur = parent[:3, :3] @ (t - h)
            head_now = parent[:3, :3] @ h + parent[:3, 3]
            aim_m = np.array(TWIN_AIM[base]) * (np.array([1, 1, 1]) if side == "L" else np.array([-1, 1, 1]))
            aim = aim_m / s + np.array([0.0, lo0, J[bones["upperleg01.L"]["head"]][2]])  # metres -> MakeHuman units
            want = aim - head_now
            R = parent[:3, :3].T @ rot_between(cur, want) @ parent[:3, :3]
            L[:3, :3] = R
            L[:3, 3] = h - R @ h
        G[b] = parent @ L
    W = np.zeros((len(V), len(order)))
    col = {b: i for i, b in enumerate(order)}
    for b, pairs in json.loads((core / "rigs" / "default_weights.mhw").read_text())["weights"].items():
        if b in col:
            for vi, w in pairs:
                W[vi, col[b]] = w
    W /= np.maximum(W.sum(1, keepdims=True), 1e-12)

    # Per-vertex skinning matrices (linear blend of the bone transforms).
    M = np.zeros((len(V), 3, 4))
    for b, i in col.items():
        m = W[:, i] > 0
        if m.any():
            M[m] += W[m, i, None, None] * G[b][None, :3, :]
    posed = np.einsum("nij,nj->ni", M, np.c_[rest, np.ones(len(rest))])

    # Clothes, hair and eyes fitted on the posed body: the fitting triangle's posed vertices plus the
    # offset turned by the triangle's own skinning rotation (as fitted in rest, just posed).
    parts: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    deleted: set[int] = set()
    for rel in CLOTHES:
        d = assets / rel
        mhclo = next(d.glob("*.mhclo"))
        obj, refs, ws, offs, scales, deletes = read_mhclo(mhclo)
        cv, cfaces, _ = read_obj(d / obj)
        sc = np.array([abs(rest[a][ax] - rest[b][ax]) / dist for ax, (a, b, dist) in sorted(scales.items())]) if scales else np.ones(3)
        rot = (ws[:, :, None, None] * M[refs][:, :, :, :3]).sum(1)
        fit = (ws[:, :, None] * posed[refs]).sum(1) + np.einsum("nij,nj->ni", rot, offs * sc)
        tris = triangulate(cfaces)
        placed_y = (fit[:, 1] - lo0) * s
        if rel.endswith("shoes01"):
            tris = tris[~(placed_y[tris] > SOCK_TOP_M).all(1)]
        parts[rel.split("/")[-1]] = (fit, tris)
        if rel.startswith("clothes"):
            deleted.update(deletes)

    glass_tris = triangulate(body_faces)
    statue_tris = triangulate([f for f in body_faces if not any(i in deleted for i in f)])

    # Scale to 1.70 m, soles at y = 0, hips over the twin's (x = 0, z = 0).
    lo = posed[np.unique(glass_tris), 1].min()
    hip_z = J[bones["upperleg01.L"]["head"]][2]
    shift = np.array([0.0, -lo, -hip_z])

    def place(p: np.ndarray) -> np.ndarray:
        return (p + shift) * s

    meshes = {"body": (place(posed), statue_tris), "glass": (place(posed), glass_tris)}
    for k, (p, t) in parts.items():
        meshes[k] = (place(p), t)

    # Compact binary: per mesh, unique vertices (uint16-quantised positions, int16 normals) + uint16 indices.
    allp = np.concatenate([m[0][np.unique(m[1])] for m in meshes.values()])
    bmin, bmax = allp.min(0), allp.max(0)
    blob, manifest = bytearray(), {"bbox": [bmin.round(5).tolist(), bmax.round(5).tolist()], "meshes": {}, "source": "MakeHuman (CC0 1.0): base mesh, macro targets, default rig; system assets male_casualsuit01, shoes01, short02, low-poly eyes"}
    shared: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for name, (p, t) in meshes.items():
        key = "body" if name in ("body", "glass") else name
        if key not in shared:
            src = meshes[key][1] if key == "body" else t
            keep = np.unique(np.concatenate([src, meshes["glass"][1]]) if key == "body" else src)
            remap = -np.ones(len(p), dtype=np.int64)
            remap[keep] = np.arange(len(keep))
            pv = p[keep]
            nv = normals(p, meshes["glass"][1] if key == "body" else t)[keep]
            q = np.round((pv - bmin) / (bmax - bmin) * 65535).astype("<u2")
            nq = np.round(nv * 32767).astype("<i2")
            off = len(blob)
            blob += q.tobytes()
            blob += nq.tobytes()
            shared[key] = (remap, np.array([off, len(keep)]))
            manifest["meshes"].setdefault("_vertices", {})[key] = {"offset": off, "count": int(len(keep))}
        remap, _ = shared[key]
        idx = remap[t]
        assert (idx >= 0).all() and idx.max() < 65536, name
        off = len(blob)
        blob += idx.astype("<u2").tobytes()
        if len(blob) % 4:
            blob += b"\0" * (4 - len(blob) % 4)
        manifest["meshes"][name] = {"vertices": key, "indexOffset": off, "indexCount": int(idx.size)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "statue.bin").write_bytes(bytes(blob))
    (OUT / "statue.json").write_text(json.dumps(manifest, indent=1) + "\n")
    joints = {b: (place(G[b][:3, :3] @ J[bones[b]["head"]] + G[b][:3, 3])).round(3).tolist()
              for b in ("upperarm01.L", "lowerarm01.L", "wrist.L", "upperleg01.L", "lowerleg01.L", "foot.L", "head", "neck01")}
    print(json.dumps({"scale": s, "bytes": len(blob), "joints": joints,
                      "meshes": {k: v for k, v in manifest["meshes"].items() if k != "_vertices"}}, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
