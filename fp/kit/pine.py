"""Snowy spruce: a slate crown of many thin bough rings. Each ring is a flat shelf that holds the snow, a broken snow
lip on the bough tops, a short drooping fringe of tips and a dark underside, so the tree reads as the reference's
horizontal stripes with a jagged edge, narrowing into a ragged spire. Seeds pick the size and a character
(full, slender, gappy, heavy, windswept)."""
from __future__ import annotations

import math

import numpy as np

from . import Asset
from ..mesh import Mesh, frustum


class _Tris:
    """triangles collected with an orientation hint, so every face points the way it should (out, up or down)."""

    def __init__(self):
        self.P, self.M, self.S, self.A = [], [], [], []

    def add(self, a, b, c, want, mat, snow, ao):
        a, b, c = (np.asarray(v, np.float64) for v in (a, b, c))
        if np.dot(np.cross(b - a, c - a), want) < 0:
            b, c = c, b
            snow = (snow[0], snow[2], snow[1])
            ao = (ao[0], ao[2], ao[1])
        self.P += [a, b, c]
        self.M += [mat] * 3
        self.S += list(snow)
        self.A += list(ao)

    def mesh(self) -> Mesh:
        n = len(self.P)
        return Mesh(np.array(self.P, np.float32), None, self.M, self.S, self.A,
                    np.arange(n).reshape(-1, 3)).flat()


def _ring(T, rng, cx, cz, r, y_bot, span, boughs, droop, snowy, ao_in, tooth=0.84, lip=0.62, collar=0.32, top=None):
    """one bough ring: apex (hidden in the ring above) -> a steep inner cone -> a flat shelf that holds the snow ->
    a broken snow lip on the bough tops -> a short drooping fringe of tips -> a dark underside back to the trunk."""
    ph = rng.uniform(0, 2 * math.pi)
    n = boughs * 2
    ay = y_bot + span if top is None else max(min(y_bot + span, top), y_bot + span * 0.5)
    apex = np.array([cx, ay, cz])                # kept inside the ring above, so no bald cone shows
    under = np.array([cx, y_bot + span * 0.25, cz])
    shelf = rng.uniform(0.68, 0.76)
    sh_y = y_bot + span * rng.uniform(0.2, 0.27)
    C, H, L, R, F = [], [], [], [], []
    for i in range(n):
        a = ph + 2 * math.pi * (i + rng.uniform(-0.2, 0.2)) / n
        tip = i % 2 == 0
        ca, sa = math.cos(a), math.sin(a)
        if tip:
            rr = r * rng.uniform(0.92, 1.08)
            yy = y_bot - droop * r * rng.uniform(0.6, 1.2)
            hr, hy = r * shelf, sh_y
            lf = rng.uniform(0.12, 0.38) if rng.random() < lip else 0.0
        else:
            rr = r * tooth * rng.uniform(0.95, 1.05)
            yy = y_bot + span * rng.uniform(0.0, 0.08)
            hr, hy = r * shelf * 0.9, sh_y + span * 0.04
            lf = rng.uniform(0.0, 0.15)
        cr = r * collar
        C.append(np.array([cx + ca * cr, y_bot + span * 0.42, cz + sa * cr]))
        H.append(np.array([cx + ca * hr, hy, cz + sa * hr]))
        R.append(np.array([cx + ca * rr, yy, cz + sa * rr]))
        L.append(H[-1] + (R[-1] - H[-1]) * lf)
        F.append(lf > 0.02 and snowy > 0.0)
    up = np.array([0.0, 1.0, 0.0])
    s3 = (snowy, snowy, snowy)
    for i in range(n):
        j = (i + 1) % n
        mid = (R[i] + R[j]) * 0.5
        out = np.array([mid[0] - cx, 0.0, mid[2] - cz])
        out /= max(np.linalg.norm(out), 1e-6)
        fo = out + up * 0.2
        # inner cone (mostly hidden by the ring above), then the flat shelf that catches the snow
        T.add(apex, C[i], C[j], up + out * 0.5, "pine", (snowy * 0.5, snowy * 0.5, snowy * 0.5), (ao_in, ao_in, ao_in))
        T.add(C[i], H[i], H[j], up, "pine", s3, (ao_in, 1.0, 1.0))
        T.add(C[i], H[j], C[j], up, "pine", s3, (ao_in, 1.0, ao_in))
        # the snow lip: snow lying on the bough tops, broken from bough to bough, seen from below
        if F[i]:
            T.add(H[i], L[i], L[j], fo, "snow", (1.0, 1.0, 1.0), (1.0, 1.0, 1.0))
        if F[j]:
            T.add(H[i], L[j], H[j], fo, "snow", (1.0, 1.0, 1.0), (1.0, 1.0, 1.0))
        # the fringe: needles falling to the tips
        T.add(L[i], R[i], R[j], fo, "pine", (0.0, 0.0, 0.0), (1.0, 0.9, 0.9))
        T.add(L[i], R[j], L[j], fo, "pine", (0.0, 0.0, 0.0), (1.0, 0.9, 1.0))
        # underneath: the dark band between tiers
        T.add(under, R[j], R[i], -up, "pine", (0.0, 0.0, 0.0), (0.3, 0.65, 0.65))


KINDS = ("full", "slender", "gappy", "heavy", "windswept")


