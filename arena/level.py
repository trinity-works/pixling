"""Hushfall Crossing as a game level: collision, navigation, line of sight and gameplay zones, built from the same place
data that drives the render (arena/place.py: the plan's signed distances, the terrain, layout() and the ruin).

Everything is in metres: u left -> right, v into the picture, z up (the projection is place.proj).

LEVELS   0 ground, 1 terrace (the ruin terrace, its ramps' upper halves, the overlook: z >= HIGH_Z), 2 the bridge deck.
         Ground and terrace are one height field (they never overlap in plan; the ramps join them); the deck is a
         second layer over the corridor.
REGION   the walkable height field: inside the ledge (sd_play < -0.5), no slope over MAX_SLOPE, and no step over
         MAX_STEP within a band round every face: FOOT_BAND on the low side (the masonry stands proud of the face),
         LIP_BAND on the high side (the kerb and cornice on the lip). Its outline, traced at 0.125 m and simplified to
         3 cm, becomes the WALLS: `wall` (a face rising: a cliff with no step-up, blocks sight), `lip` (a drop: a hard
         edge, units never fall) and `bound` (the forest shelf / out of bounds, same height).
SHAPES   every prop as circles (trunks, posts, menhirs' halves... ), boxes (tents, palisade runs, the towers' cage,
         the hearts, toppled blocks, crates) and segments with a half thickness (kerbs, rails, corbels, walls). Each
         has a level, an absolute z range and three flags: move, sight, shot.
RULE     an obstacle constrains an agent standing on a floor at z when its z range overlaps
         [z + MAX_STEP, z + AGENT_H] (so the deck's rails never touch units in the corridor, the deck is a ceiling
         2.9 m over the corridor floor, a 0.3 m kerb could be stepped over if it were not on a lip).
NAV      a 0.25 m grid over the height field and one over the deck, with the clearance (distance to the nearest
         obstacle under the rule above) per cell: an agent of radius r may stand where clearance >= r. Ramps are
         flagged cells (the only place ground and terrace cells touch); the deck's two ends are explicit links.
LOS      eye EYE above the floor (sight), chest CHEST (shots): a 3D segment against the terrain and the shapes that
         carry the flag. High ground sees over what is lower than its eye.

`build()` returns the dict that paint.level_json writes into art/level.json (with the legacy v3 keys kept).
arena/game.py (and web/level.js, the same code in JS) answers queries on it: paths, LOS, moving a unit.
arena/check.py validates it.
"""
from __future__ import annotations

import base64
import math
import random

import numpy as np

from . import place as P

VERSION = 4
NAV = 0.25                       # nav cell (m)
FINE = NAV / 2                   # the region and its outline are traced on this lattice
MAX_STEP = 0.35                  # highest step an agent climbs (m)
MAX_SLOPE_DEG = 35.0             # steepest walkable slope (the ramps are 23)
AGENT_H = 1.8                    # the agent's height for the overhead rule (a person is 1.7)
EYE = 1.6                        # eye height above the floor (sight)
CHEST = 1.1                      # projectile height above the floor (shots)
RADII = (0.3, 0.5, 0.8)          # agent radius classes the nav is checked for
HIGH_Z = 1.5                     # height-field cells this high are the terrace level
SIGHT_MIN = 1.0                  # an obstacle lower than this over its floor never blocks sight
SHOT_MIN = 0.6                   # ... nor shots
FOOT_BAND = 0.65                 # the masonry's reach out from a face's foot (m)
LIP_BAND = 0.35                  # the lip's kerb / cornice band on top (m)
CLEAR_Q = 0.02                   # clearance is stored in steps of 2 cm (uint8) ...
CLEAR_MAX = 5.0                  # ... up to 5 m
KILL_Z = -3.0                    # only if your game knocks units over the lip: below this they are lost
RAMP_BIT = 8
POCKET_MAX = 2.0                 # cut-off pockets smaller than this (m^2) are filled in for that radius, and listed
R2 = math.sqrt(2.0)
NO_DECK = dict(z0=0.0, z1=0.0, v0=0.0, v1=1.0, half_width=-1.0)    # a map without a second layer: an empty deck


def _bind():
    """read the active map's level hooks (arena/maps/<name>/level.py) and the nav lattice's size"""
    global H, NU, NV, SURF, SPEED, ALCOVES
    from .maps import active
    H = active().level
    NU = int(round((P.GU1 - P.GU0) / NAV))
    NV = int(round((P.GV1 - P.GV0) / NAV))
    SURF, SPEED, ALCOVES = H.SURF, H.SPEED, H.ALCOVES


def has_deck():
    return bool(getattr(H, "DECK", False))


def deck_z(v):
    if has_deck():
        return H.deck_z(v)
    return np.zeros(np.shape(v))


def deck_half():
    return H.DECK_HALF if has_deck() else NO_DECK["half_width"]


def bl2uv(dx, dy):
    """a Blender (world grid x, y) vector -> (u, v)"""
    return (dx - dy) / R2, (dx + dy) / R2


_bind()


# ---------------------------------------------------------------- the walkable height field
def _disk(a, R, op):
    k = int(math.floor(R / FINE + 1e-9))
    pad = np.pad(a, k, mode="edge")
    out = a.copy()
    for di in range(-k, k + 1):
        for dj in range(-k, k + 1):
            if di * di + dj * dj > (R / FINE) ** 2 + 1e-9:
                continue
            out = op(out, pad[k + di:k + di + a.shape[0], k + dj:k + dj + a.shape[1]])
    return out


