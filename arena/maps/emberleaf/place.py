"""Emberleaf Hollow: a kill map (team annihilation, no objectives) in a clearing of red-crowned trees on a forested
plateau, laid out in metres.

Axes and camera as every arena map (arena/geo.py, arena/STYLE.md): u left -> right, v into the picture, z up;
orthographic, looking along +v and down by EL; 1 m = 51.2 px across. EL is 68 degrees here (picked from a 62 / 68 / 74
test: arena/STYLE.md "camera family"); ARENA_EL overrides it for such tests.

The layout:
- two spawn glades (west, east) at the ends, each tucked behind a thicket of bushes round a red tree (the screen),
  left by a north and a south exit, a small camp at each glade's back rim;
- the fighting ground in the middle: an oval of packed granular dirt, 27 x 9 m, with a fallen log across its middle
  (half cover, forces a choice), two shorter logs and stumps each side, mirrored;
- the north lane through the grass, over a low knoll (1.1 m, the one height feature) with a fallen trunk on each
  shoulder; the south lane through the grass between the fighting ground and the pond;
- no rocks bigger than a pebble anywhere: cover is wood and leaves;
- the pond notches the front edge (a soft obstacle: blocks movement, not sight or shots);
- the frame: red-crowned trees and dark pines all round; past the back edge the plateau drops into a valley (layered
  canopy receding into haze, the valley floor with a river, far hills, the sky).

Every element and every pixel belongs to a depth ZONE (arena/zones.py).
"""
from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path

import numpy as np

from ...geo import (HUMAN, SUN_UV, Camera, fbm, poisson, sd_box, sd_ellipse, smin, smooth, to_uv, to_xy,  # noqa: F401
                    vnoise)

NAME = "emberleaf_hollow"
EL_DEG = float(os.environ.get("ARENA_EL", "68"))
PPM = 51.2                          # 1.6 x the family's 32: a 1.7 m person stands 32.6 px tall at 68 degrees
EL = math.radians(EL_DEG)
SE, CE = math.sin(EL), math.cos(EL)
R2 = math.sqrt(2.0)
SUN = (SUN_UV[0], SUN_UV[1], 0.0)
SUN_EL = math.radians(40.0)          # a late-afternoon sun: long soft shadows from the frame onto the field
CLIFF = 26.0                         # metres down the plateau's back edge to the valley floor
SEED = 23

# ---------------------------------------------------------------- the plan (metres)
FIELD = (0.0, 0.0, 28.3, 10.4, 3.2)           # the hollow: centre u, v, half sizes, superellipse exponent
GROUND = (0.0, 0.6, 13.4, 4.4, 2.4)           # the fighting ground (packed dirt): 1.41 x round 4's area
SPAWNS = {"west": (-21.5, 0.5), "east": (21.5, 0.5)}
GLADE_R = 3.5                                  # the spawn glades' dirt floor
KNOLL = (0.0, 7.7, 5.6, 1.1)                  # the knoll: centre u, v, radius, height
POND = (0.0, -8.4, 5.2, 2.4)                  # the pond: centre u, v, half sizes (it notches the front edge)
WATER_Z = -0.07                                # its surface
BACK_EDGE = 13.8                               # the plateau's lip behind the knoll (centre)
# forest bites into the hollow's outline (mirrored): u, v, radius
BITES = [(13.2, -11.2, 2.6), (12.8, 11.4, 2.2), (28.6, 7.4, 3.2), (28.8, -6.6, 3.0), (5.8, 11.6, 1.4)]
# the dirt paths from each spawn's exits into the fighting ground (written west; mirrored)
PATHS = [[(-19.6, -1.6), (-17.6, -4.1), (-14.0, -4.8), (-11.6, -3.4), (-9.6, -0.8)]]
PATH_HW = 1.0
# the routes (u, v, level), written from the west
LANES = {
    "north": [(-23.5, 0.5, 0), (-20.8, 4.6, 0), (-16.0, 6.6, 0), (-8.0, 7.4, 0), (0.0, 7.0, 0), (8.0, 7.4, 0),
              (16.0, 6.6, 0), (20.8, 4.6, 0), (23.5, 0.5, 0)],
    "centre": [(-23.5, 0.5, 0), (-20.8, -3.4, 0), (-15.5, -4.6, 0), (-8.0, -1.2, 0), (0.0, -1.8, 0), (8.0, -1.2, 0),
               (15.5, -4.6, 0), (20.8, -3.4, 0), (23.5, 0.5, 0)],
    "south": [(-23.5, 0.5, 0), (-20.8, -3.4, 0), (-15.5, -4.6, 0), (-9.0, -4.6, 0), (0.0, -4.4, 0), (9.0, -4.6, 0),
              (15.5, -4.6, 0), (20.8, -3.4, 0), (23.5, 0.5, 0)],
}

# ---------------------------------------------------------------- the picture: framed from the layout
W = 3072                             # the same 60 m across as a 1920 px map at 32 px/m, at 1.6 x the pixels
H = 1728
FRONT_PX = int(os.environ.get("ARENA_FRONT_PX", "208"))   # the hollow's front edge lands this far above the bottom
PLAY_FRONT = -10.4


def _frame():
    y0 = H - FRONT_PX + PLAY_FRONT * SE * PPM
    return W / 2, float(round(y0))


X0, Y0 = _frame()
CAM = Camera(EL_DEG, PPM, W, H, X0, Y0)


