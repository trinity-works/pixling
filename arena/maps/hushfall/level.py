"""Hushfall Crossing's level hooks for the shared level engine (arena/level.py): the props' collision shapes (matching
blender.py's geometry), the bridge deck (a second layer over the corridor), the ramps (the only joins between ground
and terrace), the camps' spawns, the objectives (the Stones, hearts, towers), the camp fires, the chokepoints, the
surfaces (snow, trodden lanes, drifts along the lip) and the alcoves only small units reach.
"""
from __future__ import annotations

import math
import random

import numpy as np

from . import place as P

SURF = {"snow": 1, "lane": 2, "drift": 3, "deck": 4}
SPEED = {"snow": 0.85, "lane": 1.0, "drift": 0.7, "deck": 1.0}
SURF_NOTE = "speed multipliers: deep snow off the trodden lanes, drifts along the ledge's lip"
GRID_LEGEND = {"0": "blocked", "1": "snow", "2": "trodden lane"}
# places only smaller units reach (declared: the check fails on any other island): radius -> (name, u, v)
ALCOVES = {0.8: [("west camp, between the tents", -25.7, 0.6), ("east camp, between the tents", 25.6, 0.6)]}
COVER_KINDS = ("spruce", "rock", "tent", "heart plinth", "menhir", "column", "toppled block", "parapet", "crates",
               "woodpile", "palisade", "tower leg")
LEGACY_PROPS = ("heart", "tower", "fire", "banner", "lamppost")
# collider kinds that are drawn props (check.py: their projected samples must land on the occluder cut-outs)
ART_KINDS = {"spruce", "rock", "tent", "tower leg", "heart plinth", "heart lantern", "banner", "lamppost", "crates",
             "woodpile", "altar", "menhir", "column", "column drum", "toppled block", "parapet", "palisade", "kerb",
             "bridge rail"}
SIDES = ("west", "east")
D = P.DECK
DECK = True
DECK_HALF = abs(D["u1"] - 0.12 - 0.13)        # the rails' inner faces (posts at u1 - 0.12, half 0.12, rail 0.13)
ZD_LANDING = P.ZD - 0.6
R2 = math.sqrt(2.0)


def deck_z(v):
    t = np.clip((np.asarray(v, np.float64) - D["v0"]) / (D["v1"] - D["v0"]), 0, 1)
    return D["z0"] + (D["z1"] - D["z0"]) * t


def deck_mask(UU, VV):
    return (np.abs(UU) < DECK_HALF) & (VV >= D["v0"]) & (VV <= D["v1"])


def bl2uv(dx, dy):
    """a Blender (world grid x, y) vector -> (u, v)"""
    return (dx - dy) / R2, (dx + dy) / R2


def _g(u, v):
    return float(P.terrain(np.array(u), np.array(v)))


def region_extra(U, V, Z, f):
    """the bridge's landings: the terrace and the overlook under the deck's two ends stay walkable, so units step on"""
    for va, vb, zt in ((D["v0"] - 1.0, D["v0"] + 0.3, P.ZD), (D["v1"] - 0.3, D["v1"] + 1.0, P.ZO)):
        g = np.minimum.reduce([D["walk"] - np.abs(U), V - va, vb - V, Z - (zt - 0.6)])
        f = np.maximum(f, g)
    return f


def wall_skip(mu, mv, zin):
    """a landing's edge under the deck: the deck carries on"""
    return abs(mu) < DECK_HALF + 0.15 and D["v0"] - 0.05 < mv < D["v1"] + 0.05 and zin > ZD_LANDING


