"""Snow-buried shrub: two to four young spruce tips poking out of one soft drift."""
from __future__ import annotations

import math

import numpy as np

from . import Asset
from ..mesh import sphere
from .pine import _spruce


def build(seed=0) -> Asset:
    """a soft drift with 2-4 young spruce, 0.8-1.6 m, half buried in it"""
    rng = np.random.default_rng(3000 + seed)
    rad = float(rng.uniform(0.5, 0.95))
    # a buried ball: only its soft cap shows, so the drift runs into the snow field without an edge
    m = sphere(rad * 1.6, "snow", segs=10, rings=6, snow=1.0, smooth=True, squash=0.32).at(0, -rad * 0.62, 0)
    for k in range(int(rng.integers(2, 5))):
        a = rng.uniform(0, 2 * math.pi)
        d = rad * rng.uniform(0.0, 0.55)
        h = float(rng.uniform(0.8, 1.6))
        tips = _spruce(int(seed * 7 + k), h, h * float(rng.uniform(0.34, 0.42)), int(rng.integers(5, 8)), young=True,
                       kind="heavy")
        m = m + tips.at(math.cos(a) * d, -0.05, math.sin(a) * d)
    return Asset(m, collide=rad * 0.8)