def proj(u, v, z=0.0):
    return X0 + u * PPM, Y0 - (v * SE + z * CE) * PPM


def screen_p(v, z):
    return v * SE + z * CE


def z_for_p(p, v):
    return (p - v * SE) / CE


def depth(u, v, z=0.0):
    return v * CE - z * SE


def sun_vec():
    h = np.array(SUN[:2]) / np.linalg.norm(SUN[:2]) * math.cos(SUN_EL)
    return (float(h[0]), float(h[1]), math.sin(SUN_EL))


# ---------------------------------------------------------------- the land
POOLS = [(19.4, -8.7, 1.7, 1.1)]                  # small mirrored pools at the front corners (u, v, half sizes)


def sd_pond(u, v):
    """the pond and the small pools (negative inside)"""
    d = sd_main_pond(u, v)
    for pu, pv, hu, hv in POOLS:
        for s_ in (-1, 1):
            d = np.minimum(d, sd_ellipse(u, v, s_ * pu, pv, hu, hv, 2.0) + 0.3 * fbm(np.abs(u), v, 0.9, 55)
                           + 0.12 * fbm(np.abs(u), v, 0.4, 56))
    return d


def sd_main_pond(u, v):
    cu, cv, hu, hv = POND
    d = sd_ellipse(u, v, cu, cv, hu, hv, 2.0) + 0.55 * fbm(np.abs(u), v, 2.2, 51) + 0.2 * fbm(np.abs(u), v, 0.9, 52)
    for s_ in (-1, 1):                                       # a bay on each side
        d = smin(d, np.hypot(np.asarray(u) - s_ * 4.6, np.asarray(v) - (cv + 0.9)) - 1.1, 0.8)
    return d


def water_outline(cu, cv, hu, hv, n=120):
    """the outline of a water body as the Blender surface's rim: along each ray from its middle, the first point
    where the bank stands above the water (a little past the waterline, so the terrain itself cuts the shore)"""
    pts = []
    for j in range(n):
        a = j / n * math.tau
        f = 0.3
        while f < 2.4:
            u_, v_ = cu + math.cos(a) * hu * f, cv + math.sin(a) * hv * f
            if float(terrain(np.array(u_), np.array(v_))) > WATER_Z + 0.05 or float(sd_pond(u_, v_)) > 0.5:
                break
            f += 0.01
        pts.append((round(u_, 4), round(v_, 4)))
    return pts


def sd_knoll(u, v):
    return np.hypot(np.asarray(u) - KNOLL[0], np.asarray(v) - KNOLL[1]) - KNOLL[2]


def sd_play(u, v):
    """signed distance to the walkable hollow: its outline, the forest's bites into it, minus the pond"""
    return np.maximum(sd_hollow(u, v), -(sd_pond(u, v) + 0.15))


def sd_hollow(u, v):
    """the hollow's outline with the forest's bites, the pond not cut out"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64)
    cu, cv, ru, rv, p = FIELD
    d = sd_ellipse(u, v, cu, cv, ru, rv, p)
    for bu, bv, br in BITES:
        for s in (-1, 1):
            d = -smin(-d, np.hypot(u - s * bu, v - bv) - br, 1.6)
    return d + 0.45 * fbm(np.abs(u), v, 2.6, 3)            # mirrored noise: the walkable is exactly symmetric


def sd_shelf(u, v):
    """the plateau's top round the hollow where the frame's trees stand; it ends at the back edge (the drop)"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64)
    edge = BACK_EDGE + 2.4 * smooth(6.0, 26.0, np.abs(u)) + 0.9 * fbm(u, v, 3.5, 7)
    return v - edge


def sd_plateau(u, v):
    return np.minimum(sd_play(u, v), sd_shelf(u, v))


def lane_dist(u, v):
    """distance (m) from the nearest dirt path (the spawn paths, mirrored) or 0 inside the fighting ground"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64)
    best = np.full(np.shape(u), 1e9)
    for pts in PATHS:
        for s in (-1, 1):
            for (a, b), (c, d) in zip(pts, pts[1:]):
                a, c = s * a, s * c
                du, dv = c - a, d - b
                t = np.clip(((u - a) * du + (v - b) * dv) / (du * du + dv * dv), 0, 1)
                best = np.minimum(best, np.hypot(u - a - t * du, v - b - t * dv))
    return best


def sd_dirt(u, v):
    """the dirt: the fighting ground, the spawn glades and the paths between them (negative inside)"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64)
    cu, cv, ru, rv, p = GROUND
    d = sd_ellipse(u, v, cu, cv, ru, rv, p)
    for s in (-1, 1):
        d = smin(d, np.hypot(u - s * SPAWNS["east"][0], v - SPAWNS["east"][1]) - GLADE_R, 1.5)
    d = smin(d, lane_dist(u, v) - PATH_HW - 0.06 * fbm(u, v, 3.0, 63), 0.8)
    return d + 0.1 * fbm(u, v, 2.2, 61) + 0.03 * fbm(u, v, 0.6, 62)              # firm, clean edges


