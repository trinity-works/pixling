"""Telephone pole: a tall leaning timber with a braced crossarm under snow, insulators and a few odd extras by seed."""
from __future__ import annotations

import numpy as np

from . import Asset
from ..mesh import Lines, box, cylinder, frustum, sphere


def build(seed=0) -> Asset:
    """a timber telephone pole, ~8.5 m, crossarm across x; anchors w0..w3 are the wire points"""
    rng = np.random.default_rng(300 + seed)
    H = float(rng.uniform(8.0, 9.0))
    m = frustum(0.15, 0.10, H, "wood", segs=7, phase=float(rng.uniform(0, 50)))
    m.A[:] = np.clip(0.72 + m.P[:, 1] / 60.0, 0, 0.86)                  # weathered timber stays dark
    m = m + sphere(0.11, "snow", segs=6, rings=2, snow=1.0, squash=0.5, smooth=True).at(0, H - 0.02, 0)
    # crossarm with two braces, a cushion of snow along it
    arm_y = H - 0.55
    m = m + box(2.0, 0.11, 0.11, "wood", snow=1.0).at(0, arm_y, 0)
    m = m + box(1.9, 0.05, 0.13, "snow", snow=1.0).at(0, arm_y + 0.11, 0)
    for s in (-1, 1):
        m = m + box(0.04, 0.62, 0.04, "wood").turn(roll=s * 52).at(s * 0.26, arm_y - 0.42, 0.07)
    anchors = {}
    for i, x in enumerate((-0.84, 0.42, 0.84)):
        m = m + cylinder(0.045, 0.13, "chrome", segs=5).at(x, arm_y + 0.11, 0)
        anchors["w%d" % i] = [x, arm_y + 0.24, 0.0]
    if seed % 2:
        m = m + cylinder(0.045, 0.13, "chrome", segs=5).at(-0.42, arm_y + 0.11, 0)      # a spare, no wire
    # a short lower arm carrying the phone line
    low = arm_y - 0.75
    m = m + box(1.0, 0.09, 0.09, "wood", snow=1.0).at(0, low, 0)
    for x in (-0.4, 0.4):
        m = m + cylinder(0.04, 0.11, "chrome", segs=5).at(x, low + 0.09, 0)
    anchors["w3"] = [-0.4, low + 0.2, 0.0]
    lines = Lines()
    kind = seed % 3
    if kind == 1:
        # a transformer can, snow on its lid, a drop wire down the pole
        y = low - 1.1
        m = m + cylinder(0.24, 0.72, "metal", segs=8).at(0, y, -0.32) + box(0.06, 0.06, 0.2, "metal").at(0, y + 0.45, -0.17)
        m = m + sphere(0.23, "snow", segs=8, rings=2, snow=1.0, squash=0.28, smooth=True).at(0, y + 0.70, -0.32)
        lines.add("wire", [[0.18, y + 0.72, -0.32], [0.30, y + 0.95, -0.2], [0.42, low + 0.18, 0.0]])
    elif kind == 2:
        # a little enamel sign at eye height
        m = m + box(0.3, 0.22, 0.03, "canvas").at(0, 1.75, -0.13) + box(0.31, 0.03, 0.05, "snow", snow=1.0).at(0, 1.97, -0.13)
    # climbing steps
    for k in range(4):
        y = 2.6 + k * 0.42
        m = m + box(0.30, 0.035, 0.035, "metal").turn(yaw=90 * (k % 2)).at(0, y, 0)
    # snow banked at the foot
    m = m + sphere(0.42, "snow", segs=8, rings=3, snow=1.0, squash=0.32, smooth=True).at(0, 0.18, 0)
    if seed in (0, 5):
        # the end poles are held by a guy wire
        lines.add("wire", [[0.0, H * 0.72, 0.0], [0.0, 0.25, 3.2]])
    lean = float(rng.uniform(-2.0, 2.0))
    m = m.turn(roll=lean)
    lines = lines.turn(roll=lean)
    R = np.radians(lean)
    for k, v in anchors.items():
        x, y, z = v
        anchors[k] = [x * np.cos(R) - y * np.sin(R), x * np.sin(R) + y * np.cos(R), z]
    return Asset(m, lines=lines, collide=0.3, anchors=anchors, sink=0.3)
