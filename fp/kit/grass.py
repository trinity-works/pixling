"""Dry grass poking through the snow: a tuft of 1 px blades fanning out of one clump, slate and blue, some bent over."""
from __future__ import annotations

import math

import numpy as np

from . import Asset
from ..mesh import Lines, Mesh


def _blade(rng, a, r0, h, fan, bent):
    """a curved blade: rises from the clump, leans out along `a`, and (bent) folds over near the tip."""
    x0, z0 = math.cos(a) * r0, math.sin(a) * r0
    la = a + rng.uniform(-0.5, 0.5)
    cl, sl = math.cos(la), math.sin(la)
    pts = []
    for t in (0.0, 0.35, 0.7, 1.0):
        k = max(t - 0.55, 0.0) ** 2 * 4.0 if bent else 0.0
        out = fan * h * t ** 1.8 + 0.6 * h * k
        y = h * (t - 0.6 * k)
        pts.append([x0 + cl * out, y, z0 + sl * out])
    return pts


def build(seed=0) -> Asset:
    """a tuft of 3-7 dry blades, 18-55 cm, fanning out of one clump; each tuft keeps one tone (slate or blue)
    with the odd blade of the other, the way the reference's clumps read"""
    rng = np.random.default_rng(700 + seed)
    L = Lines()
    n = int(rng.integers(3, 8))
    tall = rng.uniform(0.28, 0.55)
    tone, odd = ("grass_dry", "grass") if seed % 5 < 3 else ("grass", "grass_dry")
    for i in range(n):
        a = 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / n + rng.uniform(0, 2 * math.pi)
        h = tall * rng.uniform(0.45, 1.0)
        pts = _blade(rng, a, rng.uniform(0.0, 0.05), h, rng.uniform(0.15, 0.45), rng.random() < 0.15)
        L.add(odd if rng.random() < 0.2 else tone, pts)
    return Asset(Mesh(), lines=L, shadow=False)