def terrain(u, v):
    """height of the ground in metres: a calm hollow, the knoll, the pond's basin, the plateau's back edge and drop"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64)
    au = np.abs(u)                                          # mirrored: both sides play the same ground
    z = 0.16 * fbm(au, v, 8.0, 1) + 0.06 * fbm(au, v, 2.5, 2)
    # the hollow lies a little lower than the forest floor round it
    z += 0.35 * smooth(0.5, 5.0, sd_hollow(u, v))
    # the knoll
    kr = np.hypot(u - KNOLL[0], v - KNOLL[1]) / KNOLL[2]
    z += KNOLL[3] * (1 - smooth(0.0, 1.0, kr)) ** 1.0 * (1 - 0.15 * fbm(au, v, 2.0, 9))
    # the pond's basin: the bank dips to the water and under it
    dp = sd_pond(u, v)
    z = z - (0.25 + 0.55 * smooth(-0.2, -1.6, dp)) * (1 - smooth(-0.15, 0.45, dp))   # a firm bank
    z = z + 0.14 * smooth(0.05, 0.4, dp) * (1 - smooth(0.9, 1.8, dp))     # the bank stands a little proud
    # the plateau's back edge: a rocky drop in ledges to the valley
    d = sd_shelf(u, v)
    drop = smooth(-0.2, 3.0, d + 0.3 * fbm(u, v, 1.4, 19))
    ledge = 0.5 + 0.5 * fbm(u * 1.2, v * 1.2, 2.5, 4)
    zc = -CLIFF * drop ** (0.8 + 0.6 * ledge)
    step_h = 2.4 + 0.8 * fbm(u, v, 5.0, 12)
    q = zc / step_h
    fq = np.floor(q)
    zc = (fq + smooth(0.55, 1.0, q - fq)) * step_h
    return z + zc


def slope(u, v, e=0.25):
    du = (terrain(u + e, v) - terrain(u - e, v)) / (2 * e)
    dv = (terrain(u, v + e) - terrain(u, v - e)) / (2 * e)
    return np.hypot(du, dv)


def _g(u, v):
    return float(terrain(np.array(u), np.array(v)))


# ---------------------------------------------------------------- the things on it
def layout(seed: int = SEED) -> dict:
    """everything placed. Each thing: kind, u, v, zone (focus / playfield / frame), and its own fields. Mirrored
    west <-> east wherever it changes how people move or see"""
    rng = random.Random(seed)
    things = []
    keep = []                                       # (u, v, r) clear zones and placed solids

    def add(**t):
        things.append(t)
        return t

    def pair(**t):
        """a thing and its mirror (u -> -u, rot -> 180 - rot)"""
        a = add(**t)
        b = dict(t, u=-t["u"])
        if "rot" in t:
            b["rot"] = 180.0 - t["rot"]
        if "side" in t:
            b["side"] = "east" if t["side"] == "west" else "west"
        add(**b)
        keep.extend([(a["u"], a["v"], t.get("r", 0.6) + 0.4), (b["u"], b["v"], t.get("r", 0.6) + 0.4)])
        return a, b

    # --- the spawns: a carved wooden totem with a glowing rune at the back of each glade (focus: the side's mark),
    # wooden lantern posts at the exits
    for side, (cu, cv) in SPAWNS.items():
        s = -1 if side == "west" else 1
        add(kind="waystone", side=side, u=cu + s * 3.7, v=cv + 0.2, r=0.5, h=1.8, zone="focus", seed=rng.randrange(1 << 20))
        keep.append((cu + s * 3.7, cv + 0.2, 1.6))
    rng2 = random.Random(seed + 1)
    for (u, v) in ((-17.6, 5.2), (-17.8, -4.0)):
        pair(kind="lantern", side="west", u=u, v=v, r=0.2, h=1.4, zone="focus")

    # --- the spawn screens: a thicket (dense bushes round a red tree) in front of each glade; it hides each side's
    # spawn from the other's (check: no spawn point sees one of the other side). No rocks on this map: cover is wood
    # and leaves (logs, stumps, trees, bushes)
    for (u, v, r, h) in ((-15.6, -1.55, 1.5, 2.1), (-15.4, 2.65, 1.45, 2.1), (-17.1, 0.4, 1.1, 1.9),
                         (-16.5, -0.3, 0.95, 1.9), (-16.3, 1.6, 0.95, 1.9)):
        pair(kind="bush", u=u, v=v, r=r, rad=r, h=h, cls="green", seed=rng.randrange(1 << 20), zone="frame", cover=True)
    pair(kind="oak", u=-15.9, v=0.75, h=8.0, r=0.5, crown=2.5, cls="coral", seed=rng.randrange(1 << 20), zone="frame")
    pair(kind="bush", u=-14.6, v=0.4, r=1.0, h=1.9, cls="red", seed=rng.randrange(1 << 20), zone="frame")

    # --- the fighting ground: a fallen log across its middle (along v: half cover that splits the straight line; a
    # root plate at its north end, a split end at its south), two shorter logs each side, stumps at its ends, mirrored
    add(kind="log", u=0.0, v=0.9, len=3.6, r=0.42, rot=90.0, seed=rng.randrange(1 << 20), zone="frame", cover=True)
    keep.append((0.0, 1.0, 2.4))
    for (u, v, L_, rot) in ((-7.0, -1.7, 2.4, 14.0), (-6.2, 3.3, 2.0, -24.0)):
        pair(kind="log", u=u, v=v, len=L_, r=0.34, rot=rot, plate=False, seed=rng.randrange(1 << 20), zone="frame",
             cover=True)
    for (u, v, r) in ((-11.6, 1.9, 0.48), (-3.8, -3.3, 0.38), (-10.9, -2.2, 0.36)):
        pair(kind="stump", u=u, v=v, r=r, h=0.55, seed=rng.randrange(1 << 20), zone="frame", cover=True)

    # --- the north lane: a fallen trunk on the knoll's west and east shoulders, a bush clump higher up; the south lane
    # a stump by the pond
    pair(kind="log", u=-8.6, v=7.3, len=3.2, r=0.38, rot=12.0, plate=False, seed=rng.randrange(1 << 20), zone="frame",
         cover=True)
    pair(kind="bush", u=-2.9, v=9.4, r=0.95, rad=0.95, h=1.4, cls="green", seed=rng.randrange(1 << 20), zone="frame",
         cover=True)
    pair(kind="stump", u=-7.4, v=-6.4, r=0.5, h=0.6, seed=rng.randrange(1 << 20), zone="frame", cover=True)
    pair(kind="stump", u=-13.6, v=-7.4, r=0.45, h=0.5, seed=rng.randrange(1 << 20), zone="frame", cover=True)
    pair(kind="bush", u=-14.0, v=8.4, r=0.9, rad=0.9, h=1.5, cls="green", seed=rng.randrange(1 << 20), zone="frame",
         cover=True)
    for _ in range(4):                  # (keeps the frame's random stream where round 4 left it: same trees)
        rng.randrange(1 << 20)

    # --- the pond: slate stones in clumps of 2-4 with gaps where the grass and reeds reach the water, on the true
    # waterline; reeds in two clumps on the side away from the sun (dressing: no collision, the bank is the bound)
    rng3 = random.Random(seed + 2)
    cu, cv, hu, hv = POND

    def waterline(a):
        f = 1.4
        while f > 0.4 and float(terrain(np.array(cu + math.cos(a) * hu * f), np.array(cv + math.sin(a) * hv * f))) > WATER_Z:
            f -= 0.02
        return cu + math.cos(a) * hu * f, cv + math.sin(a) * hv * f
    # (no stones on the shore: grass, reeds and painted pebbles meet the water)
    for a0 in (-0.55, -0.95):                                      # the reeds: lower right, away from the sun
        for k in range(4):
            u, v = waterline(a0 + rng2.uniform(-0.12, 0.12))
            add(kind="reeds", u=u + rng2.uniform(-0.3, 0.3), v=v + rng2.uniform(-0.2, 0.2), r=0.0,
                seed=rng2.randrange(1 << 20), zone="frame")

    # --- the small pools at the front corners: a reed clump each, mirrored
    for pu, pv, hu, hv in POOLS:
        pair(kind="reeds", u=-pu + hu * 0.8, v=pv - hv * 0.6, r=0.0, seed=rng3.randrange(1 << 20), zone="frame")

    # --- ferns and leafy plants: at the hollow's inner foot and on the spawn islands, never in a lane
    def fern_region(r_):
        u = r_.uniform(-27, 27); v = r_.uniform(-11, 11)
        sp = float(sd_play(u, v))
        island = abs(abs(u) - 15.2) < 1.6 and abs(v - 0.6) < 3.6
        if not (-1.2 < sp < 0.1 or island) or float(sd_dirt(u, v)) < 0.8 or float(sd_pond(u, v)) < 0.6:
            return None
        return (u, v, 0.8)
    for u, v, r in poisson(random.Random(seed + 3), 1600, fern_region, 2.6, keep)[:20]:
        add(kind="fern", u=u, v=v, r=0.0, h=rng2.uniform(0.6, 1.0), seed=rng2.randrange(1 << 20), zone="frame")

    # --- the frame: red-crowned trees and dark pines all round on the forest floor; the centre back left open over
    # the knoll so the eye runs out to the valley; big trees at the front cut by the picture's edge
    def ring_region(r_):
        u = r_.uniform(-38, 38); v = r_.uniform(-19, 21)
        sp, sh = float(sd_play(u, v)), float(sd_shelf(u, v))
        if sp < 1.6 or sh > -1.2:
            return None
        if float(sd_pond(u, v)) < 1.4:
            return None
        if abs(u) > 23.0 and sp < 3.2:
            return None                              # the end caps stand back: the spawns are not under crowns
        if v < -8.0 and sp < 4.8 - 1.8 * float(smooth(26, 32, abs(u))):
            return None                              # the front: tall crowns stand back so the hollow's edge shows
        if abs(u) < 8.5 and v < -8.0 and sp < 6.0:
            return None                              # open in front of the pond
        if abs(u) < 7.5 + 4.0 * float(smooth(9, 15, v)) and v > 9.0:
            return None                              # the window over the knoll
        back = float(smooth(-4, 14, v))
        return (u, v, 1.9 + 0.6 * back)
    pts = poisson(rng, 9000, ring_region, 2.7, keep)
    for u, v, r in pts:
        pine_p = 0.32 + 0.4 * float(smooth(26, 36, abs(u))) + 0.25 * float(smooth(-12, -18, v))
        front = 1.0 - 0.3 * float(smooth(-9, -14, v))              # the front rows lower: crowns crop at the frame
        edge = float(sd_play(u, v)) < 3.5                          # the first row at the hollow: smaller, younger
        q = rng.random()
        if rng.random() < pine_p:
            h = rng.uniform(5.0, 7.0) if (edge and q < 0.5) else rng.uniform(8.5, 12.0) + 1.5 * float(smooth(0, 14, v))
            add(kind="pine", u=u, v=v, h=h * front, r=0.6, zone="frame", seed=rng.randrange(1 << 20))
        else:
            # oak size classes (a person is 1.7 m; the path 1.6 m wide): hero, standard, small, sapling
            if q < 0.12 and not edge:
                h, cr = rng.uniform(9.5, 10.5), rng.uniform(3.2, 3.6)
            elif q < 0.62:
                h, cr = rng.uniform(6.6, 7.8), rng.uniform(2.2, 2.7)
            elif q < 0.9 or not edge:
                h, cr = rng.uniform(4.6, 5.6), rng.uniform(1.5, 1.9)
            else:
                h, cr = rng.uniform(2.6, 3.2), rng.uniform(0.9, 1.15)
            add(kind="oak", u=u, v=v, h=h * front, r=0.5, crown=cr * (0.9 + 0.1 * front),
                cls=rng.choice(("coral", "coral", "ember")), seed=rng.randrange(1 << 20), zone="frame")
        keep.append((u, v, 1.0))
    # undergrowth along the hollow's edge: bushes (red and green), at the trees' feet, never in the walkable
    def bush_region(r_):
        u = r_.uniform(-33, 33); v = r_.uniform(-14, 16)
        sp = float(sd_play(u, v))
        if not 0.35 < sp < 2.2 or float(sd_shelf(u, v)) > -0.8 or float(sd_pond(u, v)) < 0.8:
            return None
        return (u, v, 0.9)
    for u, v, r in poisson(rng, 3000, bush_region, 1.7, keep)[:46]:
        add(kind="bush", u=u, v=v, r=0.0, h=rng.uniform(1.0, 1.6), cls=rng.choice(("green", "green", "red")),
            seed=rng.randrange(1 << 20), zone="frame", rad=rng.uniform(0.8, 1.2))
    # --- the plateau's lip in the window over the knoll: a row of stones and low bushes says "the edge is here"
    for k in range(6):
        u = -9.0 + 18.0 * (k + rng2.uniform(0.2, 0.8)) / 6
        v = float(BACK_EDGE + 2.4 * smooth(6.0, 26.0, abs(u))) - rng2.uniform(0.6, 1.4)
        if k % 2 == 1:
            add(kind="bush", u=u, v=v, r=0.0, h=rng2.uniform(0.9, 1.3), cls=rng2.choice(("green", "red")),
                seed=rng2.randrange(1 << 20), zone="frame", rad=rng2.uniform(0.7, 1.0))
        else:
            rng2.random(); rng2.random(); rng2.randrange(1 << 20)
    # --- dressing in the grass: flower sprinkles and mushrooms (playfield, no collision, never on the dirt)
    def deco_region(r_):
        u = r_.uniform(-27, 27); v = r_.uniform(-10, 10)
        sp = float(sd_play(u, v))
        if sp > -0.8 or float(sd_dirt(u, v)) < 1.0 or float(sd_pond(u, v)) < 0.6:
            return None
        return (u, v, 0.4)
    for u, v, r in poisson(rng, 2000, deco_region, 2.4, keep)[:44]:
        k = rng.random()
        add(kind="mushrooms" if k < 0.22 else "flowers", u=u, v=v, r=0.0, seed=rng.randrange(1 << 20),
            cls=rng.choice(("pink", "orange", "white", "lilac")), zone="playfield")
    # --- the edges' dressing (its own random stream, so nothing above moves): big-leaf plants in clusters along the
    # hollow's rim and round the props that stand off the lanes, mushroom patches near the rim; never on the dirt,
    # the lanes or the pond's bank
    rng4 = random.Random(seed + 7)

    def off_lane(u, v, m=1.6):
        return float(sd_dirt(u, v)) > 1.0 and float(lane_dist(u, v)) > m and float(sd_pond(u, v)) > 0.8

    def rim_region(r_):
        u = r_.uniform(-29, 29); v = r_.uniform(-11, 11)
        sp = float(sd_play(u, v))
        if not -1.6 < sp < 0.4 or not off_lane(u, v):
            return None
        return (u, v, 0.7)
    for u, v, r in poisson(rng4, 3000, rim_region, 4.0, keep)[:9]:
        for j in range(rng4.randint(3, 4)):                   # a clump of big plants
            a = rng4.uniform(0, math.tau); d = 0.0 if j == 0 else rng4.uniform(0.6, 1.0)
            uu, vv = u + math.cos(a) * d, v + math.sin(a) * d
            if off_lane(uu, vv, 1.4):
                add(kind="fern", u=uu, v=vv, r=0.0, h=rng4.uniform(0.75, 1.05), seed=rng4.randrange(1 << 20),
                    zone="frame")
    for t in [t for t in things if t["kind"] in ("stump", "log")]:
        for j in range(2):
            a = rng4.uniform(0, math.tau); d = (t.get("r") or 0.5) + rng4.uniform(0.5, 0.9)
            uu, vv = t["u"] + math.cos(a) * d, t["v"] + math.sin(a) * d
            if off_lane(uu, vv, 2.0) and float(sd_play(uu, vv)) < 0.6 and rng4.random() < 0.15:
                add(kind="fern", u=uu, v=vv, r=0.0, h=rng4.uniform(0.45, 0.8), seed=rng4.randrange(1 << 20),
                    zone="frame")

    def mush_region(r_):
        u = r_.uniform(-28, 28); v = r_.uniform(-11, 11)
        sp = float(sd_play(u, v))
        if not -2.4 < sp < -0.3 or not off_lane(u, v):
            return None
        return (u, v, 0.4)
    for u, v, r in poisson(rng4, 2000, mush_region, 2.0, keep)[:18]:
        add(kind="mushrooms", u=u, v=v, r=0.0, seed=rng4.randrange(1 << 20), cls="red", zone="playfield")

    # --- the spawn camps, at each glade's back rim (clear of every spawn point by 1.5 m; the middle stays bare for
    # spawning): a stack of crates, a banner pole in plain linen, a ring-stone campfire with a bedroll beside it, clay
    # pot lights, mushrooms and flower clumps round the edge (mirrored)
    rng5 = random.Random(seed + 9)
    pair(kind="crates", u=-23.6, v=4.14, r=0.45, h=0.6, rot=rng5.uniform(10, 30), seed=rng5.randrange(1 << 20),
         zone="frame")
    pair(kind="banner", u=-24.72, v=3.2, r=0.1, h=2.7, seed=rng5.randrange(1 << 20), zone="frame")
    pair(kind="fire", u=-24.52, v=-3.1, r=0.5, h=0.3, seed=rng5.randrange(1 << 20), zone="focus")
    pair(kind="bedroll", u=-23.0, v=-4.0, r=0.0, h=0.2, rot=rng5.uniform(-30, -10), seed=rng5.randrange(1 << 20),
         zone="playfield")
    for (u, v) in ((-22.32, 5.13), (-25.92, -1.11)):
        pair(kind="potlight", u=u, v=v, r=0.0, h=0.35, seed=rng5.randrange(1 << 20), zone="playfield")
    for (u, v, c) in ((-25.92, 2.11, "lilac"), (-22.6, 5.6, "orange"), (-25.6, -2.6, "pink"), (-21.4, -4.3, "white")):
        if off_lane(u, v, 1.2):
            pair(kind="flowers", u=u, v=v, r=0.0, seed=rng5.randrange(1 << 20), cls=c, zone="playfield")
    for (u, v) in ((-26.1, 0.3), (-24.9, 4.4), (-22.0, -4.5)):
        pair(kind="mushrooms", u=u, v=v, r=0.0, seed=rng5.randrange(1 << 20), cls="red", zone="playfield")
    # pot lights and flower clumps by the props at the hollow's rim, off the lanes
    for t in [t for t in things if t["kind"] in ("log", "stump") and t["u"] < 0]:
        a = rng5.uniform(0, math.tau); d = (t.get("r") or 0.6) + 0.7
        uu, vv = t["u"] + math.cos(a) * d, t["v"] + math.sin(a) * d
        if off_lane(uu, vv, 1.6):
            pair(kind="potlight" if t["kind"] == "log" else "flowers", u=uu, v=vv, r=0.0, h=0.35,
                 seed=rng5.randrange(1 << 20), cls=rng5.choice(("lilac", "orange", "pink")), zone="playfield")
    return dict(things=things)


# ---------------------------------------------------------------- the back of the map: forced-scale scenery
# Bands are in screen metres P (sy = Y0 - P * PPM) from P_BACK, the screen height of the plateau's back edge, to P_TOP,
# the picture's top: each band is a share of that room, so the back keeps its order at any camera angle. Layers further
# back are built smaller, simpler and lower in detail (zones.py budgets them).
P_BACK = BACK_EDGE * SE
P_TOP = Y0 / PPM
A_ = P_TOP - P_BACK


def band(f):
    return P_BACK + f * A_


SCENERY = dict(
    # the valley's canopy on three bands past the drop (backdrop), red and green crowns, smaller every step back
    forests=[
        dict(v=30.0, foot=band(-0.30), crest=(band(-0.04), band(0.04)), h=(2.0, 2.6), gap=0.9, depth=4.0, seed=31, red=0.5),
        dict(v=50.0, foot=band(0.20), crest=(band(0.28), band(0.34)), h=(1.3, 1.7), gap=0.7, depth=3.0, seed=32, red=0.4),
        dict(v=68.0, foot=band(0.36), crest=(band(0.43), band(0.48)), h=(0.95, 1.25), gap=0.55, depth=2.4, seed=33, red=0.3),
    ],
    # the valley floor between the first and second canopy, with the river winding across it
    floor=dict(v=(36.0, 49.0), p=(band(0.02), band(0.22))),
    river=dict(v=41.0, width=1.7),
    # far hills (vista): rolling ranges in haze (v, base, crest range, seed)
    hills=[dict(v=110.0, base=band(0.38), crest=(band(0.50), band(0.62)), seed=71),
           dict(v=140.0, base=band(0.46), crest=(band(0.62), band(0.80)), seed=72)],
    # fair-weather cumulus over the hills: (u, v, base, width, height)
    clouds=[(-24.0, 170.0, band(0.66), 11.0, 3.4), (2.0, 176.0, band(0.70), 9.0, 2.8),
            (25.0, 172.0, band(0.67), 12.0, 3.2)],
)


def _ridge(spec, seed):
    c = 0.8
    us = np.arange(-40.0, 40.0 + c, c)
    ss = np.arange(0.0, spec["depth"] + c, c)
    Uu, S = np.meshgrid(us, ss)
    lo, hi = spec["crest"]
    r = 0.5 + 0.5 * vnoise(Uu, 0 * Uu, 9.0, seed) * 0.8 + 0.1 * vnoise(Uu, 0 * Uu, 3.0, seed + 3)
    crest_p = lo + (hi - lo) * np.clip(r, 0, 1)
    vf = spec["v"]
    zb = z_for_p(spec["foot"], vf + S)
    hmax = (crest_p - spec["foot"]) / CE
    prof = np.sin(np.clip(S / spec["depth"], 0, 1) * math.pi / 2) ** 0.8
    Z = zb + hmax * prof
    return Uu, vf + S, Z


def _hills(spec, seed):
    c = 1.2
    us = np.arange(-48.0, 48.0 + c, c)
    ss = np.arange(0.0, 10.0 + c, c)
    Uu, S = np.meshgrid(us, ss)
    lo, hi = spec["crest"]
    r = (0.5 + 0.45 * vnoise(Uu, 0 * Uu, 16.0, seed) + 0.15 * vnoise(Uu, 0 * Uu, 6.0, seed + 1)
         + 0.06 * vnoise(Uu, 0 * Uu, 1.6, seed + 2) + 0.05 * np.abs(vnoise(Uu, 0 * Uu, 0.7, seed + 3)))   # tree-top bumps
    crest_p = lo + (hi - lo) * np.clip(r, 0, 1)
    vf = spec["v"]
    zb = z_for_p(spec["base"], vf + S)
    hmax = (crest_p - spec["base"]) / CE
    prof = np.sin(np.clip(S / 10.0, 0, 1) * math.pi / 2) ** 0.7
    return Uu, vf + S, zb + hmax * prof


def scenery() -> dict:
    """the backdrop (the valley's canopy, its floor and the river) and the vista (far hills, cumulus)"""
    out = dict(strips=[], trees=[], clouds=[], river=None)
    rng = random.Random(77)
    for k, spec in enumerate(SCENERY["forests"]):
        U, V, Z = _ridge(spec, spec["seed"])
        out["strips"].append(dict(name=f"canopy{k}", zone="backdrop", U=U, V=V, Z=Z, mat="far_ground"))
        g = spec["gap"]
        for i in range(1, U.shape[0]):
            for uu in np.arange(-38.0, 38.0, g):
                u = uu + rng.uniform(-0.35, 0.35) * g
                if fbm(u, V[i, 0] * 0.3, 7.0, 41 + k) < -0.45 - 0.1 * k:
                    continue
                j = int(np.clip(round((u + 40.0) / 0.8), 0, U.shape[1] - 1))
                red = rng.random() < spec["red"] * (1 + 0.6 * fbm(u, 0.0, 10.0, 90 + k))
                out["trees"].append(dict(u=float(u), v=float(V[i, j] + rng.uniform(-.2, .2)), z=float(Z[i, j]) - 0.1,
                                         h=rng.uniform(*spec["h"]), zone="backdrop", band=k,
                                         cls="coral" if red else "green"))
    for k, spec in enumerate(SCENERY["hills"]):
        U, V, Z = _hills(spec, spec["seed"])
        out["strips"].append(dict(name=f"hills{k}", zone="vista", U=U, V=V, Z=Z, mat="hills"))
    # the valley floor: a strip sunk so it rises from its near to its far band; the river winds across it
    fl = SCENERY["floor"]
    us = np.arange(-44.0, 44.0 + 0.8, 0.8)
    vs = np.arange(fl["v"][0], fl["v"][1] + 0.5, 0.5)
    Uu, Vv = np.meshgrid(us, vs)
    pf = lambda vv: fl["p"][0] + (fl["p"][1] - fl["p"][0]) * np.clip((vv - fl["v"][0]) / (fl["v"][1] - fl["v"][0]), 0, 1)
    Zz = z_for_p(pf(Vv), Vv) + 0.08 * fbm(Uu, Vv, 4.0, 81)
    out["strips"].append(dict(name="valley", zone="backdrop", U=Uu, V=Vv, Z=Zz, mat="far_ground"))
    rv = SCENERY["river"]
    us = np.arange(-44.0, 44.5, 0.5)
    vc = rv["v"] + 2.0 * np.sin(us / 9.0 + 0.6) + 0.9 * np.sin(us / 3.7)
    out["river"] = dict(u=us.tolist(), v=vc.tolist(), z=[float(z_for_p(pf(x), x)) + 0.12 for x in vc], w=rv["width"],
                        zone="backdrop")
    for i, (cu, cv, pb, wd, ht) in enumerate(SCENERY["clouds"]):
        out["clouds"].append(dict(u=cu, v=cv, z=z_for_p(pb, cv), w=wd, h=ht, zone="vista", floor=False, pink=False,
                                  seed=300 + i))
    return out


STRIP_W = 6144


def cloud_layers() -> dict:
    """the cumulus as a drifting strip (layers.py), STRIP_W px wide, wrapping; masses near the seam repeated"""
    period = STRIP_W / PPM
    out = dict(period=period, far=[], sea=[], corner=[])
    cr = random.Random(43)
    n = 8
    for k in range(n):
        cu = -period / 2 + period * (k + cr.uniform(0.2, 0.8)) / n
        cv = cr.uniform(166, 178)
        pb = band(cr.uniform(0.64, 0.71))
        wd, ht = cr.uniform(8, 12), cr.uniform(2.6, 3.4)
        for kk in (-1, 0, 1):
            u = cu + kk * period
            if abs(u) - wd * 0.6 < period / 2:
                out["far"].append(dict(u=float(u), v=cv, z=z_for_p(pb, cv), w=wd, h=ht, floor=False, pink=False,
                                       seed=500 + k))
    return out


# ---------------------------------------------------------------- zones of the ground
def zone_at(u, v, z, frame_trees=()):
    """the depth zone of a ground point: the hollow is playfield, the forest floor and the plateau's lip frame; the
    drop sinks into the backdrop"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64); z = np.asarray(z, np.float64)
    d = sd_play(u, v)
    out = np.full(u.shape, "frame", object)
    out[(d < -0.2) & (z > -1.2)] = "playfield"
    out[z < -9.0] = "backdrop"
    return out


# ---------------------------------------------------------------- the walk grid (the `plan` command)
CELL = 0.5
GU0, GU1, GV0, GV1 = -32.0, 32.0, -13.0, 14.0

SOLID_R = {"boulder": None, "oak": 0.55, "pine": 0.7, "bush": 0.9, "stump": None, "waystone": 0.6, "lantern": 0.2,
           "crates": 0.5, "banner": 0.15, "fire": 0.55}


def walk_grid(lay: dict) -> dict:
    us = np.arange(GU0 + CELL / 2, GU1, CELL)
    vs = np.arange(GV0 + CELL / 2, GV1, CELL)
    U, V = np.meshgrid(us, vs)
    Z = terrain(U, V)
    kind = np.ones(U.shape, np.uint8)
    kind[sd_dirt(U, V) < 0] = 2
    kind[sd_play(U, V) > -0.5] = 0
    for t in lay["things"]:
        r = SOLID_R.get(t["kind"], 0) or t.get("r", 0)
        if t["kind"] in ("log", "ruinwall") and t.get("plate", True):
            r = 1.0
        if r and t["kind"] not in ("flowers", "mushrooms", "reeds", "pebbles"):
            kind[np.hypot(U - t["u"], V - t["v"]) < r] = 0
    return dict(us=us, vs=vs, z=Z.astype(np.float32), kind=kind)


DIMENSIONS = {
    "person (scale reference)": f"{HUMAN} m",
    "metre grid": f"1 m = {PPM:.0f} px across, {PPM * SE:.1f} px into the picture, {PPM * CE:.1f} px up",
    "spawn to spawn": f"{SPAWNS['east'][0] - SPAWNS['west'][0]:.0f} m",
    "the fighting ground": f"{2 * GROUND[2]:.0f} x {2 * GROUND[3]:.1f} m of dirt and cobbles",
    "the hollow": f"{2 * FIELD[2]:.0f} x {2 * FIELD[3]:.0f} m",
    "the knoll": f"{2 * KNOLL[2]:.0f} m across, {KNOLL[3]:.1f} m high",
    "the pond": f"{2 * POND[2]:.0f} x {2 * POND[3]:.0f} m, two small pools {2 * POOLS[0][2]:.1f} x {2 * POOLS[0][3]:.1f} m",
    "the fallen log": "3.6 m, 0.8 m high (half cover)",
    "red-crowned trees (frame)": "hero 9.5-10.5 m, standard 6.6-7.8 m, small 4.6-5.6 m, saplings 2.6-3.2 m",
    "pines (frame)": "young 5-7 m, tall 8.5-13.5 m",
    "other cover": "two 2.0-2.4 m logs each side of the fight, a 3.2 m trunk on each knoll shoulder, stumps, bushes",
    "pebbles": "painted, 2-12 cm (1-6 px); no rock bigger than 0.3 m on the map",
}


def export(out: Path, seed: int = SEED) -> dict:
    """the place for Blender: scene3d.json + terrain.npz + scenery.npz"""
    from ... import zones as Z_
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lay = layout(seed)
    st = 0.3
    us = np.arange(-44.0, 44.0 + st, st)
    vs = np.arange(-26.0, 30.0 + st, st)
    U, V = np.meshgrid(us, vs)
    Z = terrain(U, V)
    np.savez_compressed(out / "terrain.npz", u=U.astype(np.float32), v=V.astype(np.float32), z=Z.astype(np.float32),
                        lane=lane_dist(U, V).astype(np.float32), plat=sd_plateau(U, V).astype(np.float32),
                        play=sd_play(U, V).astype(np.float32), raised=np.zeros_like(U, np.float32),
                        dirt=sd_dirt(U, V).astype(np.float32), pond=sd_pond(U, V).astype(np.float32))
    sc = scenery()
    arrs = {}
    for k, s in enumerate(sc["strips"]):
        for a in ("U", "V", "Z"):
            arrs[f"{k}_{a}"] = s[a].astype(np.float32)
    np.savez_compressed(out / "scenery.npz", **arrs)
    spec = dict(PPM=PPM, EL=EL, W=W, H=H, X0=X0, Y0=Y0, SUN=sun_vec(), things=lay["things"], CLIFF=CLIFF,
                spawns=SPAWNS, pond=POND, water_z=WATER_Z, pools=[(s_ * pu, pv, hu, hv) for pu, pv, hu, hv in POOLS
                                                                 for s_ in (-1, 1)],
                water_polys=[water_outline(*POND)] + [water_outline(s_ * pu, pv, hu, hv) for pu, pv, hu, hv in POOLS
                                                       for s_ in (-1, 1)],
                zones={k: dict(code=v["code"], detail=v["detail"]) for k, v in Z_.ZONES.items()},
                strips=[dict(name=s["name"], zone=s["zone"], mat=s["mat"]) for s in sc["strips"]],
                trees=sc["trees"], clouds=sc["clouds"], river=sc["river"],
                cloud_layers=cloud_layers(), strip_w=STRIP_W)
    (out / "scene3d.json").write_text(json.dumps(spec))
    return lay
