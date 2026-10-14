"""Rope-fence bollard: a short timber post with a rounded iron cap that holds a cushion of snow, an iron band and eye."""
from __future__ import annotations

import numpy as np

from . import Asset
from ..mesh import Lines, box, cylinder, frustum, lathe, sphere

EYE = 0.68     # the rope eye's height above the post's foot (the layout hangs the rope here)


def build(seed=0) -> Asset:
    """a path bollard, ~0.9 m, rope eye anchor 'rope' near the top"""
    rng = np.random.default_rng(500 + seed)
    h = float(rng.uniform(0.80, 0.94))
    r = float(rng.uniform(0.058, 0.07))
    ph = float(rng.uniform(0, 60))
    m = frustum(r * 1.08, r * 0.94, h, "wood", segs=6, phase=ph)
    m.A[:] = np.clip(0.75 + 2.5 * m.P[:, 1], 0, 1)                      # damp, darker where it meets the snow
    # a rounded iron knob, smooth so it reads round; only its crown takes the snow, the rest stays slate-blue
    cap = [(r * 0.95, h - 0.02, "metal", 0.0), (r * 1.18, h + 0.01, "metal", 0.0), (r * 1.22, h + 0.05, "metal", 0.0),
           (r * 1.08, h + 0.10, "metal", 0.0), (r * 0.65, h + 0.135, "metal", 1.0), (0.001, h + 0.15)]
    m = m + lathe(cap, "metal", segs=10, smooth=True, cap_bottom=True, cap_top=False)
    # the cushion of snow on the crown, a crescent from the side; it leans off the knob a little by seed
    lean = rng.uniform(-0.1, 0.1, 2) * r
    m = m + sphere(r * 0.95, "drift", segs=10, rings=4, squash=0.55, smooth=True).at(lean[0], h + 0.105, lean[1])
    # the iron band with its eye, where the rope hangs
    m = m + cylinder(r * 1.12, 0.04, "metal", segs=6, phase=ph, ao=0.8).at(0, EYE - 0.02, 0)
    m = m + box(0.03, 0.05, 0.05, "metal").at(r * 1.2, EYE - 0.025, 0)
    # snow banked round the foot
    m = m + lathe([(0.30, -0.04), (0.22, 0.04), (0.13, 0.08), (r * 1.1, 0.10)], "drift", segs=10, smooth=True,
                  cap_bottom=False, cap_top=False)
    lines = Lines().add("seam", [[-r * 0.98, h * 0.25, -r * 0.2], [-r * 0.94, h * 0.62, -r * 0.25]])   # a split in the grain
    tilt = rng.uniform(-8, 8, 2)
    m = m.turn(pitch=float(tilt[0]), roll=float(tilt[1]))
    lines = lines.turn(pitch=float(tilt[0]), roll=float(tilt[1]))
    eye = np.array([0.0, EYE, 0.0])
    return Asset(m, lines=lines, collide=0.14, anchors={"rope": eye.tolist()}, sink=0.08)