def props(lay, box, circ, seg, HIGH_Z):
    """collision shapes of everything placed, in metres, matching blender.py's geometry"""
    Q = math.pi / 4                                 # the world grid's axes are turned 45 degrees in (u, v)
    things = lay["things"]
    for k, t in enumerate(things):
        kind = t["kind"]
        u, v = t.get("u", 0.0), t.get("v", 0.0)
        g = _g(u, v) if kind not in ("ruin", "bridge", "stub") else 0.0
        if kind == "spruce":
            h = t["h"]
            circ("spruce", u, v, 0.45 + 0.06 * h, g, g - 0.3, g + h)
        elif kind == "rock":
            r = t["r"]
            rr = random.Random(t["seed"])
            rr.uniform(0, 3)
            circ("rock", u, v, 1.05 * r, g, g - 0.2, g + 0.9 * r)
            for _ in range(rr.randint(1, 2)):
                a = rr.uniform(0, 6.28)
                du, dv = bl2uv(math.cos(a) * r * 0.9, math.sin(a) * r * 0.9)
                circ("rock", u + du, v + dv, 0.55 * r, g, g - 0.2, g + 0.4 * r)
        elif kind == "tent":
            box("tent", u, v, 3.4 / 2 + 0.25, 2.7 / 2, math.radians(t["rot"]) + Q, g, g - 0.2, g + 2.3)
        elif kind == "tower":
            for i in (-1, 1):
                for j in (-1, 1):
                    du, dv = bl2uv(i * 1.1, j * 1.1)
                    circ("tower leg", u + du, v + dv, 0.15, g, g - 0.3, g + 4.6)
            box("tower cage", u, v, 1.23, 1.23, Q, g, g, g + 4.0, solid=False, opaque=False)
            box("tower platform", u, v, 1.3, 1.3, Q, g, g + 4.6, g + 5.6)
            box("tower roof", u, v, 1.55, 1.55, Q, g, g + 6.5, g + 8.9)
        elif kind == "heart":
            box("heart plinth", u, v, 0.75, 0.75, Q, g, g - 0.3, g + 1.0)
            box("heart lantern", u, v, 0.58, 0.58, Q, g, g + 1.0, g + 3.0)
        elif kind == "fire":
            circ("fire", u, v, 0.82, g, g - 0.1, g + 0.6, solid=False, opaque=False)
        elif kind == "banner":
            circ("banner", u, v, 0.1, g, g - 0.3, g + 5.7)
        elif kind == "lamppost":
            circ("lamppost", u, v, 0.1, g, g - 0.3, g + 2.6)
        elif kind == "crates":
            for dx, dy, dz, s in ((0, 0, 0, .9), (.95, .1, 0, .8), (.35, .1, .9, .7)):
                du, dv = bl2uv(dx, dy)
                top = g + dz + s + (0.7 if dz == 0 and dx == 0 else 0.0)
                box("crates", u + du, v + dv, s / 2, s / 2, Q, g, g + dz - 0.05, top)
        elif kind == "woodpile":
            box("woodpile", u, v, 0.75, 0.67, math.radians(t["rot"]) + Q, g, g, g + 1.03)
        elif kind == "altar":
            box("altar", u, v, 0.8, 0.8, Q, g, g - 0.2, g + 0.55)
        elif kind == "menhir":
            h = t["h"]
            lean = random.Random(k).uniform(-.12, .12)
            lu, lv = bl2uv(lean * h, 0.0)
            ang = math.radians(t["rot"]) + Q
            box("menhir", u + 0.25 * lu, v + 0.25 * lv, 0.475, 0.31, ang, g, g - 0.3, g + h / 2)
            box("menhir", u + 0.75 * lu, v + 0.75 * lv, 0.39, 0.265, ang, g, g + h / 2, g + h)
        elif kind == "column":
            sr = random.Random(t["seed"])
            n = max(1, int(round(t["h"] / 0.7)))
            z = -0.2
            for i in range(n):
                z += t["h"] / n * sr.uniform(0.92, 1.05)
                sr.uniform(-.05, .05); sr.uniform(-.05, .05)
            circ("column", u, v, 0.42, g, g - 0.2, g + z + 0.14)
            a = sr.uniform(0, 6.28)
            du, dv = bl2uv(math.cos(a), math.sin(a))
            box("column drum", u + du, v + dv, 0.35, 0.4, a + 1.4 + Q, g, g - 0.15, g + 0.75)
        elif kind == "block":
            sr = random.Random(t["seed"])
            th = math.radians(sr.uniform(12, 28))
            L_, Wd, Hh = sr.uniform(1.1, 1.4), sr.uniform(0.7, 0.85), sr.uniform(0.6, 0.75)
            ys = [-Wd / 2 * math.cos(th) - 0.7 * Hh * math.sin(th), Wd / 2 * math.cos(th) + 0.3 * Hh * math.sin(th)]
            zt = Wd / 2 * math.sin(th) + 0.7 * Hh * math.cos(th)
            ang = math.radians(t["rot"]) + Q
            off = (ys[0] + ys[1]) / 2
            cu, cv = u - math.sin(ang) * off, v + math.cos(ang) * off
            box("toppled block", cu, cv, L_ / 2, (ys[1] - ys[0]) / 2, ang, g, g - 0.3, g + zt + 0.11)
        elif kind == "stub":
            sr = random.Random(t["seed"])
            g = t["z"]
            nb = max(1, int(round(t["len"] / 0.8)))
            du, dv = -t["nv"], t["nu"]
            ang = math.atan2(dv, du)
            for i in range(nb):
                f = (i + 0.5) / nb - 0.5
                hh = t["h"] * (1.0 - 0.45 * i / max(1, nb - 1)) * sr.uniform(0.85, 1.05)
                sr.uniform(-0.1, 0.1)
                box("parapet", u + du * f * t["len"], v + dv * f * t["len"], t["len"] / nb * 0.48, 0.275, ang, g,
                    g - 0.2, g + hh)
        elif kind == "ruin":
            for b in t["kerb"]:
                tw = math.radians(b["tw"])
                an = math.atan2(b["nv"], b["nu"]) + tw
                nu_, nv_ = math.cos(an), math.sin(an)
                du, dv = -nv_, nu_
                off = b["dep"] / 2 - 0.32 + b.get("out", 0.0)
                cu, cv = b["u"] + nu_ * off, b["v"] + nv_ * off
                L2 = b["len"] / 2
                g = b["z0"] + 0.3
                seg("kerb", (cu - du * L2, cv - dv * L2), (cu + du * L2, cv + dv * L2), b["dep"] / 2, g, b["z0"], b["z1"],
                    level=int(b["z1"] >= HIGH_Z + 0.3))
        elif kind == "bridge":
            zlo, zhi = min(D["z0"], D["z1"]), max(D["z0"], D["z1"])
            for uu in (D["u0"] + 0.12, D["u1"] - 0.12):
                seg("bridge rail", (uu, D["v0"]), (uu, D["v1"]), 0.13, zlo, zlo - 0.2, zhi + 1.33, level=2,
                    opaque=False, solid=False)
                for vv, s_ in ((D["v0"] - 0.2, 1), (D["v1"] + 0.2, -1)):
                    zf = float(deck_z(vv))
                    seg("corbel", (uu, vv), (uu, vv + s_ * 1.4), 0.09, zf - 1.5, zf - 1.6, zf - 0.36, level=0,
                        opaque=False, solid=False)
            # the deck: the floor of level 2 and the ceiling of the corridor (2.9 m over its floor)
            box("deck", 0.0, (D["v0"] + D["v1"]) / 2, (D["u1"] - D["u0"]) / 2 + 0.04, (D["v1"] - D["v0"]) / 2 + 0.3,
                0.0, zlo - 3.0, zlo - 0.5, zhi + 0.02, level=0)
    # the palisade: each run of stakes along a side of the camp's square as one box
    for side, (cu, cv) in P.CAMPS.items():
        cx, cy = P.to_xy(cu, cv)
        h = P.CAMP_HALF
        lines = (("x", cx - h), ("y", cy + h)) if side == "west" else (("x", cx + h), ("y", cy - h))
        stakes = [t for t in things if t["kind"] == "stake" and t["side"] == side]
        for axis, val in lines:
            on = []
            for t in stakes:
                x, y = P.to_xy(t["u"], t["v"])
                if abs((x if axis == "x" else y) - val) < 1e-6:
                    on.append(((y if axis == "x" else x), t))
            on.sort(key=lambda p: p[0])
            runs, cur = [], []
            for s, t in on:
                if cur and s - cur[-1][0] > 0.62 * 1.5:
                    runs.append(cur); cur = []
                cur.append((s, t))
            if cur:
                runs.append(cur)
            for run in runs:
                a, b = run[0][1], run[-1][1]
                gz = min(_g(t["u"], t["v"]) for _, t in run)
                top = max(_g(t["u"], t["v"]) + t["h"] + 0.45 for _, t in run)
                if len(run) == 1:
                    circ("palisade", a["u"], a["v"], 0.2, gz, gz - 0.4, top)
                    continue
                mu, mv = (a["u"] + b["u"]) / 2, (a["v"] + b["v"]) / 2
                ang = math.atan2(b["v"] - a["v"], b["u"] - a["u"])
                box("palisade", mu, mv, math.hypot(b["u"] - a["u"], b["v"] - a["v"]) / 2 + 0.2, 0.21, ang, gz,
                    gz - 0.4, top)


