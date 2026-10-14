"""Hushfall Crossing: a ledge in the winter forest above a sea of dusk cloud, laid out in metres like GW1's Underworld.

Axes: u runs left -> right across the screen (the line between the two camps), v runs into the picture, z is up. The
world's square grid (x, y) is u, v turned 45 degrees: x = (u + v) / sqrt 2, y = (v - u) / sqrt 2, and every built thing
(palisades, tents, towers, the bridge) sits square to x, y, so it reads isometric.

The camera is orthographic, looking along +v and down by EL; a point (u, v, z) lands on the map picture at
    sx = X0 + u * PPM,   sy = Y0 - (v * sin EL + z * cos EL) * PPM
and its depth (larger = further) is v * cos EL - z * sin EL. Blender, the painter, the runtime and the exported level
all use this. EL is 40 degrees (chosen from a 30 / 35 / 40 / 45 test; ARENA_EL overrides it for such tests).

The layout (after The Underworld, Heroes' Ascent): two camps (west and east) at ground level; a raised ruin terrace in
the middle holding the Stones, with a ramp up from each side; a timber bridge from the terrace to an overlook at the
far edge (a dead end of high ground over the centre); a corridor at ground level under the bridge joining the two
camp areas. The front is the ledge's lip, falling into the cloud sea. Routes: high (ramp, terrace, ramp), low (the
corridor), and the perch (terrace, bridge, overlook).

Every element and every pixel belongs to a depth ZONE (arena/zones.py): playfield, focus, frame, backdrop, vista, sky.
Things carry their zone; ground pixels get theirs from `zone_at`; the scenery behind the ledge (`scenery`) is built
in forced scale (smaller, sunk, simpler) so an orthographic camera still shows real distance.

Key sizes (metres; a person is 1.7): see DIMENSIONS and arena/README.md.
"""
from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path

import numpy as np

from ...geo import _hash, fbm, poisson, sd_box, smin, smooth, to_uv, to_xy, vnoise  # noqa: F401

NAME = "hushfall_crossing"
PPM = 32.0                      # map px per metre
EL_DEG = float(os.environ.get("ARENA_EL", "40"))
EL = math.radians(EL_DEG)        # the camera's look down
SE, CE = math.sin(EL), math.cos(EL)
R2 = math.sqrt(2.0)
CLIFF = 30.0                     # metres down the ledge to the cloud floor
SUN = (-0.62, 0.52, 0.0)         # toward the sun, horizontal (u, v), normalised below with its elevation
SUN_EL = math.radians(50.0)
HUMAN = 1.7                      # the scale reference

# ---------------------------------------------------------------- the plan (metres)
LOBE = 18.0, 1.8, 12.0, 14.4, 3.0          # each camp area: |centre u|, centre v, radii u, v, superellipse exponent
DAIS = (0.0, -2.0, 8.0, 4.8)               # the ruin terrace: centre u, v, half sizes (16 x 9.6 m)
ZD = 3.0                                    # its height
RAMP_V, RAMP_HW, RAMP_LEN = -1.6, 3.0, 7.0  # the ramps down to each camp area: centre v, half width (6 m), run (23 deg)
CORR = (0.0, 7.0, 10.0, 4.2)                # the corridor under the bridge (ground level): centre u, v, half sizes
APRON = (0.0, -9.6, 10.0, 2.8)              # the apron at the terrace's foot, along the lip: the low front route
CORR_DIP = 0.4                              # its floor lies this much hollow
OVER = (0.0, 14.4, 7.6, 3.4)                # the overlook at the far edge (15.2 x 6.8 m)
ZO = 3.2
DECK = dict(u0=-1.8, u1=1.8, v0=2.5, v1=11.3, z0=ZD, z1=ZO, walk=1.5)   # the timber bridge: 3.6 m wide, 8.8 m span
STONES = (0.0, -2.2, 3.4, 2.0)              # the Stones objective on the terrace: centre u, v and the capture ring's radii
MENHIRS_SPENT = 7                            # the removed menhir ring's random draws, kept so the layout stays put
CAMPS = {"west": (-21.0, 0.5), "east": (21.0, 0.5)}
CAMP_HALF = 6.0                             # half the palisade square (12 x 12 m)
EDGE_NOISE = 0.35                           # how far the terrace outlines wander (m): ruins, not boxes
# the routes (u, v, level) with level 1 = on the bridge deck; written from the west
LANES = {
    "high": [(-15.5, -1.0, 0), (-12.0, RAMP_V, 0), (-6.0, RAMP_V, 0), (-3.6, 0.6, 0), (3.6, 0.6, 0), (6.0, RAMP_V, 0),
             (12.0, RAMP_V, 0), (15.5, -1.0, 0)],
    "low": [(-15.5, 3.0, 0), (-10.5, 7.6, 0), (0.0, 7.8, 0), (10.5, 7.6, 0), (15.5, 3.0, 0)],
    "front": [(-15.5, -3.5, 0), (-10.5, -8.6, 0), (0.0, -9.8, 0), (10.5, -8.6, 0), (15.5, -3.5, 0)],
    "perch": [(-15.5, -1.0, 0), (-12.0, RAMP_V, 0), (-6.0, RAMP_V, 0), (-2.0, 0.8, 0), (0.0, 2.0, 0), (0.0, 6.5, 1),
              (0.0, 12.0, 0), (0.0, 14.6, 0)],
}
SEED = 11

