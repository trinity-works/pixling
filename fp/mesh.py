"""Mesh pieces for fp assets: low-poly shapes in metres, y up, each vertex tagged with a material.

An asset is a Mesh (triangles) plus optional Lines (1 px polylines: ropes, wires, grass blades). Every vertex carries
  mat   the material (a ramp name in the style; the shader picks the tone from the light value),
  snow  how readily it catches snow (0 never, 1 like the ground): faces that point up enough turn to snow,
  ao    baked occlusion 0..1 (1 = open): darkens the light value, so pockets fall to a lower band.
Faces are flat-shaded unless a piece is built smooth (terrain, snow mounds): flat faces are what makes banded light
read as facets. Builders compose pieces with `+` and place them with `.at()`, `.turn()`, `.scale()`.
"""
from __future__ import annotations

import math

import numpy as np


class Mesh:
    def __init__(self, P=None, N=None, M=None, S=None, A=None, I=None):
        self.P = np.zeros((0, 3), np.float32) if P is None else np.asarray(P, np.float32).reshape(-1, 3)
        n = len(self.P)
        self.N = np.zeros((n, 3), np.float32) if N is None else np.asarray(N, np.float32).reshape(-1, 3)
        self.M = np.zeros(n, object) if M is None else np.asarray(M, object).reshape(-1)
        self.S = np.zeros(n, np.float32) if S is None else np.asarray(S, np.float32).reshape(-1)
        self.A = np.ones(n, np.float32) if A is None else np.asarray(A, np.float32).reshape(-1)
        self.I = np.zeros((0, 3), np.int64) if I is None else np.asarray(I, np.int64).reshape(-1, 3)

    # ---- combine / place -------------------------------------------------------------------------------------
    def __add__(self, o: "Mesh") -> "Mesh":
        if not len(o.P):
            return self.copy()
        if not len(self.P):
            return o.copy()
        return Mesh(np.vstack([self.P, o.P]), np.vstack([self.N, o.N]), np.concatenate([self.M, o.M]),
                    np.concatenate([self.S, o.S]), np.concatenate([self.A, o.A]),
                    np.vstack([self.I, o.I + len(self.P)]))

    def copy(self) -> "Mesh":
        return Mesh(self.P.copy(), self.N.copy(), self.M.copy(), self.S.copy(), self.A.copy(), self.I.copy())

    def at(self, x=0.0, y=0.0, z=0.0) -> "Mesh":
        m = self.copy()
        m.P += np.array([x, y, z], np.float32)
        return m

    def turn(self, yaw=0.0, pitch=0.0, roll=0.0) -> "Mesh":
        """rotate in degrees: yaw about y, pitch about x, roll about z (applied roll, pitch, yaw)."""
        R = rot(yaw, pitch, roll)
        m = self.copy()
        m.P = m.P @ R.T
        m.N = m.N @ R.T
        return m

    def scale(self, sx=1.0, sy=None, sz=None) -> "Mesh":
        sy = sx if sy is None else sy
        sz = sx if sz is None else sz
        m = self.copy()
        m.P = m.P * np.array([sx, sy, sz], np.float32)
        inv = np.array([1 / sx, 1 / sy, 1 / sz], np.float32)
        nn = m.N * inv
        m.N = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-9)
        return m

    def tag(self, mat=None, snow=None, ao=None) -> "Mesh":
        m = self.copy()
        if mat is not None:
            m.M[:] = mat
        if snow is not None:
            m.S[:] = snow
        if ao is not None:
            m.A[:] = ao
        return m

    def warp(self, fn) -> "Mesh":
        """move vertices with fn(P) -> P (normals of flat faces are recomputed)."""
        m = self.copy()
        m.P = np.asarray(fn(m.P.copy()), np.float32)
        return m.flat()

    def jitter(self, amount=0.03, seed=0) -> "Mesh":
        """nudge shared corners together (same position -> same offset), so faces stay closed: hand-made wobble."""
        rng = np.random.default_rng(seed)
        key = np.round(self.P / 1e-4).astype(np.int64)
        _, inv = np.unique(key, axis=0, return_inverse=True)
        off = rng.uniform(-amount, amount, (inv.max() + 1, 3)).astype(np.float32)
        m = self.copy()
        m.P = m.P + off[inv.reshape(-1)]
        return m.flat()

    def flat(self) -> "Mesh":
        """recompute per-face normals (every triangle gets its own three vertices)."""
        P = self.P[self.I]                       # (t,3,3)
        n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        idx = self.I.reshape(-1)
        t = len(self.I)
        return Mesh(P.reshape(-1, 3), np.repeat(n, 3, axis=0), self.M[idx], self.S[idx], self.A[idx],
                    np.arange(t * 3).reshape(-1, 3))

    def smooth(self) -> "Mesh":
        """average normals over shared positions (soft masses: snow mounds, terrain)."""
        key = np.round(self.P / 1e-4).astype(np.int64)
        _, inv = np.unique(key, axis=0, return_inverse=True)
        inv = inv.reshape(-1)
        P = self.P[self.I]
        fn = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])      # area-weighted
        acc = np.zeros((inv.max() + 1, 3), np.float64)
        for k in range(3):
            np.add.at(acc, inv[self.I[:, k]], fn)
        acc /= np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-12)
        m = self.copy()
        m.N = acc[inv].astype(np.float32)
        return m

    def bounds(self):
        return self.P.min(0), self.P.max(0)

    @property
    def tris(self) -> int:
        return len(self.I)