def ramp_rects():
    """each ramp: its rectangle, the entry edge at its foot (ground) and the exit edge at its top (terrace)"""
    out = []
    hw = P.RAMP_HW - 0.2
    for name, s in (("west ramp", -1), ("east ramp", 1)):
        top = s * (P.DAIS[2] - 0.3)
        foot = s * (P.DAIS[2] - 0.3 + P.RAMP_LEN)
        mid = (top + foot) / 2
        out.append(dict(name=name, kind="ramp", levels=[0, 1], rect=[min(top, foot) - 0.6, P.RAMP_V - P.RAMP_HW,
                                                                     max(top, foot) + 0.6, P.RAMP_V + P.RAMP_HW],
                        entry=[[foot, P.RAMP_V - hw], [foot, P.RAMP_V + hw]],
                        exit=[[top, P.RAMP_V - hw], [top, P.RAMP_V + hw]],
                        switch=[[mid, P.RAMP_V - hw], [mid, P.RAMP_V + hw]],
                        slope_deg=round(math.degrees(math.atan(P.ZD / P.RAMP_LEN)), 1)))
    return out



def surfaces(UU, VV, wl, inside, Zc, shape_dist, SURF_, RAMP_BIT):
    """per nav cell: snow, the trodden lanes, drifts along the lip; | RAMP_BIT on the ramps"""
    lane = P.lane_dist(UU, VV) + 0.35 * P.fbm(UU, VV, 1.1, 42)
    surf = np.full(UU.shape, SURF["snow"], np.uint8)
    surf[lane < 1.15] = SURF["lane"]
    lips = [s for s in wl if s["kind"] == "lip" and s["level"] == 0]
    dl = np.full(UU.shape, 9.0)
    for s in lips:
        dl = np.minimum(dl, shape_dist(s, UU, VV))
    surf[(dl < 1.4) & (P.sd_play(UU, VV) > -3.0)] = SURF["drift"]
    ramps = ramp_rects()
    for r in ramps:
        x0, y0, x1, y1 = r["rect"]
        m = (UU >= x0) & (UU <= x1) & (VV >= y0) & (VV <= y1) & (Zc > 0.05) & inside
        surf[m] |= RAMP_BIT
    return surf, ramps


