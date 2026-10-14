"""Emberleaf Hollow's level hooks for the shared level engine (arena/level.py): the props' collision shapes (matching
blender.py's geometry), the spawns, the fairness targets of a kill map, the chokepoints and the surfaces.

One level: the knoll (1.1 m) stays under rules.high_ground_z, so the whole hollow is the ground; there is no deck
(nav layer 1 is empty). The pond is outside the walkable (its bank is a lip: it stops movement, never sight or shots).
"""
from __future__ import annotations

import math

import numpy as np

from . import place as P
from .palette import UNIT_HUES

SURF = {"grass": 1, "dirt": 2}
SPEED = {"grass": 0.95, "dirt": 1.0}
SURF_NOTE = "speed multipliers: the grass a little slower than the trodden dirt"
GRID_LEGEND = {"0": "blocked", "1": "grass", "2": "dirt"}
ALCOVES = {}
SIDES = ("west", "east")
DECK = False
COVER_KINDS = ("log", "stump", "oak", "pine", "bush", "waystone", "crates")
LEGACY_PROPS = ("waystone", "lantern", "fire", "potlight")
ART_KINDS = {"oak", "pine", "bush", "stump", "log", "waystone", "lantern", "crates",
             "banner", "fire"}
SPAWN_RINGS = ((2.4, 0.0), (3.4, 0.26))
OCCLUDERS_NOTE = ("occ.json + occ.png: every tree, bush and prop cut out of map.png with its depth d. Draw a cut-out "
                  "over a unit whose depth is larger (further) than d and whose box it overlaps.")


def _g(u, v):
    return float(P.terrain(np.array(u), np.array(v)))


def props(lay, box, circ, seg, HIGH_Z):
    """collision shapes of everything placed, in metres, matching blender.py's geometry"""
    for t in lay["things"]:
        kind = t["kind"]
        u, v = t["u"], t["v"]
        g = _g(u, v)
        if kind == "oak":
            circ("oak", u, v, 0.42, g, g - 0.3, g + t["h"])
        elif kind == "pine":
            circ("pine", u, v, 0.45 + 0.03 * t["h"], g, g - 0.3, g + t["h"])
        elif kind == "bush":
            r = t.get("rad", t.get("r") or 1.0)
            circ("bush", u, v, 0.78 * r, g, g - 0.2, g + t["h"])
        elif kind == "boulder":
            circ("boulder", u, v, 0.95 * t["r"], g, g - 0.2, g + t["h"] - t.get("sink", 0.0))
        elif kind == "crag":
            circ("crag", u, v, 0.9 * t["r"], g, g - 0.2, g + t["h"])
        elif kind == "stump":
            circ("stump", u, v, t["r"], g, g - 0.2, g + t["h"])
        elif kind == "log":
            a = math.radians(t["rot"])
            du, dv = math.cos(a) * t["len"] / 2, math.sin(a) * t["len"] / 2
            seg("log", (u - du, v - dv), (u + du, v + dv), t["r"], g, g - 0.1, g + 2 * t["r"])
            # the root plate standing up at its north end (the big log only)
            if t.get("plate", True):
                box("log", u + du * 1.04, v + dv * 1.04, 0.75, 0.2, a + math.pi / 2, g, g - 0.1, g + 1.45)
        elif kind == "ruinwall":
            box("ruinwall", u, v, t["len"] / 2, 0.36, math.radians(t["rot"]), g, g - 0.2, g + t["h"])
        elif kind == "waystone":
            circ("waystone", u, v, 0.3, g, g - 0.2, g + t["h"])
        elif kind == "lantern":
            circ("lantern", u, v, 0.12, g, g - 0.2, g + t["h"])
        elif kind == "crates":
            circ("crates", u + 0.25, v, 0.55, g, g - 0.1, g + 1.1)
        elif kind == "banner":
            circ("banner", u, v, 0.08, g, g - 0.2, g + t["h"])
        elif kind == "fire":
            circ("fire", u, v, 0.5, g, g - 0.1, g + 0.2)


def surfaces(UU, VV, wl, inside, Zc, shape_dist, SURF_, RAMP_BIT):
    """per nav cell: grass, or the dirt of the fighting ground, the glades and the paths"""
    surf = np.full(UU.shape, SURF["grass"], np.uint8)
    surf[P.sd_dirt(UU, VV) < 0] = SURF["dirt"]
    return surf, []


def spawn_origin(side):
    cu, cv = P.SPAWNS[side]
    s = 1 if side == "east" else -1
    u = cu - s * 1.0
    return (u, cv, _g(u, cv))


def spawn_centre():
    return P.SPAWNS["west"]


def spawn_area(side):
    return dict(u=P.SPAWNS[side][0], v=P.SPAWNS[side][1], r=4.0), 6.5


def levels(A, HIGH_Z):
    return [dict(id=0, name="ground", layer=0,
                 note="the whole hollow: one level (the knoll's 1.1 m stays under high_ground_z); no deck")]


def objectives(lv, lay):
    return []                                     # a kill map: team annihilation, nothing to capture


def _target(lv, id_, kind, side, u, v, r):
    return dict(id=id_, kind=kind, side=side, u=u, v=v, z=lv.hf_z(u, v), level=0, capture_r=r)


def zone_extras(lv, lay):
    """the mode, and the places both sides race to (check.py's fairness: each against its mirror)"""
    t = [_target(lv, "centre", "centre", None, 0.0, 0.9, 2.6),
         _target(lv, "knoll", "knoll", None, 0.0, 7.6, 2.2),
         _target(lv, "south lane", "south lane", None, 0.0, -4.4, 1.2)]
    for side, (cu, cv) in P.SPAWNS.items():
        t.append(_target(lv, f"spawn {side}", "spawn", side, cu, cv, 2.0))
    return dict(mode=dict(kind="annihilation", note="team deathmatch to the last unit: no objectives, no capture; "
                                                     "the targets are where the fights happen, for AI and for the "
                                                     "fairness check"),
                targets=t,
                unit_hues=dict(bands={k: list(v) for k, v in UNIT_HUES.items()},
                               rule="team colours from these hue bands (no map pixel shows them above chroma 0.2); "
                                    "every unit carries a 1 px ink outline and a 1 px light rim (arena/STYLE.md)"))


def chokepoints():
    return [("north lane over the knoll", (0.0, 7.6), (0, 1), 0),
            ("north lane west of the knoll", (-11.0, 6.8), (0, 1), 0),
            ("north lane east of the knoll", (11.0, 6.8), (0, 1), 0),
            ("south lane by the pond", (0.0, -4.6), (0, 1), 0),
            ("west spawn north exit", (-17.5, 6.0), (0, 1), 0), ("west spawn south exit", (-17.5, -4.8), (0, 1), 0),
            ("east spawn north exit", (17.5, 6.0), (0, 1), 0), ("east spawn south exit", (17.5, -4.8), (0, 1), 0)]