def _spruce(seed, height, width, rings, young=False, kind="full"):
    """a whole spruce: trunk, `rings` bough rings narrowing upward to a slim leader. `kind` sets the character:
    full, slender, gappy (thin whorls that show the trunk), heavy (snow-laden, drooping), windswept (leaning).
    Each seed also carries its own snow load, so a crowd of them varies in value, not only in shape."""
    rng = np.random.default_rng(seed)
    lip = float(np.random.default_rng(seed + 50000).uniform(0.4, 0.85))   # own stream: shapes stay put
    T = _Tris()
    base = height * (rng.uniform(0.0, 0.03) if young else rng.uniform(0.05, 0.12))
    top = height * rng.uniform(0.9, 0.93)
    lean = rng.uniform(-0.06, 0.06, 2) * width
    droop = rng.uniform(0.12, 0.22)
    fat = rng.uniform(0.75, 0.9)                 # envelope exponent: lower is a fuller crown
    snowy = 1.0 if young else 0.78
    thin = set()
    if kind == "slender":
        width *= 0.78
        rings += 2
        fat = rng.uniform(0.9, 1.05)
    elif kind == "gappy":
        thin = set(rng.choice(np.arange(1, rings - 2), size=min(3, rings - 3), replace=False).tolist())
        droop *= 1.3
    elif kind == "heavy":
        snowy = 1.0
        lip = 0.9
        droop = rng.uniform(0.24, 0.32)
        width *= 1.08
    elif kind == "windswept":
        a = rng.uniform(0, 2 * math.pi)
        lean = np.array([math.cos(a), math.sin(a)]) * width * rng.uniform(0.18, 0.26)
        lip *= 0.6                               # the wind strips the boughs: a darker tree
    # ring heights: a little irregular, closer together toward the top
    t = np.linspace(0.0, 1.0, rings) ** 0.85
    t[1:-1] += rng.uniform(-0.22, 0.22, rings - 2) / rings
    ys = base + (top - base) * t
    for k in range(rings):
        u = (ys[k] - base) / (height - base)
        r = width * (1.0 - u) ** fat * rng.uniform(0.86, 1.12)
        if u > 0.65:
            r *= 1.0 - (u - 0.65) * 1.1          # the crown narrows into a spire
        if k in thin:
            r *= rng.uniform(0.38, 0.5)
        r = max(r, width * 0.08)
        gap = (ys[min(k + 1, rings - 1)] - ys[max(k - 1, 0)]) / (2 if 0 < k < rings - 1 else 1)
        span = max(gap * 1.5, r * 0.8)
        if k == rings - 1:
            span = height - ys[k]
            r = min(r, span * 0.34)
        cx, cz = lean * (u * u) + rng.uniform(-0.04, 0.04, 2) * width
        boughs = 17 if r > 2.4 else 15 if r > 1.9 else 13 if r > 1.5 else 11 if r > 1.1 else 9 if r > 0.75 else \
            7 if r > 0.45 else 5                    # teeth stay small on the broad lower rings seen up close
        tooth = 0.84 if r > 0.8 else 0.66 + 0.22 * r     # small rings near the top bite deeper: a ragged spire
        collar = 0.32 if r > 0.8 else 0.55          # small rings keep a full core: no bare stalk between them
        if k == rings - 1:                          # the leader: two little whorls, not one bald cone
            _ring(T, rng, cx, cz, r, ys[k], span * 0.5, boughs, droop, snowy, 0.8, tooth, lip, collar)
            r, span = r * 0.55, span * 0.58
            ys[k] += span * 0.72
        top = None if k == rings - 1 else ys[k + 1] + 0.4 * (ys[k + 1] - ys[k])
        _ring(T, rng, cx, cz, r, ys[k], span, boughs, droop * (0.8 + 0.8 * u), snowy, 0.5 + 0.3 * u, tooth,
              lip, collar, top)
    m = T.mesh()
    trunk = min(ys[min(3, rings - 1)] + 0.2, height * 0.55)
    m = m + frustum(0.07 * width + 0.04, 0.04 * width + 0.02, trunk, "bark", segs=5, ao=0.8)
    return m.turn(yaw=float(rng.uniform(0, 360)))


def build(seed=0) -> Asset:
    """a full spruce, 7-12 m, narrow and jagged; seed picks the shape and its character (see KINDS)"""
    rng = np.random.default_rng(1000 + seed)
    h = float(rng.uniform(7.0, 12.0))
    w = h * float(rng.uniform(0.27, 0.33))
    kind = KINDS[seed % len(KINDS)]
    rings = int(h * 1.25) + int(rng.integers(-1, 2))  # thin tiers: the horizontal stripe rhythm of the reference
    return Asset(_spruce(seed, h, w, rings, kind=kind), collide=0.5)


def build_small(seed=0) -> Asset:
    """a young spruce, 1.4-3 m, full to the ground and heavier with snow"""
    rng = np.random.default_rng(2000 + seed)
    h = float(rng.uniform(1.4, 3.0))
    kind = ("full", "heavy", "slender", "heavy")[seed % 4]
    return Asset(_spruce(seed + 77, h, h * float(rng.uniform(0.34, 0.4)), int(rng.integers(6, 9)), young=True,
                         kind=kind), collide=0.35)