def spawn_origin(side):
    cu, cv = P.CAMPS[side]
    s = 1 if side == "east" else -1
    u = cu - s * 3.0
    return (u, cv, _g(u, cv))


def spawn_centre():
    """the west spawn ring's centre (the east one is its mirror)"""
    return P.CAMPS["west"]


def spawn_area(side):
    return dict(u=P.CAMPS[side][0], v=P.CAMPS[side][1], r=4.4), 7.0


OCCLUDERS_NOTE = ("occ.json + occ.png: every tree, prop and the bridge cut out of map.png with its depth d (and "
                  "deck=1 for the bridge). Draw a cut-out over a unit whose depth is larger (further) than d and "
                  "whose box it overlaps; the bridge goes over units on levels 0-1 and under units on the deck.")


def levels(A, HIGH_Z):
    levels = [dict(id=0, name="ground", layer=0, note="height-field cells lower than high_ground_z"),
              dict(id=1, name="terrace", layer=0, note="the ruin terrace, the ramps' upper halves and the overlook: "
                                                           "height-field cells at or over high_ground_z; reached from "
                                                           "the ground only by the two ramps"),
              dict(id=2, name="deck", layer=1, u0=D["u0"], u1=D["u1"], v0=D["v0"], v1=D["v1"], z0=D["z0"], z1=D["z1"],
                   walk_half_width=round(DECK_HALF, 3), note="the bridge: walked between its rails, entered only at "
                                                             "its two ends (nav.links); the corridor runs beneath")]
    under = A["inside"] & (np.abs(A["U"][1::2, 1::2]) < 1.8) & (A["V"][1::2, 1::2] > D["v0"]) & \
        (A["V"][1::2, 1::2] < D["v1"]) & (A["Zc"] < HIGH_Z)
    zc = A["Zc"][under]
    ceil_z = min(D["z0"], D["z1"]) - 0.5
    levels[2]["headroom"] = [float(ceil_z - zc.max()), float(ceil_z - zc.min())]
    levels[2]["note"] += "; headroom = the corridor's clear height under it (min, max m)"
    return levels


def objectives(lv, lay):
    objectives = [dict(id="stones", kind="stones", side=None, u=P.STONES[0], v=P.STONES[1],
                       z=lv.hf_z(P.STONES[0], P.STONES[1]), level=1, capture_r=4.6)]
    for t in lay["things"]:
        if t["kind"] in ("heart", "tower"):
            objectives.append(dict(id=f"{t['kind']} {t['side']}", kind=t["kind"], side=t["side"], u=t["u"], v=t["v"],
                                   z=lv.hf_z(t["u"], t["v"]), level=0, capture_r=3.0))
    return objectives


def zone_extras(lv, lay):
    return dict(heal=[dict(kind="campfire warmth", side=t["side"], u=t["u"], v=t["v"], r=3.2,
                           note="optional: regenerate out of combat") for t in lay["things"] if t["kind"] == "fire"])


def chokepoints():
    return [("west ramp", (-(P.DAIS[2] + P.RAMP_LEN / 2), P.RAMP_V), (0, 1), 0),
            ("east ramp", (P.DAIS[2] + P.RAMP_LEN / 2, P.RAMP_V), (0, 1), 0),
            ("bridge", (0.0, (D["v0"] + D["v1"]) / 2), (1, 0), 1),
            ("corridor west mouth", (-P.CORR[2], P.CORR[1]), (0, 1), 0),
            ("corridor east mouth", (P.CORR[2], P.CORR[1]), (0, 1), 0),
            ("corridor under the bridge", (0.0, 7.0), (0, 1), 0),
            ("apron west", (-10.0, -9.0), (0, 1), 0), ("apron east", (10.0, -9.0), (0, 1), 0)]