def region():
    """the fine lattice (0.125 m; nav cell (i, j) is fine point (2i+1, 2j+1)): U, V, Z and the walkable field f
    (> 0 walkable; its zero line is the outline)"""
    fu = P.GU0 + FINE * np.arange(2 * NU + 1)
    fv = P.GV0 + FINE * np.arange(2 * NV + 1)
    U, V = np.meshgrid(fu, fv)
    Z = P.terrain(U, V)
    gy, gx = np.gradient(Z, FINE)
    slope = np.hypot(gx, gy)
    f = np.minimum.reduce([
        -(P.sd_play(U, V) + 0.5),                                   # the ledge's lip and the forest shelf
        (Z + MAX_STEP) - _disk(Z, FOOT_BAND, np.maximum),          # the foot of a face, the masonry proud of it
        _disk(Z, LIP_BAND, np.minimum) - (Z - MAX_STEP),           # the lip of a drop, the kerb on it
        (math.tan(math.radians(MAX_SLOPE_DEG)) - slope) * 2.0,
    ])
    # the map's own additions (Hushfall: the bridge's landings stay walkable, so units step on and off the deck)
    if hasattr(H, "region_extra"):
        f = H.region_extra(U, V, Z, f)
    return U, V, Z, _despeckle(f, U[0], V[:, 0])


def _despeckle(f, xs, ys, area=1.0):
    """specks of the outline smaller than `area` m^2 (a bump in the corridor, a dimple on the snow) take the sign of
    what surrounds them"""
    for lp in contours(f, xs, ys):
        p = np.asarray(lp)
        a = 0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))
        if a >= area:
            continue
        j0, j1 = np.searchsorted(xs, p[:, 0].min()) - 2, np.searchsorted(xs, p[:, 0].max()) + 2
        i0, i1 = np.searchsorted(ys, p[:, 1].min()) - 2, np.searchsorted(ys, p[:, 1].max()) + 2
        if i0 < 0 or j0 < 0 or i1 >= f.shape[0] or j1 >= f.shape[1]:
            continue
        sub = f[i0:i1 + 1, j0:j1 + 1]
        ring = np.concatenate([sub[0], sub[-1], sub[:, 0], sub[:, -1]])
        if (ring > 0).all():
            sub[sub <= 0] = 0.01
        elif (ring <= 0).all():
            sub[sub > 0] = -0.01
    return f


# marching squares: corners a (i,j) b (i,j+1) c (i+1,j+1) d (i+1,j); edges 0 a-b, 1 b-c, 2 c-d, 3 d-a
_MS = {1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)], 6: [(0, 2)], 7: [(3, 2)], 8: [(2, 3)], 9: [(0, 2)],
       11: [(1, 2)], 12: [(3, 1)], 13: [(0, 1)], 14: [(3, 0)]}