# ---------------------------------------------------------------- the picture: framed from the layout
W = 1920
H = 1080
FRONT_PX = 120                   # the cloud sea under the ledge's front lip
PLAY_FRONT = -12.6               # the lip's v at the centre


def _frame():
    y0 = H - FRONT_PX + PLAY_FRONT * SE * PPM          # the lip lands FRONT_PX above the bottom
    return W / 2, float(round(y0))


X0, Y0 = _frame()


# ---------------------------------------------------------------- projection
def proj(u, v, z=0.0):
    return X0 + u * PPM, Y0 - (v * SE + z * CE) * PPM


def screen_p(v, z):
    """how high a point sits on the picture, in metres (sy = Y0 - P * PPM)"""
    return v * SE + z * CE


def z_for_p(p, v):
    """the height that puts a point at depth v on screen height p: how the scenery is sunk into its band"""
    return (p - v * SE) / CE


def depth(u, v, z=0.0):
    return v * CE - z * SE


def sun_vec():
    """toward the sun in (u, v, z)"""
    h = np.array(SUN[:2]) / np.linalg.norm(SUN[:2]) * math.cos(SUN_EL)
    return (float(h[0]), float(h[1]), math.sin(SUN_EL))


# ---------------------------------------------------------------- the land
def sd_lobe(u, v, side, grow=(0.0, 0.0), dv=0.0):
    cu, cv, ru, rv, p = LOBE
    ru, rv, cv = ru + grow[0], rv + grow[1], cv + dv
    cu = -cu if side < 0 else cu
    m = ((np.abs(np.asarray(u) - cu) / ru) ** p + (np.abs(np.asarray(v) - cv) / rv) ** p) ** (1 / p)
    return (m - 1) * min(ru, rv)


def edge_noise(u, v):
    """how far a terrace's outline wanders from its box (m): broken ruin edges"""
    return EDGE_NOISE * fbm(u, v, 2.6, 21) + 0.12 * fbm(u, v, 0.9, 22)


def sd_dais(u, v):
    return sd_box(u, v, DAIS, 1.4) - edge_noise(u, v)


def sd_over(u, v):
    return sd_box(u, v, OVER, 1.8) - edge_noise(u, v)


def sd_play(u, v):
    """signed distance to the walkable top of the ledge: the two camp areas, the terrace, the corridor, the overlook"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64)
    d = np.minimum(sd_lobe(u, v, -1), sd_lobe(u, v, 1))
    d = np.minimum(d, sd_box(u, v, DAIS, 1.2))
    d = np.minimum(d, sd_box(u, v, CORR, 0.5))
    d = np.minimum(d, sd_box(u, v, OVER, 1.6))
    d = smin(d, sd_box(u, v, APRON, 2.0), 3.0)        # filleted: no spike of lip between the apron and a camp
    return d + 0.35 * fbm(u, v, 2.2, 3)


def sd_shelf(u, v):
    """the forest shelf: ledge ground round the back and sides of each camp area where the frame's spruces stand; the
    centre back stays open (the overlook juts out over the drop) and the front stays a clean lip"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64)
    d = np.minimum(sd_lobe(u, v, -1, (5.5, 6.0), 2.5), sd_lobe(u, v, 1, (5.5, 6.0), 2.5))
    d = np.maximum(d, -(np.abs(u) - 9.0))                   # not behind the overlook
    d = np.maximum(d, -(v + 9.0 - 3.0 * smooth(22, 30, np.abs(u))))   # only the corners come forward
    return d + 0.6 * fbm(u, v, 4.0, 5)


def sd_plateau(u, v):
    """the ledge's whole top: the play area and the forest shelf round it"""
    return np.minimum(sd_play(u, v), sd_shelf(u, v))


