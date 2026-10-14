"""Shared helpers every map's place.py builds on: value noise, signed distances, dart throwing, the camera family.

The camera family (arena/STYLE.md): orthographic, looking along +v (the world's square grid turned 45 degrees), down
by the map's elevation EL; 1 m = PPM px across on every map. A point (u, v, z) lands on the map picture at
    sx = X0 + u * PPM,   sy = Y0 - (v * sin EL + z * cos EL) * PPM
and its depth (larger = further) is v * cos EL - z * sin EL.
"""
from __future__ import annotations

import math

import numpy as np

R2 = math.sqrt(2.0)
PPM = 32.0                      # map px per metre across, the same on every map (STYLE.md)
HUMAN = 1.7                     # the scale reference (m)
SUN_UV = (-0.62, 0.52)          # toward the sun, horizontal (u, v): the upper left of the picture, on every map


class Camera:
    """one map's orthographic camera: elevation (degrees), px per metre, picture size and origin"""

    def __init__(self, el_deg: float, ppm: float, w: int, h: int, x0: float, y0: float):
        self.el_deg, self.ppm, self.w, self.h, self.x0, self.y0 = el_deg, ppm, w, h, x0, y0
        self.el = math.radians(el_deg)
        self.se, self.ce = math.sin(self.el), math.cos(self.el)

    def proj(self, u, v, z=0.0):
        return self.x0 + u * self.ppm, self.y0 - (v * self.se + z * self.ce) * self.ppm

    def depth(self, u, v, z=0.0):
        return v * self.ce - z * self.se

    def screen_p(self, v, z):
        return v * self.se + z * self.ce

    def z_for_p(self, p, v):
        return (p - v * self.se) / self.ce

    def human_px(self, h=HUMAN):
        return h * self.ce * self.ppm


def sun_vec(el_rad: float, horiz=SUN_UV):
    """toward the sun in (u, v, z), for a sun `el_rad` above the horizon"""
    h = np.array(horiz[:2]) / np.linalg.norm(horiz[:2]) * math.cos(el_rad)
    return (float(h[0]), float(h[1]), math.sin(el_rad))


def to_xy(u, v):
    return (u + v) / R2, (v - u) / R2


def to_uv(x, y):
    return (x - y) / R2, (x + y) / R2


# ---------------------------------------------------------------- noise
def _hash(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def vnoise(u, v, scale, seed=0):
    """smooth value noise in [-1, 1] at feature size `scale` metres"""
    u = np.asarray(u, np.float64) / scale
    v = np.asarray(v, np.float64) / scale
    iu, iv = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    fu, fv = u - iu, v - iv
    fu, fv = fu * fu * (3 - 2 * fu), fv * fv * (3 - 2 * fv)
    a = _hash(iu, iv, seed); b = _hash(iu + 1, iv, seed)
    c = _hash(iu, iv + 1, seed); d = _hash(iu + 1, iv + 1, seed)
    return (a + (b - a) * fu + (c - a) * fv + (a - b - c + d) * fu * fv) * 2 - 1


def fbm(u, v, scale, seed=0, oct=3):
    s, amp, tot = 0.0, 1.0, 0.0
    for o in range(oct):
        s = s + amp * vnoise(u, v, scale / 2 ** o, seed + 17 * o)
        tot += amp
        amp *= 0.5
    return s / tot


def smooth(a, b, x):
    t = np.clip((np.asarray(x, np.float64) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- signed distances
def sd_box(u, v, b, r=1.0):
    """signed distance (m) to a rounded box (centre u, v, half sizes); negative inside"""
    cu, cv, hu, hv = b
    qx = np.abs(np.asarray(u, np.float64) - cu) - hu + r
    qy = np.abs(np.asarray(v, np.float64) - cv) - hv + r
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def sd_ellipse(u, v, cu, cv, ru, rv, p=2.0):
    """approximate signed distance (m) to a superellipse (exponent p): negative inside"""
    m = ((np.abs(np.asarray(u, np.float64) - cu) / ru) ** p + (np.abs(np.asarray(v, np.float64) - cv) / rv) ** p) ** (1 / p)
    return (m - 1) * min(ru, rv)


def smin(a, b, k):
    """polynomial smooth minimum: a union of two signed distances with its creases filleted over k metres"""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def poisson(rng, n_try, region, rmin, existing=()):
    """dart throwing: points from region() kept rmin apart (and from existing (u, v, r))"""
    out = []
    for _ in range(n_try):
        p = region(rng)
        if p is None:
            continue
        u, v, r = p
        ok = all((u - a) ** 2 + (v - b) ** 2 > (max(rmin, r * 0.5 + rr * 0.5)) ** 2 for a, b, rr in out)
        ok = ok and all((u - a) ** 2 + (v - b) ** 2 > (rr + r * 0.4) ** 2 for a, b, rr in existing)
        if ok:
            out.append((u, v, r))
    return out