def contours(f, xs, ys):
    """closed loops of f = 0 as lists of (u, v)"""
    F = np.pad(f, 1, constant_values=-1.0)
    dx = xs[1] - xs[0]
    xs = np.concatenate([[xs[0] - dx], xs, [xs[-1] + dx]])
    ys = np.concatenate([[ys[0] - dx], ys, [ys[-1] + dx]])
    b = F > 0
    case = b[:-1, :-1] * 1 + b[:-1, 1:] * 2 + b[1:, 1:] * 4 + b[1:, :-1] * 8
    pts = {}

    def point(key):
        if key not in pts:
            kind, i, j = key
            if kind == "h":
                f0, f1 = F[i, j], F[i, j + 1]
                t = f0 / (f0 - f1)
                pts[key] = (xs[j] + t * (xs[j + 1] - xs[j]), ys[i])
            else:
                f0, f1 = F[i, j], F[i + 1, j]
                t = f0 / (f0 - f1)
                pts[key] = (xs[j], ys[i] + t * (ys[i + 1] - ys[i]))
        return key

    adj = {}
    for i, j in zip(*np.nonzero((case > 0) & (case < 15))):
        c = int(case[i, j])
        ek = [("h", i, j), ("v", i, j + 1), ("h", i + 1, j), ("v", i, j)]
        if c in (5, 10):
            centre = F[i, j] + F[i, j + 1] + F[i + 1, j + 1] + F[i + 1, j] > 0
            pairs = ([(0, 1), (2, 3)] if centre else [(3, 0), (1, 2)]) if c == 5 else \
                    ([(3, 0), (1, 2)] if centre else [(0, 1), (2, 3)])
        else:
            pairs = _MS[c]
        for a_, b_ in pairs:
            ka, kb = point(ek[a_]), point(ek[b_])
            adj.setdefault(ka, []).append(kb)
            adj.setdefault(kb, []).append(ka)
    loops, seen = [], set()
    for start in adj:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [k for k in adj[cur] if k != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            if cur == start:
                break
            if cur in seen:
                break
            seen.add(cur)
            loop.append(cur)
        loops.append([pts[k] for k in loop])
    return loops


def _dp(pts, tol):
    """Douglas-Peucker on an open polyline (array n x 2)"""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = b - a
    L = np.hypot(*ab)
    if L < 1e-9:
        d = np.hypot(*(pts - a).T)
    else:
        d = np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / L
    k = int(np.argmax(d))
    if d[k] <= tol:
        return np.array([a, b])
    return np.vstack([_dp(pts[:k + 1], tol)[:-1], _dp(pts[k:], tol)])


def simplify(loop, tol=0.03):
    p = np.asarray(loop, np.float64)
    if len(p) < 8:
        return p
    k = int(np.argmax(np.hypot(*(p - p[0]).T)))          # split the ring at its far point
    a = _dp(p[:k + 1], tol)
    b = _dp(np.vstack([p[k:], p[:1]]), tol)
    return np.vstack([a[:-1], b[:-1]])


def walls(U, V, Z, f):
    """the outline of the walkable height field as segments, each classed by what lies past it"""
    xs, ys = U[0], V[:, 0]
    loops = [simplify(lp) for lp in contours(f, xs, ys) if len(lp) > 6]
    segs = []
    for lp in loops:
        nxt = np.roll(lp, -1, 0)
        for a, b in zip(lp, nxt):
            if np.hypot(*(b - a)) < 1e-6:
                continue
            segs.append((a[0], a[1], b[0], b[1]))
    S = np.array(segs)
    mid = (S[:, :2] + S[:, 2:]) / 2
    t = S[:, 2:] - S[:, :2]
    t /= np.hypot(*t.T)[:, None]
    n = np.stack([t[:, 1], -t[:, 0]], 1)
    # the outward normal: f falls along it
    fi = lambda p: _bilin(f, xs, ys, p[:, 0], p[:, 1])
    flip = fi(mid + 0.06 * n) > fi(mid - 0.06 * n)
    n[flip] *= -1
    zin = P.terrain(*(mid - 0.2 * n).T)
    outs = np.stack([P.terrain(*(mid + d * n).T) for d in np.arange(0.1, 1.31, 0.15)], 1)
    zo_max, zo_min = outs.max(1), outs.min(1)
    out = []
    for k in range(len(S)):
        u0, v0, u1, v1 = S[k]
        mu, mv = mid[k]
        if hasattr(H, "wall_skip") and H.wall_skip(mu, mv, zin[k]):
            continue                                  # (Hushfall) a landing's edge under the deck: the deck carries on
        if zo_max[k] > zin[k] + MAX_STEP:
            kind, z0, z1 = "wall", zin[k] - 0.3, max(zo_max[k], zin[k] + 0.5)
        elif zo_min[k] < zin[k] - MAX_STEP:
            kind, z0, z1 = "lip", zo_min[k], zin[k] + 1.0
        else:
            kind, z0, z1 = "bound", zin[k] - 0.5, zin[k] + 3.0
        out.append(dict(kind=kind, shape="seg", u0=u0, v0=v0, u1=u1, v1=v1, t=0.0, level=int(zin[k] >= HIGH_Z),
                        z0=float(z0), z1=float(z1), move=True, sight=kind == "wall", shot=kind == "wall"))
    return out


def _bilin(a, xs, ys, u, v):
    """bilinear sample of a lattice array at points"""
    fx = np.clip((np.asarray(u) - xs[0]) / (xs[1] - xs[0]), 0, len(xs) - 1.001)
    fy = np.clip((np.asarray(v) - ys[0]) / (ys[1] - ys[0]), 0, len(ys) - 1.001)
    j, i = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - j, fy - i
    return (a[i, j] * (1 - tx) * (1 - ty) + a[i, j + 1] * tx * (1 - ty) + a[i + 1, j] * (1 - tx) * ty
            + a[i + 1, j + 1] * tx * ty)


# ---------------------------------------------------------------- the props' shapes (from the same data Blender builds)
def _g(u, v):
    return float(P.terrain(np.array(u), np.array(v)))


def props(lay):
    """collision shapes of everything placed, in metres: the map's hooks (H.props) describe each prop with these
    builders, matching its Blender geometry"""
    out = []

    def add(kind, shape, g, z0, z1, solid=True, opaque=True, **geo):
        h = z1 - g
        lvl = geo.pop("level", int(g >= HIGH_Z))
        out.append(dict(kind=kind, shape=shape, level=lvl, z0=float(z0), z1=float(z1), move=True,
                        sight=bool(opaque and h >= SIGHT_MIN), shot=bool(solid and h >= SHOT_MIN), **geo))

    def box(kind, u, v, hu, hv, ang, g, z0, z1, **kw):
        add(kind, "box", g, z0, z1, u=u, v=v, hu=hu, hv=hv, a=ang, **kw)

    def circ(kind, u, v, r, g, z0, z1, **kw):
        add(kind, "circle", g, z0, z1, u=u, v=v, r=r, **kw)

    def seg(kind, a, b, t, g, z0, z1, **kw):
        add(kind, "seg", g, z0, z1, u0=a[0], v0=a[1], u1=b[0], v1=b[1], t=t, **kw)

    H.props(lay, box, circ, seg, HIGH_Z)
    return out


# ---------------------------------------------------------------- distances (vectorised; game.py / level.js mirror)
def shape_dist(s, u, v):
    """distance (m) from points to a shape's footprint (0 inside)"""
    if s["shape"] == "circle":
        return np.maximum(np.hypot(u - s["u"], v - s["v"]) - s["r"], 0.0)
    if s["shape"] == "box":
        c, sn = math.cos(s["a"]), math.sin(s["a"])
        du, dv = u - s["u"], v - s["v"]
        x, y = du * c + dv * sn, -du * sn + dv * c
        return np.hypot(np.maximum(np.abs(x) - s["hu"], 0), np.maximum(np.abs(y) - s["hv"], 0))
    au, av, bu, bv = s["u0"], s["v0"], s["u1"], s["v1"]
    eu, ev = bu - au, bv - av
    L2 = eu * eu + ev * ev
    t = np.clip(((u - au) * eu + (v - av) * ev) / max(L2, 1e-12), 0, 1)
    return np.maximum(np.hypot(u - au - t * eu, v - av - t * ev) - s["t"], 0.0)


def shape_bbox(s):
    if s["shape"] == "circle":
        return s["u"] - s["r"], s["v"] - s["r"], s["u"] + s["r"], s["v"] + s["r"]
    if s["shape"] == "box":
        c, sn = abs(math.cos(s["a"])), abs(math.sin(s["a"]))
        eu, ev = s["hu"] * c + s["hv"] * sn, s["hu"] * sn + s["hv"] * c
        return s["u"] - eu, s["v"] - ev, s["u"] + eu, s["v"] + ev
    t = s["t"]
    return min(s["u0"], s["u1"]) - t, min(s["v0"], s["v1"]) - t, max(s["u0"], s["u1"]) + t, max(s["v0"], s["v1"]) + t


def constrains(s, z):
    """the vertical rule: does the obstacle touch an agent standing on a floor at z"""
    return (s["z1"] > z + MAX_STEP) & (s["z0"] < z + AGENT_H)


def clearance(obst, us, vs, Z, mask, cap=CLEAR_MAX):
    """per lattice point (us x vs, floor heights Z): distance to the nearest obstacle under the vertical rule"""
    du = us[1] - us[0]
    out = np.full(Z.shape, cap, np.float64)
    for s in obst:
        if not s["move"]:
            continue
        x0, y0, x1, y1 = shape_bbox(s)
        j0 = max(0, int(math.floor((x0 - cap - us[0]) / du)))
        j1 = min(len(us), int(math.ceil((x1 + cap - us[0]) / du)) + 1)
        i0 = max(0, int(math.floor((y0 - cap - vs[0]) / du)))
        i1 = min(len(vs), int(math.ceil((y1 + cap - vs[0]) / du)) + 1)
        if j0 >= j1 or i0 >= i1:
            continue
        m = mask[i0:i1, j0:j1]
        if not m.any():
            continue
        UU, VV = np.meshgrid(us[j0:j1], vs[i0:i1])
        d = shape_dist(s, UU, VV)
        d = np.where(constrains(s, Z[i0:i1, j0:j1]), d, cap)
        out[i0:i1, j0:j1] = np.minimum(out[i0:i1, j0:j1], d)
    out[~mask] = 0.0
    return out


# ---------------------------------------------------------------- the graph (game.py has the same rules)
NB8 = [(0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0), (1, 1, R2), (1, -1, R2), (-1, 1, R2), (-1, -1, R2)]


def components(walk, Zc, surf, deck_walk, deck_links):
    """connected components of the nav graph (height field + deck + links) over boolean walk masks. Returns labels
    (2, NV, NU) int, -1 = not walkable"""
    lab = np.full((2, NV, NU), -1, np.int32)
    zl = [Zc, np.broadcast_to(deck_z(P.GV0 + NAV * (np.arange(NV) + 0.5))[:, None], (NV, NU))]
    masks = [walk, deck_walk]
    link = {}
    for a, b in deck_links:
        link.setdefault((0,) + a, []).append((1,) + b)
        link.setdefault((1,) + b, []).append((0,) + a)
    n = 0
    for L0 in (0, 1):
        for i0, j0 in zip(*np.nonzero(masks[L0])):
            if lab[L0, i0, j0] >= 0:
                continue
            stack = [(L0, i0, j0)]
            lab[L0, i0, j0] = n
            while stack:
                L, i, j = stack.pop()
                z = zl[L][i, j]
                for di, dj, _ in NB8:
                    ii, jj = i + di, j + dj
                    if not (0 <= ii < NV and 0 <= jj < NU) or not masks[L][ii, jj] or lab[L, ii, jj] >= 0:
                        continue
                    if di and dj and not (masks[L][i, jj] and masks[L][ii, j]):
                        continue
                    if abs(zl[L][ii, jj] - z) > MAX_STEP:
                        continue
                    if L == 0 and (z >= HIGH_Z) != (zl[0][ii, jj] >= HIGH_Z) and not (
                            surf[i, j] & RAMP_BIT and surf[ii, jj] & RAMP_BIT):
                        continue
                    lab[L, ii, jj] = n
                    stack.append((L, ii, jj))
                for (L2, ii, jj) in link.get((L, i, j), []):
                    if masks[L2][ii, jj] and lab[L2, ii, jj] < 0:
                        lab[L2, ii, jj] = n
                        stack.append((L2, ii, jj))
            n += 1
    return lab


# ---------------------------------------------------------------- build
def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def build(seed: int = None, quiet: bool = True) -> dict:
    lay = P.layout(P.SEED if seed is None else seed)
    U, V, Zf, f = region()
    wl = walls(U, V, Zf, f)
    shapes = props(lay)
    obst = wl + shapes
    for i, s in enumerate(obst):
        s["id"] = i
        for k in list(s):
            if isinstance(s[k], float):
                s[k] = round(s[k], 3)
    us = P.GU0 + NAV * (np.arange(NU) + 0.5)
    vs = P.GV0 + NAV * (np.arange(NV) + 0.5)
    Zc = Zf[1::2, 1::2]
    inside = f[1::2, 1::2] > 0
    clear = clearance(obst, us, vs, Zc, inside)
    # the deck (a second layer, when the map has one)
    UU, VV = np.meshgrid(us, vs)
    dmask = H.deck_mask(UU, VV) if has_deck() else np.zeros(UU.shape, bool)
    Zd = deck_z(VV)
    dclear = clearance(obst, us, vs, Zd, dmask)
    # the links at the deck's ends: a deck cell and a landing cell at the same or a neighbouring spot, close in height
    links = []
    for i, j in zip(*np.nonzero(dmask)):
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                ii, jj = i + di, j + dj
                if 0 <= ii < NV and 0 <= jj < NU and inside[ii, jj] and Zc[ii, jj] > H.ZD_LANDING \
                        and abs(Zc[ii, jj] - Zd[i, j]) <= MAX_STEP and (di, dj) in ((0, 0), (-1, 0), (1, 0)):
                    links.append(((ii, jj), (i, j)))
    # surfaces (the map's: snow and lanes, grass and dirt ...), | RAMP_BIT on ramps
    surf, ramps = H.surfaces(UU, VV, wl, inside, Zc, shape_dist, SURF, RAMP_BIT)
    surf[~inside] = 0
    dsurf = np.where(dmask, SURF.get("deck", 0), 0).astype(np.uint8)
    # pockets: walkable at a radius but cut off from the spawns at it: filled in when small (the clearance clamped just
    # under that radius), declared as alcoves when larger (ALCOVES: room for small units only)
    sp = {s: _spawn_origin(s) for s in H.SIDES}
    pockets = []
    for r in RADII:
        lab = components(inside & (clear >= r), Zc, surf, dmask & (dclear >= r), links)
        main = lab[(0,) + _cell(*sp["west"][:2])]
        for c in np.unique(lab[lab >= 0]):
            if c == main:
                continue
            m = lab == c
            area = float(m.sum() * NAV * NAV)
            ii, jj = np.nonzero(m[0] | m[1])
            cu, cv = float(us[jj].mean()), float(vs[ii].mean())
            if area <= POCKET_MAX:
                pockets.append(dict(r=r, u=round(cu, 2), v=round(cv, 2), area_m2=round(area, 2)))
                lo = 0.0 if r == RADII[0] else r - CLEAR_Q
                clear[m[0]] = np.minimum(clear[m[0]], lo)
                dclear[m[1]] = np.minimum(dclear[m[1]], lo)
    q = lambda c: np.clip(np.floor(c / CLEAR_Q + 1e-6), 0, 255).astype(np.uint8)
    zcm = np.clip(np.round(Zc * 100), -32000, 32000).astype(np.int16)
    nav = dict(
        cell=NAV, u0=P.GU0, v0=P.GV0, nu=NU, nv=NV,
        about="two layers on one lattice: 'hf' (the height field: ground and terrace) and 'deck'. Cell (i, j) is "
              "centred at (u0 + (j + 0.5) * cell, v0 + (i + 0.5) * cell); arrays are row-major (i * nu + j), base64. "
              "clear: uint8 clearance in steps of clear_q m (0 = not walkable): an agent of radius r may stand where "
              "clear * clear_q >= r. z_cm: int16 ground height (cm) of every cell, walkable or not (LOS uses it as "
              "the terrain). surf: uint8 surface (legend) | 8 on ramps. A hf cell's level is 1 where z >= "
              "high_ground_z, else 0; ground and terrace cells touch only on ramps. The deck's floor is deck.z(v).",
        clear_q=CLEAR_Q, clear_max=CLEAR_MAX,
        hf=dict(clear=b64(q(clear)), surf=b64(surf), z_cm=b64(zcm)),
        deck=dict(clear=b64(q(dclear)), surf=b64(dsurf), **_deck_info()),
        surfaces=dict(legend={str(v): k for k, v in SURF.items()}, ramp_bit=RAMP_BIT, speed=SPEED, note=H.SURF_NOTE),
        links=ramps + _deck_links(links, vs),
        pockets=pockets,
        alcoves=[dict(r=r, name=n, u=u, v=v) for r, lst in ALCOVES.items() for n, u, v in lst],
    )
    return dict(lay=lay, shapes=obst, nav=nav, arrays=dict(U=U, V=V, Zf=Zf, f=f, clear=clear, dclear=dclear,
                                                           surf=surf, inside=inside, Zc=Zc, dmask=dmask, links=links),
                spawn_origin=sp)


def _deck_info():
    if not has_deck():
        return dict(NO_DECK, z="no deck on this map: layer 1 is empty")
    D = H.D
    return dict(z0=D["z0"], z1=D["z1"], v0=D["v0"], v1=D["v1"], half_width=round(H.DECK_HALF, 3),
                z="z0 + (z1 - z0) * clamp((v - v0) / (v1 - v0), 0, 1)")


def _deck_links(links, vs):
    if not has_deck():
        return []
    D = H.D
    return [dict(name=n, kind="deck end", levels=[1, 2], edge=[[-D["walk"], vv], [D["walk"], vv]],
                 pairs=[[int(a[0] * NU + a[1]), int(b[0] * NU + b[1])] for a, b in links
                        if (vs[b[0]] < (D["v0"] + D["v1"]) / 2) == (vv < (D["v0"] + D["v1"]) / 2)])
            for n, vv in (("bridge south end (terrace)", D["v0"]), ("bridge north end (overlook)", D["v1"]))]


def _cell(u, v):
    return int((v - P.GV0) // NAV), int((u - P.GU0) // NAV)


def _spawn_origin(side):
    return H.spawn_origin(side)


# ---------------------------------------------------------------- measured gameplay data
def _clean(o):
    if isinstance(o, dict):
        return {k: (v if k == "projection" else _clean(v)) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return round(float(o), 3)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def exact_clear(shapes, u, v, z, f_at=None):
    """exact distance (m) from points (floor z) to the nearest obstacle under the vertical rule"""
    u, v, z = (np.atleast_1d(np.asarray(x, np.float64)) for x in (u, v, z))
    out = np.full(u.shape, CLEAR_MAX)
    for s in shapes:
        if not s["move"]:
            continue
        out = np.minimum(out, np.where(constrains(s, z), shape_dist(s, u, v), CLEAR_MAX))
    return out


def free_span(b, centre, direction, layer, reach=7.0):
    """wall-to-wall width (m) of the free line through `centre` along `direction` on a layer"""
    A = b["arrays"]
    s = np.arange(-reach, reach + 1e-9, 0.02)
    du, dv = direction
    n = math.hypot(du, dv)
    u, v = centre[0] + s * du / n, centre[1] + s * dv / n
    if layer == 1:
        z = deck_z(v)
        inside = (np.abs(u) <= H.DECK_HALF) & (v >= H.D["v0"]) & (v <= H.D["v1"])
    else:
        z = P.terrain(u, v)
        inside = _bilin(A["f"], A["U"][0], A["V"][:, 0], u, v) > 0
    free = inside & (exact_clear(b["shapes"], u, v, z) > 0)
    c = len(s) // 2
    if not free[c]:
        return 0.0
    lo = c
    while lo > 0 and free[lo - 1]:
        lo -= 1
    hi = c
    while hi < len(s) - 1 and free[hi + 1]:
        hi += 1
    return float(s[hi] - s[lo] + 0.02)


def los_from(lv, A, Bs, mode="sight"):
    """batched game.Level.clear_line from one point A (u, v, z) to many Bs (n x 3): the same test, vectorised"""
    Bs = np.asarray(Bs, np.float64)
    out = np.ones(len(Bs), bool)
    du, dv, dz = Bs[:, 0] - A[0], Bs[:, 1] - A[1], Bs[:, 2] - A[2]
    L = np.hypot(du, dv)
    n = np.maximum(1, np.ceil(L / 0.25)).astype(int)
    K = int(n.max())
    k = np.arange(K + 1)[None, :]
    t = k / n[:, None]
    valid = (k <= n[:, None]) & (t * L[:, None] >= 0.35) & ((1 - t) * L[:, None] >= 0.35)
    uu, vv = A[0] + du[:, None] * t, A[1] + dv[:, None] * t
    zz = A[2] + dz[:, None] * t
    hz = _hf_bilin(lv, uu, vv)
    out &= ~np.any(valid & (zz < hz - 0.05), 1)
    for s in lv.shapes:
        if not s[mode]:
            continue
        hit = _seg_hits_many(s, A, Bs)
        out &= ~hit
    return out


def _hf_bilin(lv, u, v):
    fi = (v - lv.v0) / lv.cell - 0.5
    fj = (u - lv.u0) / lv.cell - 0.5
    i = np.clip(np.floor(fi).astype(int), 0, lv.nv - 2)
    j = np.clip(np.floor(fj).astype(int), 0, lv.nu - 2)
    a = np.clip(fi - i, 0, 1); bb = np.clip(fj - j, 0, 1)
    kk = i * lv.nu + j
    z = lv.z
    return (z[kk] * (1 - a) * (1 - bb) + z[kk + lv.nu] * a * (1 - bb) + z[kk + 1] * (1 - a) * bb
            + z[kk + lv.nu + 1] * a * bb)


def _seg_hits_many(s, A, Bs):
    du, dv = Bs[:, 0] - A[0], Bs[:, 1] - A[1]
    m = len(Bs)
    if s["shape"] == "circle":
        fu, fv = A[0] - s["u"], A[1] - s["v"]
        a = du * du + dv * dv
        b = 2 * (fu * du + fv * dv)
        c = fu * fu + fv * fv - s["r"] ** 2
        disc = b * b - 4 * a * c
        ok = disc >= 0
        sq = np.sqrt(np.maximum(disc, 0))
        a2 = np.where(a < 1e-12, 1.0, 2 * a)
        t0, t1 = (-b - sq) / a2, (-b + sq) / a2
        zero = a < 1e-12
        t0 = np.where(zero, 0.0, t0); t1 = np.where(zero, 1.0, t1)
        ok = np.where(zero, c <= 0, ok)
    else:
        if s["shape"] == "box":
            cu, cv, hu, hv, ang = s["u"], s["v"], s["hu"], s["hv"], s["a"]
        else:
            cu, cv = (s["u0"] + s["u1"]) / 2, (s["v0"] + s["v1"]) / 2
            ang = math.atan2(s["v1"] - s["v0"], s["u1"] - s["u0"])
            hu = math.hypot(s["u1"] - s["u0"], s["v1"] - s["v0"]) / 2 + s["t"]
            hv = max(s["t"], 1e-3)
        c, sn = math.cos(ang), math.sin(ang)
        ox, oy = (A[0] - cu) * c + (A[1] - cv) * sn, -(A[0] - cu) * sn + (A[1] - cv) * c
        dx, dy = du * c + dv * sn, -du * sn + dv * c
        t0, t1 = np.full(m, -1e18), np.full(m, 1e18)
        ok = np.ones(m, bool)
        for o, d, h in ((ox, dx, hu), (oy, dy, hv)):
            small = np.abs(d) < 1e-12
            ok &= ~(small & (abs(o) > h))
            dd = np.where(small, 1.0, d)
            ta, tb = (-h - o) / dd, (h - o) / dd
            lo, hi = np.minimum(ta, tb), np.maximum(ta, tb)
            t0 = np.where(small, t0, np.maximum(t0, lo))
            t1 = np.where(small, t1, np.minimum(t1, hi))
        ok &= t0 <= t1
    t0, t1 = np.maximum(t0, 0.0), np.minimum(t1, 1.0)
    ok &= t0 <= t1
    za, zb = A[2] + (Bs[:, 2] - A[2]) * t0, A[2] + (Bs[:, 2] - A[2]) * t1
    return ok & (np.maximum(za, zb) >= s["z0"]) & (np.minimum(za, zb) <= s["z1"])


def coarse_points(lv, size=2.0, r=0.3):
    """one representative standing spot per size x size m square per layer: the walkable cell nearest its centre"""
    pts = []
    n = int(round(size / lv.cell))
    for layer in (0, 1):
        c = lv.clear[layer].reshape(lv.nv, lv.nu)
        for i0 in range(0, lv.nv, n):
            for j0 in range(0, lv.nu, n):
                sub = c[i0:i0 + n, j0:j0 + n]
                ii, jj = np.nonzero(sub >= r)
                if not len(ii):
                    continue
                d = (ii - (n - 1) / 2) ** 2 + (jj - (n - 1) / 2) ** 2
                k = int(np.argmin(d))
                i, j = i0 + ii[k], j0 + jj[k]
                u, v = lv.u0 + (j + 0.5) * lv.cell, lv.v0 + (i + 0.5) * lv.cell
                pts.append((u, v, layer))
    return pts


def coarse_visibility(lv, size=2.0):
    pts = coarse_points(lv, size)
    E = np.array([(u, v, lv.floor_z(u, v, ly) + lv.eye) for u, v, ly in pts])
    n = len(pts)
    vis = np.zeros((n, n), bool)
    for i in range(n):
        vis[i, i:] = los_from(lv, E[i], E[i:])
    vis |= vis.T
    bits = np.packbits(vis.ravel())
    return dict(cell=size, eye=lv.eye, points=[[u, v, ly] for u, v, ly in pts], bits=b64(bits),
                about="pair (a, b) of `points` (u, v, layer) sees each other eye to eye when bit a * n + b of `bits` "
                      "(packbits, big-endian within a byte) is set; a coarse helper for AI (who can see this square), "
                      "the exact test is the LOS function"), vis


SPAWN_RINGS = ((2.4, 0.0), (3.6, 0.26))   # default; a map may set its own (H.SPAWN_RINGS)


def spawn_points(lv):
    """spawn spots round each side's spawn centre, mirrored west <-> east, each free for a 0.5 m unit"""
    cu, cv = H.spawn_centre()
    west, east = [], []
    for r, off in getattr(H, "SPAWN_RINGS", SPAWN_RINGS):
        for k in range(12):
            a = k / 12 * math.tau + off
            u, v = cu + r * math.cos(a), cv + r * 0.85 * math.sin(a)
            ok = all(lv.clear[0][lv.cell_of(x, v)] >= 0.5 and lv.penetration(x, v, 0, 0.5) == 0 for x in (u, -u))
            if ok:
                west.append([u, v, lv.hf_z(u, v)])
                east.append([-u, v, lv.hf_z(-u, v)])
    return dict(west=west, east=east)


def cover_spots(lv, shapes):
    """spots beside things that stop shots: where a unit of radius 0.5 can stand pressed to them. `facing` is the
    direction (degrees in u, v) from the spot to the cover, i.e. the side it protects; full >= 1.6 m over the floor,
    half >= 0.8 m (low rocks, blocks: shots at chest height pass over at range)"""
    out = []
    for s in shapes:
        if s["kind"] not in H.COVER_KINDS or not s["shot"]:
            continue
        if s["shape"] == "seg":
            continue
        cu, cv = s["u"], s["v"]
        g = s["z0"] + (0.3 if s["kind"] != "toppled block" else 0.3)
        for k in range(8):
            a = k * math.pi / 4
            ea, eb = math.cos(a), math.sin(a)
            rho = 0.1
            while dist_shape(s, cu + ea * rho, cv + eb * rho) < 0.55 and rho < 4:
                rho += 0.05
            u, v = cu + ea * rho, cv + eb * rho
            k_ = lv.cell_of(u, v)
            if k_ < 0 or lv.clear[0][k_] < 0.5 or lv.penetration(u, v, 0, 0.5) > 0:
                continue
            z = lv.hf_z(u, v)
            h = s["z1"] - z
            if h < 0.8:
                continue
            if any((u - o["u"]) ** 2 + (v - o["v"]) ** 2 < 0.8 ** 2 for o in out):
                continue
            out.append(dict(u=u, v=v, z=z, level=int(z >= HIGH_Z), facing=round(math.degrees(math.atan2(-eb, -ea)), 1),
                            height=h, kind="full" if h >= 1.6 else "half", of=s["kind"], shape=s["id"]))
    del g
    return out


def dist_shape(s, u, v):
    return float(shape_dist(s, np.array(u), np.array(v)))


def to_json(b) -> dict:
    """the level as data: art/level.json (version 4)"""
    from . import game
    lay, shapes, nav = b["lay"], b["shapes"], b["nav"]
    A = b["arrays"]
    rules = dict(
        units="metres; u left -> right, v into the picture, z up",
        max_step=MAX_STEP, max_slope_deg=MAX_SLOPE_DEG, agent_height=AGENT_H, eye_height=EYE, chest_height=CHEST,
        high_ground_z=HIGH_Z, radii=list(RADII), sight_min_height=SIGHT_MIN, shot_min_height=SHOT_MIN,
        obstacle_rule="an obstacle (a shape with move) constrains an agent standing on a floor at z when its z range "
                      "overlaps [z + max_step, z + agent_height]",
        bounds="hard walls: every edge of the walkable is a wall segment (wall: a face rising, no step-up; lip: a "
               "drop, units never fall; bound: out of bounds at the same height). There is no kill plane; if your "
               "game knocks units over the lip, treat a unit whose ground falls below kill_z as lost",
        kill_z=KILL_Z,
        sight="eye to eye: from eye_height over one floor to eye_height over the other; blocked by the terrain "
              "(nav z_cm as a height field) and by every shape with sight whose prism the segment passes through. "
              "High ground sees over whatever is lower than its eye",
        shots="the same from chest_height, against the shapes with shot",
    )
    levels = H.levels(A, HIGH_Z)
    L = dict(name=P.NAME, version=VERSION, rules=rules, levels=levels,
             colliders=dict(about="shape: circle (u, v, r) | box (u, v, hu, hv half sizes, a = angle of its hu axis "
                                  "from +u toward +v, radians) | seg (u0, v0 to u1, v1, t = half thickness: a capsule). "
                                  "level, z0..z1 (absolute m), move / sight / shot. kind wall / lip / bound are the "
                                  "edges of the walkable height field",
                            shapes=shapes),
             nav=nav)
    lv = game.Level(_clean(L))
    # spawns, objectives, zones
    sp = spawn_points(lv)
    zones = {}
    zones["spawns"] = {}
    for side in ("west", "east"):
        area, safe = H.spawn_area(side)
        zones["spawns"][side] = dict(origin=list(b["spawn_origin"][side]), area=area, safe_radius=safe, points=sp[side])
    zones["objectives"] = H.objectives(lv, lay)
    for k, v in H.zone_extras(lv, lay).items():
        zones[k] = v
    zones["chokepoints"] = [dict(name=n, u=c[0], v=c[1], layer=ly, level=2 if ly else lv.level_of(c[0], c[1], 0),
                                 across=list(d), width=free_span(b, c, d, ly),
                                 abreast_r05=int(free_span(b, c, d, ly) // 1.0))
                            for n, c, d, ly in H.chokepoints()]
    zones["cover"] = cover_spots(lv, shapes)
    zones["surfaces"] = dict(speed=SPEED, legend=nav["surfaces"]["legend"], where="nav.hf.surf / nav.deck.surf")
    loops = [simplify(lp, 0.08) for lp in contours(A["f"], A["U"][0], A["V"][:, 0]) if len(lp) > 6]
    area = lambda p: 0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))
    outer = max(loops, key=area)
    zones["out_of_bounds"] = dict(rule="everything outside the walkable height field and the deck; walled, no kill "
                                       "plane (rules.kill_z if you add knockback)",
                                  outer=[[float(x), float(y)] for x, y in outer], kill_z=KILL_Z)
    vis, _ = coarse_visibility(lv)
    L.update(zones=zones, visibility=vis,
             los=dict(eye_height=EYE, chest_height=CHEST, terrain="nav.hf.z_cm (sampled every 0.25 m, 5 cm grace, "
                                                                  "0.35 m round each end ignored)",
                      shapes="colliders with sight (eye to eye) or shot (chest to chest); a seg is tested as its box"))
    L["projection"] = dict(ppm=P.PPM, el_deg=P.EL_DEG, sin_el=round(P.SE, 6), cos_el=round(P.CE, 6), map_w=P.W,
                           map_h=P.H, x0=P.X0, y0=P.Y0,
                           screen="sx = x0 + u * ppm;  sy = y0 - (v * sin_el + z * cos_el) * ppm",
                           depth="v * cos_el - z * sin_el (larger is further: draw far first)",
                           grid_xy="x = (u + v) / sqrt 2, y = (v - u) / sqrt 2 (buildings sit square to x, y)",
                           human_px=round(P.HUMAN * P.CE * P.PPM, 1))
    return _clean(L)


def legacy(L, b):
    """the v3 keys, rebuilt from the v4 data so they agree: grid (0.5 m kind + height), spawns, objectives,
    chokepoints, lanes, props, dimensions"""
    A = b["arrays"]
    Zf, f = A["Zf"], A["f"]
    us = P.GU0 + 0.5 * (np.arange(NU // 2) + 0.5)
    vs = P.GV0 + 0.5 * (np.arange(NV // 2) + 0.5)
    UU, VV = np.meshgrid(us, vs)
    Z = Zf[2::4, 2::4][:len(vs), :len(us)]
    inside = f[2::4, 2::4][:len(vs), :len(us)] > 0
    free = exact_clear(b["shapes"], UU.ravel(), VV.ravel(), Z.ravel()).reshape(UU.shape) > 0
    kind = np.where(inside & free, 1, 0).astype(np.uint8)
    kind[(kind == 1) & (P.lane_dist(UU, VV) < 1.2)] = 2
    hcm = np.round(Z * 100).astype(int)
    L["grid"] = dict(u0=P.GU0, v0=P.GV0, cell=0.5, nu=len(us), nv=len(vs), legend=dict(H.GRID_LEGEND),
                     rows="kind[i] is the row at v = v0 + (i + 0.5) * cell, one digit per cell from u0 (legacy v3; "
                          "the nav is the exact one)",
                     kind=["".join(str(int(k)) for k in row) for row in kind],
                     height_cm=[[int(x) for x in row] for row in hcm])
    L["high_ground_z"] = HIGH_Z
    L["spawns"] = {s: L["zones"]["spawns"][s]["points"] for s in ("west", "east")}
    L["objectives"] = [{k: o[k] for k in ("kind", "side", "u", "v", "z")} for o in L["zones"]["objectives"]]
    L["chokepoints"] = [dict(name=c["name"], u=c["u"], v=c["v"], width=c["width"], level=c["level"])
                        for c in L["zones"]["chokepoints"]]
    L["lanes"] = {k: [[u, v, 2 if lv else 0] for u, v, lv in pts] for k, pts in P.LANES.items()}
    things = b["lay"]["things"]
    L["props"] = [dict(kind=t["kind"], u=round(t["u"], 2), v=round(t["v"], 2), z=round(_g(t["u"], t["v"]), 2),
                       side=t.get("side")) for t in things if t["kind"] in H.LEGACY_PROPS]
    L["dimensions"] = P.DIMENSIONS
    L["occluders"] = H.OCCLUDERS_NOTE
    return _clean(L)


def export(seed: int = None):
    b = build(seed)
    return legacy(to_json(b), b), b