def raised(u, v):
    """height of the built-up ground (the terrace, its ramps, the overlook) above the snow"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64)
    au = np.abs(u)
    zd = ZD * (1 - smooth(-0.3, 0.1, sd_dais(u, v)))
    ramp = np.clip(1 - (au - (DAIS[2] - 0.3)) / RAMP_LEN, 0, 1) * (au > DAIS[2] - 0.8)
    ramp = ZD * ramp * (1 - smooth(RAMP_HW - 0.15, RAMP_HW + 0.2, np.abs(v - RAMP_V) + 0.5 * edge_noise(u, v)))
    zo = ZO * (1 - smooth(-0.3, 0.1, sd_over(u, v)))
    return np.maximum(np.maximum(zd, ramp), zo)


def lane_dist(u, v):
    """distance (m) from the nearest trodden lane (high and low; the perch is planks and a dead end)"""
    best = np.full(np.shape(u), 1e9)
    for name, pts in LANES.items():
        if name == "perch":
            continue
        for (a, b, la), (c, d, lb) in zip(pts, pts[1:]):
            if la or lb:
                continue
            du, dv = c - a, d - b
            t = np.clip(((u - a) * du + (v - b) * dv) / (du * du + dv * dv), 0, 1)
            best = np.minimum(best, np.hypot(u - a - t * du, v - b - t * dv))
    return best


def terrain(u, v):
    """height of the ground in metres (the ledge's cliffs too)"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64)
    d = sd_plateau(u, v)
    z = 0.22 * fbm(u, v, 9.0, 1) + 0.1 * fbm(u, v, 3.0, 2)
    r = raised(u, v)
    z = z * (1 - smooth(0.2, 1.0, r)) + r
    # the corridor under the bridge lies a little hollow, for headroom under the deck
    z = z - CORR_DIP * (1 - smooth(-2.4, 1.2, sd_box(u, v, (0.0, 7.6, 7.6, 1.8), 0.8)))
    # the forest shelf falls away behind the camps, so the ring's back rows stand lower and the back opens over
    # them; wind drifts banked along the ledge's lip
    sp = sd_play(u, v)
    z -= 4.0 * smooth(1.5, 8.0, sp) * smooth(2.0, 9.0, v) * (r < 0.1)
    z += 0.45 * smooth(-3.2, -1.2, d) * (1 - smooth(-0.6, 0.0, d)) * (r < 0.1)
    # the cliff: a rocky drop in terraces
    drop = smooth(-0.15, 3.2, d + 0.25 * fbm(u, v, 1.6, 9))
    ledge = 0.5 + 0.5 * fbm(u * 1.2, v * 1.2, 2.5, 4)
    zc = -CLIFF * drop ** (0.8 + 0.6 * ledge)
    step_h = 2.6 + 0.8 * fbm(u, v, 5.0, 12)
    q = zc / step_h
    fq = np.floor(q)
    zc = (fq + smooth(0.55, 1.0, q - fq)) * step_h
    z = z + zc
    for cu, cv in CAMPS.values():                       # camp floors levelled
        k = smooth(8.5, 5.0, np.hypot(u - cu, v - cv))
        z = z * (1 - 0.7 * k)
    return z


def slope(u, v, e=0.25):
    du = (terrain(u + e, v) - terrain(u - e, v)) / (2 * e)
    dv = (terrain(u, v + e) - terrain(u, v - e)) / (2 * e)
    return np.hypot(du, dv)


# ---------------------------------------------------------------- the things on it
def camp_square(side):
    """the camp's palisade: the two sides of its x,y square that face away from the field; (u, v) post points"""
    cu, cv = CAMPS[side]
    cx, cy = to_xy(cu, cv)
    h = CAMP_HALF
    pts = []
    n = int(2 * h / 0.62)
    for i in range(n + 1):
        t = -h + 2 * h * i / n
        if side == "west":
            pts.append(to_uv(cx - h, cy + t))
            if i:
                pts.append(to_uv(cx + t, cy + h))
        else:
            pts.append(to_uv(cx + h, cy + t))
            if i:
                pts.append(to_uv(cx + t, cy - h))
    return pts


def outline(sd, box, step=0.5):
    """points round a terrace's broken outline: (u, v, nu, nv) with the outward normal, walking the box's rounded
    rectangle and pushing each point out to where sd = 0"""
    cu, cv, hu, hv = box
    pts = []
    per = 4 * (hu + hv)
    n = int(per / step)
    for i in range(n):
        s = i / n * per
        if s < 2 * hu:
            u, v, nu, nv = cu - hu + s, cv - hv, 0.0, -1.0
        elif s < 2 * hu + 2 * hv:
            u, v, nu, nv = cu + hu, cv - hv + (s - 2 * hu), 1.0, 0.0
        elif s < 4 * hu + 2 * hv:
            u, v, nu, nv = cu + hu - (s - 2 * hu - 2 * hv), cv + hv, 0.0, 1.0
        else:
            u, v, nu, nv = cu - hu, cv + hv - (s - 4 * hu - 2 * hv), -1.0, 0.0
        # corners: round them by stepping in along the diagonal
        cx = np.clip(u, cu - hu + 1.6, cu + hu - 1.6); cy = np.clip(v, cv - hv + 1.6, cv + hv - 1.6)
        du, dv = u - cx, v - cy
        ln = math.hypot(du, dv)
        if ln > 1e-6:
            nu, nv = du / ln, dv / ln
            u, v = cx + nu * 1.6, cy + nv * 1.6
        for _ in range(4):                                # onto the noisy outline
            d = float(sd(np.array(u), np.array(v)))
            u, v = u - nu * d, v - nv * d
        pts.append((u, v, nu, nv))
    return pts


def _gap(name, u, v, nu, nv):
    """where a terrace's edge is open: the ramps' mouths and the bridge's landings"""
    if name == "dais" and abs(nu) > 0.5 and abs(v - RAMP_V) < RAMP_HW + 0.3:
        return True
    if abs(u) < DECK["u1"] + 0.5 and ((name == "over" and nv < -0.5) or (name == "dais" and nv > 0.5)):
        return True
    return False


COURSES = [-0.35, 0.3, 0.92, 1.55, 2.2, 2.75]     # the masonry's course lines (absolute z, metres)


def ruin_edges(rng):
    """the masonry of the terrace and the overlook, as a ruin: courses of dressed blocks in running bond (each course
    laid along the outline with its own joints) on every face the camera sees, the top courses broken; a kerb of
    single blocks along the lip, gappy, on every side (so the edges that face away still read against what is below
    them); a cornice of drifted snow along the top; broken stubs of parapet on a few stretches"""
    blocks, kerb, cornice, stubs = [], [], [], []
    for name, sd, box, ztop in (("dais", sd_dais, DAIS, ZD), ("over", sd_over, OVER, ZO)):
        line = outline(sd, box, 0.2)
        P_ = np.array([(u, v) for u, v, _, _ in line])
        seg = np.hypot(*(np.roll(P_, -1, 0) - P_).T)
        cum = np.concatenate([[0], np.cumsum(seg)])
        total = cum[-1]

        def at(s_):
            s_ = s_ % total
            i = int(np.searchsorted(cum, s_, side="right") - 1)
            i = min(i, len(line) - 1)
            return line[i]
        lines = list(COURSES[:-1]) + [ztop - 0.6]
        for k, (z0, z1) in enumerate(zip(lines, lines[1:] + [ztop])):
            if z1 - z0 < 0.25:
                continue
            s_ = rng.uniform(0, 1.2)
            while s_ < total:
                ln = rng.uniform(0.8, 1.35)
                u, v, nu, nv = at(s_ + ln / 2)
                s_ += ln
                if nv > 0.55 or _gap(name, u, v, nu, nv):
                    continue                              # turned away from the camera, or open
                g = float(terrain(np.array(u + nu * 1.4), np.array(v + nv * 1.4)))
                if z1 < g - 0.1:
                    continue
                top_course = z1 >= ztop - 0.01
                if top_course and rng.random() < 0.22:
                    continue                              # the broken top
                if k == len(lines) - 2 and rng.random() < 0.08:
                    continue
                blocks.append(dict(u=u, v=v, nu=nu, nv=nv, z0=max(z0, g - 0.35), z1=z1 + rng.uniform(-0.04, 0.05),
                                   len=ln * 0.97, dep=rng.uniform(0.6, 0.85), out=rng.uniform(-0.06, 0.1),
                                   tw=rng.uniform(-3, 3), val=rng.uniform(-0.12, 0.12)))
        # the kerb and the cornice along the lip, all round
        s_ = rng.uniform(0, 1.0)
        while s_ < total:
            ln = rng.uniform(0.7, 1.2)
            u, v, nu, nv = at(s_ + ln / 2)
            s_ += ln
            if _gap(name, u, v, nu, nv):
                continue
            if rng.random() < (0.45 if nv < 0.55 else 0.8):  # the lips that face away get more: they carry the edge
                kerb.append(dict(u=u - nu * 0.3, v=v - nv * 0.3, nu=nu, nv=nv, z0=ztop - 0.3,
                                 z1=ztop + rng.uniform(0.25, 0.5), len=ln * 0.92, dep=0.5, out=0.0,
                                 tw=rng.uniform(-6, 6), val=rng.uniform(-0.12, 0.12)))
        s_ = rng.uniform(0, 1.5)
        while s_ < total:
            ln = rng.uniform(1.4, 2.6)
            u, v, nu, nv = at(s_ + ln / 2)
            s_ += ln + rng.uniform(0.0, 0.9)
            if _gap(name, u, v, nu, nv):
                continue
            cornice.append(dict(u=u - nu * 0.25, v=v - nv * 0.25, nu=nu, nv=nv, z=ztop, len=ln, h=rng.uniform(0.14, 0.24)))
        # the parapet's broken stubs: a few runs of 1-3 blocks on the lip, not a wall
        for (u, v, nu, nv) in outline(sd, box, 1.0):
            if rng.random() > 0.12 or _gap(name, u, v, nu, nv) or abs(u) < DECK["u1"] + 1.2:
                continue
            if name == "dais" and abs(nu) > 0.5 and abs(v - RAMP_V) < RAMP_HW + 0.8:
                continue
            stubs.append(dict(u=u - nu * 0.35, v=v - nv * 0.35, nu=nu, nv=nv, z=ztop, h=rng.uniform(0.5, 1.0),
                              len=rng.uniform(1.2, 2.4), seed=rng.randrange(1 << 20)))
    # the ramps' side faces (the one the camera sees): courses down to the ground as the ramp falls
    for sgn in (-1, 1):
        for k, (z0, z1) in enumerate(zip(COURSES[:-1], COURSES[1:] + [ZD])):
            s_ = DAIS[2] - 0.6 + rng.uniform(0, 0.6)
            while s_ < DAIS[2] + RAMP_LEN:
                ln = rng.uniform(0.8, 1.3)
                u = sgn * (s_ + ln / 2)
                s_ += ln
                v = RAMP_V - RAMP_HW - 0.05
                top = float(raised(np.array(u), np.array(v + 0.6)))
                if z1 > top + 0.15:
                    continue
                g = float(terrain(np.array(u), np.array(v - 1.2)))
                blocks.append(dict(u=u, v=v, nu=0.0, nv=-1.0, z0=max(z0, g - 0.35), z1=min(z1, top + 0.05),
                                   len=ln * 0.97, dep=rng.uniform(0.6, 0.85), out=rng.uniform(-0.05, 0.08),
                                   tw=rng.uniform(-2, 2), val=rng.uniform(-0.12, 0.12)))
    # the ramps' edges: a kerb stepping down each side, so the slope reads
    for sgn in (-1, 1):
        for side in (-1, 1):
            s_ = DAIS[2] + rng.uniform(-0.2, 0.4)
            while s_ < DAIS[2] + RAMP_LEN - 0.6:
                ln = rng.uniform(0.7, 1.1)
                u = sgn * (s_ + ln / 2)
                s_ += ln + rng.uniform(0.0, 0.35)
                if rng.random() < 0.25:
                    continue
                v = RAMP_V + side * (RAMP_HW - 0.15)
                top = float(raised(np.array(u), np.array(RAMP_V)))
                kerb.append(dict(u=u, v=v, nu=0.0, nv=float(side), z0=top - 0.35, z1=top + rng.uniform(0.22, 0.4),
                                 len=ln * 0.92, dep=0.45, out=0.0, tw=rng.uniform(-6, 6), val=rng.uniform(-0.12, 0.12)))
    return blocks, kerb, cornice, stubs


def layout(seed: int = SEED) -> dict:
    """everything placed. Each thing: kind, u, v, zone (focus / playfield / frame), and its own fields"""
    rng = random.Random(seed)
    things = []
    keep = []                                       # (u, v, r) clear zones and placed solids

    def add(**t):
        things.append(t)
        return t

    # --- the camps: the heart, tower, fire and banners are what is fought for (focus); the palisade and tents bound
    # the camp (frame); crates and woodpile are dressing (playfield)
    for side, (cu, cv) in CAMPS.items():
        s = -1 if side == "west" else 1
        cx, cy = to_xy(cu, cv)
        add(kind="heart", side=side, u=cu, v=cv, r=1.1, zone="focus")
        for pu, pv in camp_square(side):
            if sd_play(pu, pv) > -0.6:
                continue
            add(kind="stake", side=side, u=pu, v=pv, h=2.3 + 0.35 * rng.random(), r=0.2, lean=rng.uniform(-3, 3),
                zone="frame")
        for (dx, dy, rot) in (((-3.6, -1.2, 90.0), (1.2, 3.6, 0.0)) if side == "west" else ((3.6, 1.2, 90.0), (-1.2, -3.6, 0.0))):
            tu, tv = to_uv(cx + dx, cy + dy)
            add(kind="tent", side=side, u=tu, v=tv, rot=rot, r=1.7, zone="frame")
        add(kind="tower", side=side, u=cu - s * 2.6, v=cv + 5.4, r=1.3, zone="focus")
        add(kind="fire", side=side, u=cu - s * 2.8, v=cv - 2.0, r=0.6, zone="focus")
        for dv in (-4.6, 4.2):
            add(kind="banner", side=side, u=cu - s * 4.0, v=cv + dv, r=0.25, zone="focus")
        add(kind="crates", side=side, u=cu + s * 4.6, v=cv - 2.8, r=0.8, zone="playfield")
        add(kind="woodpile", side=side, u=cu + s * 3.6, v=cv + 2.8, rot=0.0, r=0.9, zone="playfield")
    for t in things:
        keep.append((t["u"], t["v"], t.get("r", 0.5)))

    # --- the Stones on the terrace: an open capture ring with no props (the menhir ring and its altar cluttered the
    # centre; the game marks the objective itself). The ring's draws are still taken so everything after it stands
    # where it stood.
    su, sv, sru, srv = STONES
    for k in range(MENHIRS_SPENT):
        rng.random(), rng.uniform(0, 180)
    keep.append((su, sv, 4.0))
    # --- the bridge (focus: the timber, its plank rhythm, its snow), its lamps at both ends
    add(kind="bridge", u=0.0, v=(DECK["v0"] + DECK["v1"]) / 2, r=0.0, zone="focus", **{k: DECK[k] for k in DECK})
    for e, (vv, zz) in enumerate(((DECK["v0"] - 0.4, ZD), (DECK["v1"] + 0.4, ZO))):
        for side in (-1, 1):
            add(kind="lamppost", u=side * 2.3, v=vv, r=0.2, lit=True, zone="focus")
    keep.append((0.0, 6.5, 2.4))

    # --- the ruin: block courses on the terraces' faces, a gappy kerb and a cornice of snow along their lips, broken
    # parapet stubs; toppled blocks at the feet and on the overlook; broken columns
    blocks, kerb, cornice, stubs = ruin_edges(rng)
    add(kind="ruin", u=0.0, v=0.0, r=0.0, zone="frame", blocks=blocks, kerb=kerb, cornice=cornice)
    for st in stubs:
        add(kind="stub", r=0.4, zone="frame", **st)
    topple = [(-9.9, -6.7, 30), (9.7, -6.8, -25), (-5.4, -8.0, 70), (11.4, 4.6, 10), (-11.6, 4.4, -40),
              (-8.6, 10.6, 15), (8.8, 10.4, -60), (-4.6, 15.8, 20), (5.2, 16.4, -35)]
    for (u, v, rot) in topple:
        add(kind="block", u=u, v=v, rot=rot, r=0.8, seed=rng.randrange(1 << 20), zone="frame")
        keep.append((u, v, 1.2))
    for (u, v, h) in ((-6.2, 13.0, 1.9), (6.4, 12.6, 1.1), (-6.8, -5.6, 1.4), (6.9, 1.6, 2.2)):
        add(kind="column", u=u, v=v, h=h, r=0.45, seed=rng.randrange(1 << 20), zone="frame")
        keep.append((u, v, 1.0))

    # --- rocks at a few chokepoints (cover): the ramps' shoulders
    rocks = [(-13.6, 3.0, 0.9), (13.6, 3.0, 0.9), (-13.8, -6.2, 0.8), (13.8, -6.2, 0.8)]
    for (u, v, r) in rocks:
        add(kind="rock", u=u, v=v, r=r, seed=rng.randrange(1 << 20), zone="frame")
        keep.append((u, v, r + 0.6))

    # --- the frame's forest ring on the shelf: taller at the back, short at the front corners, the centre back open
    def ring_region(r_):
        u = r_.uniform(-36, 36); v = r_.uniform(-14, 24)
        sp, sh = float(sd_play(u, v)), float(sd_shelf(u, v))
        if sp < 0.9 or sh > -0.5 or abs(u) < 9.6 + 3.0 * float(smooth(5, 10, v)):
            return None
        back = smooth(-6, 10, v)
        hh = r_.uniform(6.5, 8.5) + 1.5 * float(back) + 0.8 * float(smooth(1, 6, sp))
        if v < -6 and abs(u) < 27:
            return None
        return (u, v, 0.5 + hh * 0.13)
    for u, v, r in poisson(rng, 14000, ring_region, 1.45, keep):
        add(kind="spruce", u=u, v=v, h=(r - 0.5) / 0.13, r=0.8, cls=rng.choice(("a", "b", "b")), zone="frame")
        keep.append((u, v, 0.9))
    # a grove at each camp area's back edge: cover, kept out of the lanes
    # (the east grove mirrors the west one, so both camps' back corners play the same)
    gu, gv = -26.5, -7.0
    for u, v, r in poisson(rng, 200, lambda r_: (gu + r_.uniform(-1.4, 1.4), gv + r_.uniform(-1.0, 1.0), 1.0), 1.7, keep)[:2]:
        h, cls = rng.uniform(5.5, 7.0), rng.choice(("a", "b"))
        for s_ in (1, -1):
            add(kind="spruce", u=s_ * u, v=v, h=h, r=0.7, cls=cls, zone="frame")
            keep.append((s_ * u, v, 0.9))
    return dict(things=things)


# ---------------------------------------------------------------- the back of the map: forced-scale scenery
# Bands are in screen metres P (sy = Y0 - P * PPM), measured from P_BACK, the screen height of the ledge's back edge.
# Each layer is placed deep (its v) and sunk (z) so that it lands in its band; layers further back are built smaller,
# simpler and lower in detail (zones.py budgets them).
P_BACK = 17.0 * SE                  # the overlook's back edge on the ground
SCENERY = dict(
    # forest masses on three ridges past the drop (backdrop), smaller with every step back: (v, foot P, crest P,
    # tree height (m, forced scale), spacing, rows)
    forests=[
        dict(v=34.0, foot=P_BACK - 3.0, crest=(P_BACK + 0.4, P_BACK + 2.2), h=(4.4, 6.2), gap=1.15, depth=5.0, seed=31),
        dict(v=52.0, foot=P_BACK - 0.5, crest=(P_BACK + 2.6, P_BACK + 4.2), h=(3.0, 4.2), gap=0.85, depth=4.0, seed=32),
        dict(v=72.0, foot=P_BACK + 1.5, crest=(P_BACK + 4.4, P_BACK + 5.8), h=(2.0, 2.8), gap=0.62, depth=3.0, seed=33),
    ],
    # the cumulus (vista): (u, v, base P, width, height, pink crown): towers past the forests, taller at the sides so
    # their crowns stand over the forest ring, lower in the middle so the window over the overlook stays open; two
    # standing up out of the cloud sea at the front corners
    towers=[(-25.0, 110.0, P_BACK + 2.4, 17.0, 12.0, True), (-7.0, 118.0, P_BACK + 4.0, 13.0, 8.0, True),
            (9.0, 112.0, P_BACK + 3.4, 15.0, 9.5, True), (26.0, 116.0, P_BACK + 2.6, 16.0, 11.5, True),
            (-33.0, -19.0, -14.5, 14.0, 11.5, True), (33.5, -19.0, -14.5, 13.0, 12.5, True)],
    # the cloud sea under the ledge's front lip: low wide masses whose tops stand just under the lip (base P, top P),
    # in front of the cliff as it falls
    sea=dict(v=(-16.0, -21.0), base=-13.5, top=(-8.8, -7.2), u=(-34.0, 34.0), n=10),
)


def _ridge(spec, seed):
    """a low forested ridge as a height field (U, V, Z), its foot sunk to screen height `foot`, its crest wandering
    between the crest band's ends"""
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


def scenery() -> dict:
    """the backdrop and vista: the forest ridges and their trees, the cumulus towers and the cloud sea"""
    out = dict(strips=[], trees=[], clouds=[])
    rng = random.Random(77)
    for k, spec in enumerate(SCENERY["forests"]):
        U, V, Z = _ridge(spec, spec["seed"])
        out["strips"].append(dict(name=f"forest{k}", zone="backdrop", U=U, V=V, Z=Z))
        # trees over the ridge in rows from its foot to its crest, thinned in clearings: masses, not a carpet
        g = spec["gap"]
        for i in range(1, U.shape[0]):
            for uu in np.arange(-38.0, 38.0, g):
                u = uu + rng.uniform(-0.35, 0.35) * g
                if fbm(u, V[i, 0] * 0.3, 6.0, 41 + k) < -0.25 - 0.1 * k:
                    continue
                j = int(np.clip(round((u + 40.0) / 0.8), 0, U.shape[1] - 1))
                out["trees"].append(dict(u=float(u), v=float(V[i, j] + rng.uniform(-.2, .2)), z=float(Z[i, j]) - 0.15,
                                         h=rng.uniform(*spec["h"]), zone="backdrop", band=k))
    for i, (cu, cv, pb, wd, ht, pink) in enumerate(SCENERY["towers"]):
        out["clouds"].append(dict(u=cu, v=cv, z=z_for_p(pb, cv), w=wd, h=ht, zone="vista", floor=False, pink=pink,
                                  seed=300 + i))
    sea = SCENERY["sea"]
    cr = random.Random(41)
    for k in range(sea["n"]):
        cu = sea["u"][0] + (sea["u"][1] - sea["u"][0]) * (k + cr.uniform(0.2, 0.8)) / sea["n"]
        cv = cr.uniform(*sea["v"])
        top = cr.uniform(*sea["top"])
        z0 = z_for_p(sea["base"], cv)
        # a floor mass's puffs reach about half its nominal height: size it so its real top lands on `top`
        out["clouds"].append(dict(u=float(cu), v=float(cv), z=z0, w=cr.uniform(11, 15), h=1.9 * (top - sea["base"]) / CE,
                                  zone="vista", floor=True, pink=False, seed=100 + k))
    return out


# The clouds as layers that drift (the viewer's parallax, arena/layers.py): each rendered alone and complete, the far
# cumulus and the cloud sea as strips STRIP_W px wide that wrap seamlessly (every mass near a seam is repeated one
# period over), the two towers standing out of the sea at the front corners as their own layer
STRIP_W = 3840
HIDDEN_TOWERS = [(42.0, 114.0, P_BACK + 3.0, 14.0, 10.0, True), (57.0, 111.0, P_BACK + 2.2, 16.0, 12.0, True),
                 (-48.0, 117.0, P_BACK + 3.6, 13.0, 9.0, True)]


def cloud_layers() -> dict:
    period = STRIP_W / PPM
    out = dict(period=period, far=[], sea=[], corner=[])

    def place_(layer, c):
        for k in (-1, 0, 1):
            u = c["u"] + k * period
            if abs(u) - c["w"] * 0.6 < period / 2:
                out[layer].append(dict(c, u=u))
    towers = SCENERY["towers"]
    for i, (cu, cv, pb, wd, ht, pink) in enumerate(list(towers[:4]) + HIDDEN_TOWERS):
        place_("far", dict(u=cu, v=cv, z=z_for_p(pb, cv), w=wd, h=ht, floor=False, pink=pink, seed=300 + i))
    for i, (cu, cv, pb, wd, ht, pink) in enumerate(towers[4:]):
        out["corner"].append(dict(u=cu, v=cv, z=z_for_p(pb, cv), w=wd, h=ht, floor=False, pink=pink, seed=304 + i))
    sea = SCENERY["sea"]
    cr = random.Random(41)
    n = 20
    for k in range(n):
        cu = -period / 2 + period * (k + cr.uniform(0.2, 0.8)) / n
        cv = cr.uniform(*sea["v"])
        top = cr.uniform(*sea["top"])
        place_("sea", dict(u=float(cu), v=float(cv), z=z_for_p(sea["base"], cv), w=cr.uniform(11, 15),
                           h=1.9 * (top - sea["base"]) / CE, floor=True, pink=False, seed=500 + k))
    return out


# ---------------------------------------------------------------- zones of the ground
def zone_at(u, v, z, frame_trees=()):
    """the depth zone of a ground point (names in zones.ZONES): the play floor, the frame (the terraces' faces, the
    shelf, the tree line's ground, the top of the cliff), then the cliff as it sinks toward the cloud sea"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64); z = np.asarray(z, np.float64)
    d = sd_play(u, v)
    out = np.full(u.shape, "frame", object)
    top = (d < -0.9) & (z > -0.9)
    faces = np.abs(z - raised(u, v)) > 0.6
    out[top & ~faces] = "playfield"
    near = np.zeros(u.shape, bool)
    for (tu, tv) in frame_trees:
        near |= (u - tu) ** 2 + (v - tv) ** 2 < 1.6 ** 2
    out[near & top] = "frame"
    # the cliff under the lip stays frame ("the edge is here") until it sinks into the cloud sea (paint.FOG_Z)
    return out


# ---------------------------------------------------------------- the walk grid
CELL = 0.5
GU0, GU1, GV0, GV1 = -32.0, 32.0, -13.0, 19.0


def walk_grid(lay: dict) -> dict:
    """per CELL: ground height (m), and what it is: 0 blocked, 1 snow, 2 trodden lane. The bridge deck is a second
    level over the corridor (DECK)"""
    us = np.arange(GU0 + CELL / 2, GU1, CELL)
    vs = np.arange(GV0 + CELL / 2, GV1, CELL)
    U, V = np.meshgrid(us, vs)
    Z = terrain(U, V)
    kind = np.ones(U.shape, np.uint8)
    kind[lane_dist(U, V) < 1.2] = 2
    kind[sd_play(U, V) > -0.5] = 0                                   # the ledge's lip, the forest shelf and beyond
    kind[slope(U, V) > 0.62] = 0                                     # the terraces' faces; the ramps stay walkable
    # the terrace's back face, which the camera cannot see, and the overlook's: their feet are not walkable
    kind[(np.abs(U) < DAIS[2] + 0.4) & (V > DAIS[1] + DAIS[3] - 0.6) & (V < DAIS[1] + DAIS[3] + 0.8) & (Z < ZD - 0.4)] = 0
    D = DECK
    # the bridge's landings: the high ground under the deck's two ends is walkable, so units step on and off it
    kind[(np.abs(U) < D["walk"]) & (V > D["v0"] - 0.6) & (V < D["v1"] + 0.6) & (Z > ZD - 0.6)] = 1
    for t in lay["things"]:
        k = t["kind"]
        if k == "ruin":
            continue
        u, v = t["u"], t["v"]
        if k == "stub":
            a = math.atan2(t["nv"], t["nu"]) + math.pi / 2
            du, dv = math.cos(a) * t["len"] / 2, math.sin(a) * t["len"] / 2
            tt = np.clip(((U - u + du) * 2 * du + (V - v + dv) * 2 * dv) / max(4 * (du * du + dv * dv), 1e-6), 0, 1)
            kind[np.hypot(U - (u - du) - tt * 2 * du, V - (v - dv) - tt * 2 * dv) < 0.45] = 0
            continue
        r = {"spruce": 1.1, "rock": t.get("r", 1) * 1.05, "tent": 1.7, "tower": 1.3, "heart": 0.9, "stake": 0.32,
             "menhir": 0.55, "altar": 0.8, "crates": 0.8, "woodpile": 0.9, "banner": 0.25, "lamppost": 0.2,
             "fire": 0.6, "block": 0.8, "column": 0.6}.get(k)
        if r:
            kind[np.hypot(U - u, V - v) < r] = 0
    return dict(us=us, vs=vs, z=Z.astype(np.float32), kind=kind)


def spawns(g: dict, lay: dict) -> dict:
    """spawn points per camp: a ring of free cells round the heart, inside the palisade, clear of tents and props"""
    out = {}
    for side, (cu, cv) in CAMPS.items():
        pts = []
        for r in (2.4, 3.6):
            for k in range(12):
                a = k / 12 * math.tau + (0.26 if r > 3 else 0)
                u, v = cu + r * math.cos(a), cv + r * 0.85 * math.sin(a)
                i, j = int((v - GV0) / CELL), int((u - GU0) / CELL)
                if 0 <= i < g["kind"].shape[0] and 0 <= j < g["kind"].shape[1]:
                    near = g["kind"][max(0, i - 1):i + 2, max(0, j - 1):j + 2]
                    if (near > 0).all():
                        pts.append((round(u, 2), round(v, 2), round(float(g["z"][i, j]), 2)))
        out[side] = pts
    return out


DIMENSIONS = {
    "person (scale reference)": f"{HUMAN} m",
    "metre grid": f"1 m = {PPM:.0f} px across, {PPM * SE:.1f} px into the picture, {PPM * CE:.1f} px up",
    "camp palisade": f"{2 * CAMP_HALF:.0f} x {2 * CAMP_HALF:.0f} m",
    "camp to camp (hearts)": f"{CAMPS['east'][0] - CAMPS['west'][0]:.0f} m",
    "camp heart to the Stones": f"{math.hypot(CAMPS['east'][0] - STONES[0], CAMPS['east'][1] - STONES[1]):.0f} m",
    "ruin terrace": f"{2 * DAIS[2]:.0f} x {2 * DAIS[3]:.1f} m, {ZD:.1f} m high",
    "ramps": f"{2 * RAMP_HW:.0f} m wide, {RAMP_LEN:.0f} m run ({math.degrees(math.atan(ZD / RAMP_LEN)):.0f} deg)",
    "the Stones": f"an open {2 * STONES[2]:.1f} x {2 * STONES[3]:.1f} m capture ring, no props",
    "bridge": f"{DECK['u1'] - DECK['u0']:.1f} m wide ({2 * DECK['walk']:.0f} m walked), {DECK['v1'] - DECK['v0']:.1f} m span",
    "headroom under the bridge": f"{ZD - 0.5 + CORR_DIP:.1f} m",
    "corridor": f"{2 * CORR[2]:.0f} m long, {2 * CORR[3]:.1f} m deep",
    "overlook": f"{2 * OVER[2]:.1f} x {2 * OVER[3]:.1f} m, {ZO:.1f} m high",
    "spruces (frame)": "6.5-12 m (4-7 people)",
    "watchtower": "4.6 m platform, 7.5 m roof",
    "tents": "3.4 x 2.7 m, 2.3 m ridge",
}


def export(out: Path, seed: int = SEED) -> dict:
    """the place for Blender: scene3d.json + terrain.npz + scenery.npz"""
    from ... import zones as Z_
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lay = layout(seed)
    st = 0.3
    us = np.arange(-42.0, 42.0 + st, st)
    vs = np.arange(-24.0, 26.0 + st, st)
    U, V = np.meshgrid(us, vs)
    Z = terrain(U, V)
    lane = lane_dist(U, V)
    np.savez_compressed(out / "terrain.npz", u=U.astype(np.float32), v=V.astype(np.float32), z=Z.astype(np.float32),
                        lane=lane.astype(np.float32), plat=sd_plateau(U, V).astype(np.float32),
                        play=sd_play(U, V).astype(np.float32), raised=raised(U, V).astype(np.float32))
    sc = scenery()
    arrs = {}
    for k, s in enumerate(sc["strips"]):
        for a in ("U", "V", "Z"):
            arrs[f"{k}_{a}"] = s[a].astype(np.float32)
    np.savez_compressed(out / "scenery.npz", **arrs)
    spec = dict(PPM=PPM, EL=EL, W=W, H=H, X0=X0, Y0=Y0, SUN=sun_vec(), things=lay["things"], CLIFF=CLIFF,
                camps=CAMPS, deck=DECK, zones={k: dict(code=v["code"], detail=v["detail"]) for k, v in Z_.ZONES.items()},
                strips=[dict(name=s["name"], zone=s["zone"]) for s in sc["strips"]],
                trees=sc["trees"], clouds=sc["clouds"], cloud_layers=cloud_layers(), strip_w=STRIP_W)
    (out / "scene3d.json").write_text(json.dumps(spec))
    return lay


if __name__ == "__main__":
    import sys
    lay = export(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/arena_work"))
    from collections import Counter
    print(Counter(t["kind"] for t in lay["things"]))