class Lines:
    """1 px polylines drawn at the game's pixel size: ropes, power lines, grass blades, antennae."""

    def __init__(self, polys=None):
        self.polys = list(polys or [])          # [(mat, ndarray (k,3))]

    def add(self, mat, pts) -> "Lines":
        self.polys.append((mat, np.asarray(pts, np.float32).reshape(-1, 3)))
        return self

    def __add__(self, o: "Lines") -> "Lines":
        return Lines(self.polys + o.polys)

    def at(self, x=0.0, y=0.0, z=0.0) -> "Lines":
        return Lines([(m, p + np.array([x, y, z], np.float32)) for m, p in self.polys])

    def turn(self, yaw=0.0, pitch=0.0, roll=0.0) -> "Lines":
        R = rot(yaw, pitch, roll)
        return Lines([(m, p @ R.T) for m, p in self.polys])

    def scale(self, s=1.0) -> "Lines":
        return Lines([(m, p * s) for m, p in self.polys])


# ---- maths ---------------------------------------------------------------------------------------------------------
def rot(yaw=0.0, pitch=0.0, roll=0.0) -> np.ndarray:
    y, p, r = (math.radians(a) for a in (yaw, pitch, roll))
    Ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    Rz = np.array([[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]])
    return (Ry @ Rx @ Rz).astype(np.float32)


def _mesh(P, I, mat, snow=0.0, ao=1.0, smooth=False) -> Mesh:
    P = np.asarray(P, np.float32)
    m = Mesh(P, None, [mat] * len(P), [snow] * len(P), [ao] * len(P), I)
    return m.smooth() if smooth else m.flat()


# ---- primitives (all centred on x/z, base at y=0 unless noted) -----------------------------------------------------
def box(w, h, d, mat, snow=0.0, ao=1.0) -> Mesh:
    """w (x) by h (y) by d (z), base at y=0."""
    x, z = w / 2, d / 2
    P = [[-x, 0, -z], [x, 0, -z], [x, 0, z], [-x, 0, z], [-x, h, -z], [x, h, -z], [x, h, z], [-x, h, z]]
    I = [[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2],
         [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0]]
    return _mesh(P, I, mat, snow, ao)


def frustum(r0, r1, h, mat, segs=8, snow=0.0, ao=1.0, cap=True, smooth=False, phase=0.0) -> Mesh:
    """a ring of r0 at y=0 to r1 at y=h (r1=0: a cone). smooth=True for round posts and trunks."""
    return lathe([(r0, 0.0), (r1, h)], mat, segs, snow, ao, cap_bottom=cap, cap_top=cap, smooth=smooth, phase=phase)


def cylinder(r, h, mat, segs=8, **kw) -> Mesh:
    return frustum(r, r, h, mat, segs, **kw)


def lathe(profile, mat, segs=8, snow=0.0, ao=1.0, cap_bottom=True, cap_top=True, smooth=False, phase=0.0) -> Mesh:
    """revolve [(radius, y), ...] (bottom to top) around y. Per-ring (mat, snow) can be given as 3rd/4th items."""
    rings = []
    a = np.linspace(0, 2 * math.pi, segs, endpoint=False) + math.radians(phase)
    for item in profile:
        r, y = item[0], item[1]
        rings.append(np.stack([np.cos(a) * r, np.full(segs, y), np.sin(a) * r], 1))
    out = Mesh()
    for k in range(len(rings) - 1):
        lo, hi = rings[k], rings[k + 1]
        pm = profile[k][2] if len(profile[k]) > 2 else mat
        ps = profile[k][3] if len(profile[k]) > 3 else snow
        P, I = [], []
        for i in range(segs):
            j = (i + 1) % segs
            b = len(P)
            P += [lo[i], lo[j], hi[j], hi[i]]
            I += [[b, b + 2, b + 1], [b, b + 3, b + 2]]
        piece = Mesh(np.array(P, np.float32), None, [pm] * len(P), [ps] * len(P), [ao] * len(P), I)
        out = out + piece
    if cap_top and profile[-1][0] > 1e-6:
        c = np.array([0, profile[-1][1], 0], np.float32)
        P = [c] + list(rings[-1])
        I = [[0, 1 + (i + 1) % segs, 1 + i] for i in range(segs)]
        out = out + Mesh(np.array(P), None, [mat] * len(P), [snow] * len(P), [ao] * len(P), I)
    if cap_bottom and profile[0][0] > 1e-6:
        c = np.array([0, profile[0][1], 0], np.float32)
        P = [c] + list(rings[0])
        I = [[0, 1 + i, 1 + (i + 1) % segs] for i in range(segs)]
        out = out + Mesh(np.array(P), None, [mat] * len(P), [0.0] * len(P), [ao] * len(P), I)
    return out.smooth() if smooth else out.flat()


