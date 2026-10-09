"""Hidden-3D -> stable pixel sprite renderer.

A model is a bone hierarchy; each bone carries SDF parts in its local space.
Every bone is rendered as its own *layer* (4x supersampled, reduced by
coverage + majority vote) and cached by (bone, facing, orientation, scale).
Layers are composited with depth test at *integer* pixel offsets, so a part
that only translates between frames keeps an identical pixel pattern — no
swimming. Colors are never computed: every pixel is (material, shade level),
resolved against the style's locked ramps at the end.

Projection is cabinet-oblique: screen_up = z + K*y (K = 0.5), which keeps the
full character height and shows tops of things (3/4 top-down).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .sdf import STAMP_SHAPES, eval_prim, rot_matrix, smin

K = 0.5
RAY = np.array([0.0, 1.0, -K]) / math.sqrt(1 + K * K)   # direction a view ray travels
DIRECTIONS = ["S", "SE", "E", "NE", "N", "NW", "W", "SW"]
# yaw that turns a model authored facing south (-Y, toward the viewer) to each direction
YAW = {"S": 0, "SE": 45, "E": 90, "NE": 135, "N": 180, "NW": 225, "W": 270, "SW": 315}


@dataclass
class Layer:
    ox: int              # screen x of layer array [0,0] relative to the bone origin
    oy: int              # screen y (down) of [0,0] relative to bone origin
    mat: np.ndarray      # int16, -1 = empty
    light: np.ndarray    # float32 0..1
    depth: np.ndarray    # float32, along RAY, relative to bone origin
    normal: np.ndarray   # (h, w, 3) float32 world normals
    hnorm: np.ndarray = None    # 0 = bottom of this bone's visible surface, 1 = top
    local: np.ndarray = None    # (h, w, 3) surface position in the bone's own space (texture coords)


@dataclass
class Buffers:
    """Composited G-buffer for one frame."""
    mat: np.ndarray
    light: np.ndarray
    depth: np.ndarray
    bone: np.ndarray
    normal: np.ndarray
    hnorm: np.ndarray = None
    height: np.ndarray = None   # world z of the visible surface (px above the feet)
    local: np.ndarray = None    # surface position in its bone's space: detail patterns stick to parts


# ------------------------------------------------------------------ bones

@dataclass
class Bone:
    name: str
    parent: Optional[str]
    at: np.ndarray
    rot: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    parts: List[Dict] = field(default_factory=list)
    stamps: List[Dict] = field(default_factory=list)   # 2D pixel details pinned to the bone
    blend: float = 0.0            # smooth-union radius within this bone
    z_bias: float = 0.0           # nudge depth (e.g. keep eyes above face)
    seam: bool = False            # always separate this bone from overlapping bones with a line
    facets: int = 0               # 0 = smooth; 14/26 = snap normals to that many planes (carved look)


class Model:
    def __init__(self, spec: Dict, materials: List[str]):
        self.spec = spec
        self.materials = materials
        self.mat_index = {m: i for i, m in enumerate(materials)}
        self.bones: Dict[str, Bone] = {}
        self.order: List[str] = []
        for b in spec["bones"]:
            parts = [p for p in b.get("parts", []) if p.get("shape") not in STAMP_SHAPES]
            stamps = [p for p in b.get("parts", []) if p.get("shape") in STAMP_SHAPES]
            bone = Bone(b["name"], b.get("parent"), np.asarray(b.get("at", (0, 0, 0)), float),
                        tuple(b.get("rot", (0, 0, 0))), parts, stamps, b.get("blend", 0.0),
                        b.get("z_bias", 0.0), bool(b.get("seam", False)),
                        int(b.get("facets", spec.get("shading", {}).get("facets", 0))))
            for p in bone.parts:
                if p["mat"] not in self.mat_index:
                    raise ValueError("bone %s uses unknown material %r" % (bone.name, p["mat"]))
            self.bones[bone.name] = bone
            self.order.append(bone.name)
        self._cache: Dict[tuple, Layer] = {}
        self.squash_bones = set(spec.get("squash_bones", ["hips", "torso", "body"]))

    # world transforms --------------------------------------------------
    def world(self, pose: Dict, yaw: float, squash: Tuple[float, float] = (1.0, 1.0), widen: float = 1.0
              ) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """-> bone: (M 3x3 local->world linear map, origin 3).

        pose[bone] = {rot, at (offset), scale}; scale inherits down the chain.
        squash = (horizontal, vertical) whole-body scale about the feet.
        """
        out = {}
        Ryaw = rot_matrix(0, 0, yaw)
        # widen: screen-x stretch applied after the facing turn (pixel artists cheat front views wider)
        Wd = np.diag([widen, 1.0, 1.0])
        for name in self.order:
            b = self.bones[name]
            pb = pose.get(name, {})
            local = rot_matrix(*b.rot) @ rot_matrix(*pb.get("rot", (0, 0, 0))) \
                @ np.diag(np.asarray(pb.get("scale", (1, 1, 1)), float))
            off = b.at + np.asarray(pb.get("at", (0, 0, 0)), float)
            if b.parent is None:
                M = Wd @ Ryaw @ local
                o = Wd @ Ryaw @ off
            else:
                pM, po = out[b.parent]
                M = pM @ local
                o = po + pM @ off
            out[name] = (M, o)
        if squash != (1.0, 1.0):
            # squash/stretch about the feet: every joint moves with the squash, but only the soft
            # body bones deform; heads, hats, weapons and props translate rigidly and keep their pixels
            Sq = np.diag([squash[0], squash[0], squash[1]])
            soft = self.squash_bones
            out = {n: ((Sq @ M) if n in soft else M, Sq @ o) for n, (M, o) in out.items()}
        return out

    # layer rendering -----------------------------------------------------
    def layer(self, name: str, M: np.ndarray, light_dir: np.ndarray, ss: int = 4) -> Optional[Layer]:
        b = self.bones[name]
        if not b.parts:
            return None
        key = (name, tuple(np.round(M, 3).ravel()))
        if key in self._cache:
            return self._cache[key]
        lay, h = _render_layer(b, M, light_dir, self.mat_index, ss)
        lay.height = h
        self._cache[key] = lay
        return lay


def _bounds(parts: List[Dict]) -> Tuple[np.ndarray, float]:
    pts, rad = [], 0.0
    for p in parts:
        at = np.asarray(p.get("at", (0, 0, 0)), float)
        s = p["shape"]
        if s in ("ellipsoid", "sphere"):
            r = p.get("r", 1.0)
            e = float(np.max(r))
            pts += [at - e, at + e]
        elif s == "capsule":
            a = at + np.asarray(p.get("a", (0, 0, 0)), float)
            bb = at + np.asarray(p["b"], float)
            e = max(p.get("r1", p.get("r", 1)), p.get("r2", p.get("r", 1)))
            pts += [a - e, a + e, bb - e, bb + e]
        elif s == "box":
            e = float(np.linalg.norm(p["half"]))
            pts += [at - e, at + e]
        elif s == "cylinder":
            e = math.hypot(p["r"], p["h"])
            pts += [at - e, at + e]
        elif s == "torus":
            e = p["R"] + p["r"]
            pts += [at - e, at + e]
        elif s == "roof":
            e = math.hypot(math.hypot(*p["half"][:2]), p["h"])
            pts += [at - e, at + e]
        elif s == "cone":
            e = math.hypot(p["r"], p["h"])
            pts += [at - e, at + np.array([e, e, e + p["h"]])]
    P = np.array(pts)
    lo, hi = P.min(0), P.max(0)
    c = (lo + hi) / 2
    return c, float(np.linalg.norm(hi - lo) / 2) + 1.0


def _scene_sdf(bone: Bone, q: np.ndarray, mat_index: Dict[str, int]) -> Tuple[np.ndarray, np.ndarray]:
    d = None
    m = None
    for p in bone.parts:
        di = eval_prim(p, q)
        mi = mat_index[p["mat"]]
        if p.get("subtract"):
            if d is not None:
                d = np.maximum(d, -di)
            continue
        if d is None:
            d, m = di, np.full(len(q), mi, np.int16)
        else:
            m = np.where(di < d, mi, m).astype(np.int16)
            d = smin(d, di, p.get("blend", bone.blend))
    return d, m


def _facet_dirs(kind: int) -> np.ndarray:
    import itertools
    v = [np.array(c, float) for c in itertools.product((-1, 0, 1), repeat=3) if any(c)]
    if kind == 14:
        v = [x for x in v if np.count_nonzero(x) in (1, 3)]
    v = np.array(v)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


_FACETS = {14: _facet_dirs(14), 26: _facet_dirs(26)}


def _render_layer(bone: Bone, M: np.ndarray, L: np.ndarray, mat_index, ss: int) -> Layer:
    c_local, rad = _bounds(bone.parts)
    c = M @ c_local
    sv = np.linalg.svd(M, compute_uv=False)
    rad *= float(sv.max())
    cx, cy = c[0], c[2] + K * c[1]
    ry = rad * math.sqrt(1 + K * K)
    x0, x1 = math.floor(cx - rad) - 1, math.ceil(cx + rad) + 1
    y0, y1 = math.floor(cy - ry) - 1, math.ceil(cy + ry) + 1   # screen up coords
    W, H = x1 - x0, y1 - y0
    # sample grid (screen up = +y); row 0 = top
    xs = x0 + (np.arange(W * ss) + 0.5) / ss
    ys = y1 - (np.arange(H * ss) + 0.5) / ss
    SX, SY = np.meshgrid(xs, ys)
    n = SX.size
    t_start = np.dot(c, RAY) - rad - 1.0
    # points on the y=0 plane with screen coords (sx, sy), pulled back along the ray
    plane = np.stack([SX.ravel(), np.zeros(n), SY.ravel()], 1)
    origin = plane + np.outer(t_start - plane @ RAY, RAY)
    Minv = np.linalg.inv(M)
    dscale = float(sv.min())

    def f(p):
        q = p @ Minv.T
        d, m = _scene_sdf(bone, q, mat_index)
        return d * dscale, m

    t = np.zeros(n)
    hit = np.zeros(n, bool)
    alive = np.ones(n, bool)
    t_max = 2 * rad + 4.0
    for _ in range(80):
        idx = np.nonzero(alive)[0]
        if idx.size == 0:
            break
        p = origin[idx] + np.outer(t[idx], RAY)
        d, _ = f(p)
        h = d < 0.02
        hit[idx[h]] = True
        alive[idx[h]] = False
        t[idx[~h]] += np.maximum(d[~h] * 0.9, 0.01)
        gone = t[idx] > t_max
        alive[idx[gone]] = False
    hi_idx = np.nonzero(hit)[0]
    P = origin[hi_idx] + np.outer(t[hi_idx], RAY)
    _, mats = f(P)
    e = 0.05
    grads = []
    for ax in range(3):
        dv = np.zeros(3)
        dv[ax] = e
        grads.append(f(P + dv)[0] - f(P - dv)[0])
    N = np.stack(grads, 1)
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
    if bone.facets:
        # carve: snap the normal to a plane set fixed in the bone's own space, so facets travel with the
        # part (no shimmer) and shading falls into flat planes the way pixel artists paint form
        D = _FACETS[bone.facets]
        Nl = N @ M
        Nl /= np.linalg.norm(Nl, axis=1, keepdims=True) + 1e-9
        Nq = D[np.argmax(Nl @ D.T, axis=1)]
        N = Nq @ Minv
        N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
    lam = N @ L
    depth_s = np.full(n, np.inf)
    depth_s[hi_idx] = P @ RAY
    mat_s = np.full(n, -1, np.int16)
    mat_s[hi_idx] = mats
    light_s = np.zeros(n)
    light_s[hi_idx] = lam
    nor_s = np.zeros((n, 3))
    nor_s[hi_idx] = N
    hgt_s = np.zeros(n)
    hgt_s[hi_idx] = P[:, 2]
    loc_s = np.zeros((n, 3))
    loc_s[hi_idx] = P @ Minv.T

    # reduce ss x ss -> 1 by coverage and majority material
    mat_s = mat_s.reshape(H, ss, W, ss).transpose(0, 2, 1, 3).reshape(H, W, ss * ss)
    light_s = light_s.reshape(H, ss, W, ss).transpose(0, 2, 1, 3).reshape(H, W, ss * ss)
    depth_s = depth_s.reshape(H, ss, W, ss).transpose(0, 2, 1, 3).reshape(H, W, ss * ss)
    nor_s = nor_s.reshape(H, ss, W, ss, 3).transpose(0, 2, 1, 3, 4).reshape(H, W, ss * ss, 3)
    hgt_s = hgt_s.reshape(H, ss, W, ss).transpose(0, 2, 1, 3).reshape(H, W, ss * ss)
    loc_s = loc_s.reshape(H, ss, W, ss, 3).transpose(0, 2, 1, 3, 4).reshape(H, W, ss * ss, 3)
    out_h = np.zeros((H, W), np.float32)
    out_p = np.zeros((H, W, 3), np.float32)
    cover = (mat_s >= 0).sum(-1)
    filled = cover * 2 >= ss * ss
    out_m = np.full((H, W), -1, np.int16)
    out_l = np.zeros((H, W), np.float32)
    out_d = np.full((H, W), np.inf, np.float32)
    out_n = np.zeros((H, W, 3), np.float32)
    ys_, xs_ = np.nonzero(filled)
    for y, x in zip(ys_, xs_):
        ms = mat_s[y, x]
        valid = ms[ms >= 0]
        vals, counts = np.unique(valid, return_counts=True)
        # front-most material wins ties so thin front details survive
        best = vals[counts == counts.max()]
        if len(best) > 1:
            dd = depth_s[y, x]
            best = [min(best, key=lambda v: dd[ms == v].min())]
        mv = best[0]
        sel = ms == mv
        out_m[y, x] = mv
        out_l[y, x] = light_s[y, x][sel].mean()
        out_d[y, x] = depth_s[y, x][sel].min()
        out_h[y, x] = hgt_s[y, x][sel].mean()
        out_p[y, x] = loc_s[y, x][sel].mean(0)
        nv = nor_s[y, x][sel].mean(0)
        out_n[y, x] = nv / (np.linalg.norm(nv) + 1e-9)
    hn = np.zeros((H, W), np.float32)
    if filled.any():
        lo, hi = out_h[filled].min(), out_h[filled].max()
        hn = np.where(filled, (out_h - lo) / max(hi - lo, 1e-3), 0).astype(np.float32)
    return Layer(ox=x0, oy=-y1, mat=out_m, light=out_l, depth=out_d, normal=out_n, hnorm=hn, local=out_p), out_h


# ------------------------------------------------------------------ frames

def render_frame(model: Model, pose: Dict, facing: str, size: Tuple[int, int], anchor: Tuple[int, int],
                 light_dir: np.ndarray, root_offset: Tuple[float, float, float] = (0, 0, 0),
                 ss: int = 4, hide=(), squash: Tuple[float, float] = (1.0, 1.0), yaw_offset: float = 0.0,
                 widen: float = 1.0) -> Buffers:
    """Composite all bone layers. anchor = pixel (x, y) of world origin (feet)."""
    W, H = size
    buf = Buffers(mat=np.full((H, W), -1, np.int16), light=np.zeros((H, W), np.float32),
                  depth=np.full((H, W), np.inf, np.float32), bone=np.full((H, W), -1, np.int16),
                  normal=np.zeros((H, W, 3), np.float32), hnorm=np.zeros((H, W), np.float32),
                  height=np.zeros((H, W), np.float32), local=np.zeros((H, W, 3), np.float32))
    world = model.world(pose, YAW[facing] + yaw_offset, squash, widen)
    ro = np.asarray(root_offset, float)
    for bi, name in enumerate(model.order):
        M, o = world[name]
        lay = None if name in hide else model.layer(name, M, light_dir, ss)
        if lay is None:
            continue
        o = o + ro
        sx = int(math.floor(o[0] + 0.5))
        sy = int(math.floor(-(o[2] + K * o[1]) + 0.5))
        dep0 = float(o @ RAY) + model.bones[name].z_bias
        h, w = lay.mat.shape
        X0 = anchor[0] + sx + lay.ox
        Y0 = anchor[1] + sy + lay.oy
        # clip
        ax0, ay0 = max(0, -X0), max(0, -Y0)
        ax1, ay1 = min(w, W - X0), min(h, H - Y0)
        if ax1 <= ax0 or ay1 <= ay0:
            continue
        sl = (slice(Y0 + ay0, Y0 + ay1), slice(X0 + ax0, X0 + ax1))
        lm = lay.mat[ay0:ay1, ax0:ax1]
        ld = lay.depth[ay0:ay1, ax0:ax1] + dep0
        win = (lm >= 0) & (ld < buf.depth[sl])
        buf.mat[sl] = np.where(win, lm, buf.mat[sl])
        buf.light[sl] = np.where(win, lay.light[ay0:ay1, ax0:ax1], buf.light[sl])
        buf.depth[sl] = np.where(win, ld, buf.depth[sl])
        buf.bone[sl] = np.where(win, bi, buf.bone[sl])
        buf.normal[sl] = np.where(win[..., None], lay.normal[ay0:ay1, ax0:ax1], buf.normal[sl])
        buf.hnorm[sl] = np.where(win, lay.hnorm[ay0:ay1, ax0:ax1], buf.hnorm[sl])
        buf.height[sl] = np.where(win, lay.height[ay0:ay1, ax0:ax1] + o[2], buf.height[sl])
        buf.local[sl] = np.where(win[..., None], lay.local[ay0:ay1, ax0:ax1], buf.local[sl])
    return buf
