"""Signed-distance primitives, vectorized over (N, 3) point arrays.

Units are native pixels: a head of radius 5 is 10 px wide in the final sprite.
Axes: X right, Y forward (away from a south-facing viewer), Z up.
"""
from __future__ import annotations

import math
from typing import Dict, Sequence

import numpy as np


# pixel stamps are drawn on top of the render (Forge._stamps), never raymarched as shapes
STAMP_SHAPES = ("stamp", "stamp_row")

def rot_matrix(rx: float = 0.0, ry: float = 0.0, rz: float = 0.0) -> np.ndarray:
    """Euler degrees, applied X then Y then Z."""
    ax, ay, az = (math.radians(v) for v in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def _len(p: np.ndarray) -> np.ndarray:
    return np.sqrt(np.einsum("ij,ij->i", p, p))


def sd_ellipsoid(p: np.ndarray, r: Sequence[float]) -> np.ndarray:
    r = np.asarray(r, dtype=np.float64)
    k0 = _len(p / r)
    k1 = _len(p / (r * r))
    return np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -r.min())


def sd_round_cone(p: np.ndarray, a: Sequence[float], b: Sequence[float], r1: float, r2: float) -> np.ndarray:
    """Capsule from a (radius r1) to b (radius r2). Exact (Inigo Quilez)."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    ba = b - a
    l2 = float(ba @ ba)
    if l2 < 1e-9:
        return _len(p - a) - max(r1, r2)
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    xv = pa * l2 - np.outer(y, ba)
    x2 = np.einsum("ij,ij->i", xv, xv)
    y2 = y * y * l2
    z2 = z * z * l2
    k = math.copysign(1.0, rr) * rr * rr * x2
    out = (np.sqrt(x2 * a2 * il2) + y * rr) * il2 - r1
    m1 = np.sign(z) * a2 * z2 > k
    m2 = np.sign(y) * a2 * y2 < k
    out = np.where(m1, np.sqrt(x2 + z2) * il2 - r2, out)
    out = np.where(m2 & ~m1, np.sqrt(x2 + y2) * il2 - r1, out)
    return out


def sd_box(p: np.ndarray, half: Sequence[float], rounding: float = 0.0) -> np.ndarray:
    h = np.asarray(half, float) - rounding
    q = np.abs(p) - h
    return _len(np.maximum(q, 0.0)) + np.minimum(q.max(axis=1), 0.0) - rounding


def sd_cylinder(p: np.ndarray, r: float, h: float, rounding: float = 0.0) -> np.ndarray:
    """Vertical (Z) cylinder, half-height h."""
    d = np.stack([np.hypot(p[:, 0], p[:, 1]) - r + rounding, np.abs(p[:, 2]) - h + rounding], 1)
    return np.minimum(np.maximum(d[:, 0], d[:, 1]), 0.0) + _len(np.maximum(d, 0.0)) - rounding


def sd_torus(p: np.ndarray, R: float, r: float) -> np.ndarray:
    """Torus in the XY plane (a ring lying flat)."""
    q = np.stack([np.hypot(p[:, 0], p[:, 1]) - R, p[:, 2]], 1)
    return _len(q) - r


def sd_cone(p: np.ndarray, r: float, h: float) -> np.ndarray:
    """Cone with base radius r at z=0 and apex at z=h (a spike / hat / tree top)."""
    return sd_round_cone(p, (0, 0, 0), (0, 0, h), r, 0.01)


def sd_capped_cone(p: np.ndarray, r_base: float, r_top: float, h: float) -> np.ndarray:
    """Flat-capped cone/frustum along +z, base (radius r_base) at z=0, top (r_top) at z=h. Exact (Quilez)."""
    hh = h / 2
    qx = np.hypot(p[:, 0], p[:, 1])
    qy = p[:, 2] - hh
    k1 = np.array([r_top, hh])
    k2 = np.array([r_top - r_base, 2 * hh])
    rr = np.where(qy < 0, r_base, r_top)
    ca = np.stack([qx - np.minimum(qx, rr), np.abs(qy) - hh], 1)
    t = np.clip(((k1[0] - qx) * k2[0] + (k1[1] - qy) * k2[1]) / float(k2 @ k2), 0, 1)
    cb = np.stack([qx - k1[0] + k2[0] * t, qy - k1[1] + k2[1] * t], 1)
    sgn = np.where((cb[:, 0] < 0) & (ca[:, 1] < 0), -1.0, 1.0)
    return sgn * np.sqrt(np.minimum(np.einsum("ij,ij->i", ca, ca), np.einsum("ij,ij->i", cb, cb)))


def sd_roof(p: np.ndarray, half: Sequence[float], h: float, gable: bool = False) -> np.ndarray:
    """Pitched roof on a flat base at z = 0: footprint half [hx, hy], ridge height h, ridge along the
    longer axis. Hip roof (all four sides slope at one pitch; a square footprint gives a pyramid) or,
    with gable, vertical ends on the short sides."""
    hx, hy = float(half[0]), float(half[1])
    k = h / min(hx, hy)
    n = math.sqrt(1 + k * k)
    ax, ay, z = np.abs(p[..., 0]), np.abs(p[..., 1]), p[..., 2]
    dx = (k * (ax - hx) + z) / n
    dy = (k * (ay - hy) + z) / n
    if gable:
        if hx >= hy:
            dx = ax - hx
        else:
            dy = ay - hy
    return np.maximum(np.maximum(dx, dy), -z)


def smin(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def eval_prim(prim: Dict, p: np.ndarray) -> np.ndarray:
    """prim: {'shape':..., 'at':[x,y,z], 'rot':[rx,ry,rz], ...shape params}."""
    at = np.asarray(prim.get("at", (0, 0, 0)), float)
    q = p - at
    if "rot" in prim:
        q = q @ rot_matrix(*prim["rot"])  # inverse rotation (R^T applied as row-vector @ R)
    s = prim["shape"]
    if s in ("ellipsoid", "sphere"):
        r = prim.get("r", 1.0)
        r = (r, r, r) if np.isscalar(r) else r
        return sd_ellipsoid(q, r)
    if s == "capsule":
        return sd_round_cone(q, prim.get("a", (0, 0, 0)), prim["b"], prim.get("r1", prim.get("r", 1)),
                             prim.get("r2", prim.get("r", 1)))
    if s == "box":
        return sd_box(q, prim["half"], prim.get("round", 0.0))
    if s == "cylinder":
        return sd_cylinder(q, prim["r"], prim["h"], prim.get("round", 0.0))
    if s == "torus":
        return sd_torus(q, prim["R"], prim["r"])
    if s == "cone":
        if prim.get("flat") or "r_top" in prim:
            return sd_capped_cone(q, prim["r"], prim.get("r_top", 0.0), prim["h"]) - prim.get("round", 0.0)
        return sd_cone(q, prim["r"], prim["h"])
    if s == "roof":
        return sd_roof(q, prim["half"], prim["h"], prim.get("gable", False))
    raise ValueError("unknown shape %r" % s)