def sphere(r, mat, segs=8, rings=5, snow=0.0, ao=1.0, smooth=False, squash=1.0) -> Mesh:
    """a low-poly ball centred at y=r*squash (sitting on y=0)."""
    prof = []
    for k in range(rings + 1):
        t = math.pi * k / rings
        prof.append((r * math.sin(t) + (1e-5 if k in (0, rings) else 0), r * squash * (1 - math.cos(t))))
    return lathe(prof, mat, segs, snow, ao, cap_bottom=False, cap_top=False, smooth=smooth)


def prism(poly, h, mat, snow=0.0, ao=1.0, top_mat=None, bevel=0.0) -> Mesh:
    """extrude a 2D polygon [(x, z), ...] (counter-clockwise seen from above) from y=0 to y=h.
    bevel shrinks the top face inward (a slab with chamfered edges)."""
    poly = np.asarray(poly, np.float32)
    n = len(poly)
    c = poly.mean(0)
    top = poly if bevel <= 0 else c + (poly - c) * (1 - bevel / max(np.linalg.norm(poly - c, axis=1).mean(), 1e-6))
    P, I, Mt = [], [], []
    for i in range(n):
        j = (i + 1) % n
        b = len(P)
        P += [[poly[i][0], 0, poly[i][1]], [poly[j][0], 0, poly[j][1]], [top[j][0], h, top[j][1]], [top[i][0], h, top[i][1]]]
        I += [[b, b + 2, b + 1], [b, b + 3, b + 2]]
        Mt += [mat] * 4
    b = len(P)
    P += [[c[0], h, c[1]]] + [[t[0], h, t[1]] for t in top]
    Mt += [top_mat or mat] * (n + 1)
    I += [[b, b + 1 + (i + 1) % n, b + 1 + i] for i in range(n)]
    m = Mesh(np.array(P, np.float32), None, Mt, [snow] * len(P), [ao] * len(P), I).flat()
    # fix winding so normals point out (polygon may be clockwise)
    if np.mean(m.N[:, 1][-3 * n:]) < 0:
        m.I = m.I[:, ::-1]
        m = m.flat()
    return m


def quad(p0, p1, p2, p3, mat, snow=0.0, ao=1.0, double=False) -> Mesh:
    P = np.array([p0, p1, p2, p3], np.float32)
    I = [[0, 1, 2], [0, 2, 3]] + ([[0, 2, 1], [0, 3, 2]] if double else [])
    return _mesh(P, I, mat, snow, ao)


def tube(pts, r, mat, segs=5, snow=0.0, ao=1.0) -> Mesh:
    """a thin tube along a polyline (branches, rails, handles)."""
    pts = np.asarray(pts, np.float32)
    out = Mesh()
    for a, b in zip(pts[:-1], pts[1:]):
        d = b - a
        L = float(np.linalg.norm(d))
        if L < 1e-6:
            continue
        seg = cylinder(r, L, mat, segs, snow=snow, ao=ao, cap=False)
        # rotate y-axis onto d
        yv = np.array([0, 1, 0], np.float32)
        dv = d / L
        v = np.cross(yv, dv)
        s, c = np.linalg.norm(v), float(np.dot(yv, dv))
        if s < 1e-6:
            R = np.eye(3, dtype=np.float32) if c > 0 else np.diag([1, -1, -1]).astype(np.float32)
        else:
            k = v / s
            K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]], np.float32)
            R = np.eye(3, dtype=np.float32) + s * K + (1 - c) * (K @ K)
        seg.P = seg.P @ R.T + a
        seg.N = seg.N @ R.T
        out = out + seg
    return out


# ---- curves --------------------------------------------------------------------------------------------------------
def catenary(a, b, sag, n=16) -> np.ndarray:
    """points of a hanging rope/wire from a to b, dipping `sag` metres at the middle (a parabola is close enough)."""
    a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
    t = np.linspace(0, 1, n, dtype=np.float32)[:, None]
    p = a + (b - a) * t
    p[:, 1] -= sag * 4 * t[:, 0] * (1 - t[:, 0])
    return p


def spline(ctrl, n=200) -> np.ndarray:
    """Catmull-Rom through control points [(x, y, z), ...], resampled to n points evenly spaced by arc length."""
    c = np.asarray(ctrl, np.float64)
    c = np.vstack([c[0] * 2 - c[1], c, c[-1] * 2 - c[-2]])
    dense = []
    for i in range(1, len(c) - 2):
        p0, p1, p2, p3 = c[i - 1], c[i], c[i + 1], c[i + 2]
        for t in np.linspace(0, 1, 40, endpoint=False):
            t2, t3 = t * t, t * t * t
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                                + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dense.append(c[-2])
    dense = np.array(dense)
    seg = np.linalg.norm(np.diff(dense, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    u = np.linspace(0, s[-1], n)
    return np.stack([np.interp(u, s, dense[:, k]) for k in range(3)], 1).astype(np.float32)
