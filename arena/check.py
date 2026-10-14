"""Validate the level for a game: `python3 -m arena check` (a short report; exit 1 on a failure).

- reachability: every walkable cell is reached from both spawns, per agent radius (no islands but the pockets the
  export filled in and listed in nav.pockets)
- objectives: both spawns reach every objective's capture circle
- fairness: path lengths from each spawn to each objective and to the other side's heart, against the mirrored
  route from the other spawn (the map is mirrored: the difference must stay within FAIR_M or FAIR_PCT)
- spawn safety: no spawn point sees a spawn point of the other side
- routes: the narrowest gap on each lane (the widest disc that gets through, as a width)
- stuck: every nav step is free in the continuous colliders (sweep), random walkers never wedge or end where the nav
  cannot take them home, and walkers following A* paths arrive
- art: the colliders sit on the painted props (projected samples land on the occluder cut-outs), the terrace walls'
  feet on the masonry
"""
from __future__ import annotations

import heapq
import json
import math
import random
from pathlib import Path

import numpy as np

from . import game

HERE = Path(__file__).resolve().parent
FAIR_M, FAIR_PCT = 0.75, 0.02
LANE_HALF = 5.0


def _bind():
    """the active map's art folder, title and the collider kinds that are drawn props (the art agreement)"""
    global ART, TITLE, ART_KINDS
    from .maps import active
    M = active()
    ART, TITLE = M.ART, M.TITLE
    ART_KINDS = set(M.level.ART_KINDS)


def load(art: Path = None) -> game.Level:
    return game.Level(json.loads((Path(art or ART) / "level.json").read_text()))


def origin_node(lv, side, r):
    u, v, _ = lv.L["zones"]["spawns"][side]["origin"]
    return lv.snap(u, v, 0, r)


def reach(lv, r, fields=None):
    """walkable cells at r not reached from either spawn, grouped into islands"""
    fields = fields or {}
    out = {}
    for side in ("west", "east"):
        d = fields.get((side, r))
        if d is None:
            d = lv.field([origin_node(lv, side, r)], r)
            fields[(side, r)] = d
        walk = np.concatenate([lv.clear[0] >= r, lv.clear[1] >= r])
        out[side] = np.nonzero(walk & ~np.isfinite(d))[0]
    return out, fields


def islands(lv, nodes):
    """group unreached nodes by 8-adjacency: [(area m2, u, v)]"""
    left = set(int(n) for n in nodes)
    out = []
    while left:
        s = left.pop()
        comp, stack = [s], [s]
        while stack:
            n = stack.pop()
            ly = n // lv.N
            i, j = divmod(n % lv.N, lv.nu)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    m = ly * lv.N + (i + di) * lv.nu + (j + dj)
                    if m in left:
                        left.remove(m); comp.append(m); stack.append(m)
        cs = [lv.centre(n) for n in comp]
        out.append((len(comp) * lv.cell ** 2, float(np.mean([c[0] for c in cs])), float(np.mean([c[1] for c in cs]))))
    return sorted(out, reverse=True)


def to_target(lv, dist, obj, r):
    """the nearest node inside an objective's capture circle (on its level) and its grid distance"""
    best, bd = -1, math.inf
    rr = obj["capture_r"]
    for i in range(int((obj["v"] - rr - lv.v0) / lv.cell), int((obj["v"] + rr - lv.v0) / lv.cell) + 1):
        for j in range(int((obj["u"] - rr - lv.u0) / lv.cell), int((obj["u"] + rr - lv.u0) / lv.cell) + 1):
            if not (0 <= i < lv.nv and 0 <= j < lv.nu):
                continue
            k = i * lv.nu + j
            u, v = lv.centre(k)
            if (u - obj["u"]) ** 2 + (v - obj["v"]) ** 2 > rr * rr or lv.level_of(u, v, 0) != obj["level"]:
                continue
            if dist[k] < bd:
                best, bd = k, dist[k]
    return best, bd


def path_len(lv, dist, node, r, start):
    nodes = lv.descend(dist, node, r)
    if nodes is None:
        return None, None
    s = lv.centre(nodes[0])
    pts = lv.smooth(nodes, r, (start[0], start[1], 0) if start else None, None)
    return lv.length(pts), pts


def mirror(lv, obj):
    for o in lv.L["zones"]["objectives"] + lv.L["zones"].get("targets", []):
        if abs(o["u"] + obj["u"]) < 0.3 and abs(o["v"] - obj["v"]) < 0.3 and o["kind"] == obj["kind"]:
            return o
    return None


def fairness(lv, r, fields):
    """objectives, and a kill map's fairness targets (zones.targets: places both sides race to), against their mirror"""
    rows = []
    objs = lv.L["zones"]["objectives"] + lv.L["zones"].get("targets", [])
    for o in objs:
        m = mirror(lv, o)
        if m is None:
            continue
        res = {}
        for side, target in (("west", o), ("east", m)):
            d = fields[(side, r)]
            node, gd = to_target(lv, d, target, r)
            org = lv.L["zones"]["spawns"][side]["origin"]
            ln, pts = path_len(lv, d, node, r, org) if node >= 0 else (None, None)
            res[side] = (ln, gd, pts)
        label = o["id"] if o["side"] is None else o["kind"] + (" own" if o["side"] == "west" else " enemy")
        a, b = res["west"][0], res["east"][0]
        diff = abs(a - b) if a is not None and b is not None else math.inf
        ok = diff <= max(FAIR_M, FAIR_PCT * max(a or 0, b or 0))
        rows.append(dict(target=label, west=a, east=b, diff=diff, ok=ok, west_pts=res["west"][2], east_pts=res["east"][2]))
    # the same objective from both sides (each side's own/enemy pairs are mirrored above; the Stones are shared)
    return rows


def spawn_los(lv):
    sp = lv.L["zones"]["spawns"]
    seen = []
    for a in sp["west"]["points"] + [sp["west"]["origin"]]:
        for b in sp["east"]["points"] + [sp["east"]["origin"]]:
            if lv.los((a[0], a[1], 0), (b[0], b[1], 0)):
                seen.append((a, b))
    return seen


def widest(lv, a, b, poly, r0=0.05):
    """maximin path from node a to node b inside the lane's corridor: the largest clearance it can keep"""
    def near_lane(n):
        u, v = lv.centre(n)
        best = 1e9
        for (p, q) in zip(poly, poly[1:]):
            du, dv = q[0] - p[0], q[1] - p[1]
            t = max(0.0, min(1.0, ((u - p[0]) * du + (v - p[1]) * dv) / max(du * du + dv * dv, 1e-9)))
            best = min(best, math.hypot(u - p[0] - t * du, v - p[1] - t * dv))
        return best <= LANE_HALF
    cl = lambda n: lv.clear[n // lv.N][n % lv.N]
    best = {a: cl(a)}
    h = [(-cl(a), a)]
    where = {a: a}
    while h:
        nb, n = heapq.heappop(h)
        nb = -nb
        if n == b:
            return nb, where[n]
        if nb < best.get(n, -1):
            continue
        for m, _ in lv.neighbours(n, r0):
            if not near_lane(m):
                continue
            w = min(nb, cl(m))
            if w > best.get(m, -1):
                best[m] = w
                where[m] = m if cl(m) <= nb else where[n]
                heapq.heappush(h, (-w, m))
    return 0.0, None


def roomiest(lv, u, v, layer, reach=2.0):
    """the cell with the most clearance within reach of a waypoint (so a lane's ends do not set its gap)"""
    best, bc = -1, -1.0
    n = int(reach / lv.cell)
    k0 = lv.cell_of(u, v)
    i0, j0 = divmod(k0, lv.nu)
    for i in range(i0 - n, i0 + n + 1):
        for j in range(j0 - n, j0 + n + 1):
            k = i * lv.nu + j
            cu, cv = lv.centre(k)
            if (cu - u) ** 2 + (cv - v) ** 2 <= reach * reach and lv.clear[layer][k] > bc:
                best, bc = k, lv.clear[layer][k]
    return best + layer * lv.N


def routes(lv):
    out = {}
    for name, pts in lv.L["lanes"].items():
        poly = [(p[0], p[1]) for p in pts]
        nodes = [roomiest(lv, p[0], p[1], 1 if p[2] == 2 else 0) for p in pts]
        worst, at = math.inf, None
        for a, b in zip(nodes, nodes[1:]):
            w, n = widest(lv, a, b, poly)
            if w < worst:
                worst, at = w, n
        out[name] = (2 * worst, lv.centre(at) if at is not None else None)
    return out


def sweep(lv, r=0.5):
    """every nav step an agent of radius r may take is free in the continuous colliders at its midpoint"""
    bad, n = [], 0
    for layer in (0, 1):
        c = lv.clear[layer]
        idx = np.nonzero(c >= r)[0]
        for k in idx:
            node = int(k) + layer * lv.N
            for m, _ in lv.neighbours(node, r):
                if m < node or (m >= lv.N) != (node >= lv.N):
                    continue
                a, b = lv.centre(node), lv.centre(m)
                u, v = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                n += 1
                p = lv.penetration(u, v, layer, r)
                if p > 0.03:
                    bad.append((u, v, layer, p))
    return n, bad


def walkers(lv, n=120, steps=250, r=0.5, seed=1, fields=None):
    """random walkers: they must never wedge, and must always stand where the nav can take them home"""
    rng = random.Random(seed)
    home = fields.get(("west", r)) if fields else None
    if home is None:
        home = lv.field([origin_node(lv, "west", r)], r)
    cand = [k for k in np.nonzero(np.isfinite(home[:lv.N]))[0]]
    wedged, lost = [], []
    for w in range(n):
        k = int(rng.choice(cand))
        u, v = lv.centre(k)
        unit = dict(u=u, v=v, layer=0, r=r)
        a = rng.uniform(0, math.tau)
        for s in range(steps):
            a += rng.gauss(0, 0.5)
            lv.move(unit, 0.15 * math.cos(a), 0.15 * math.sin(a))
            if s % 50 == 49 or s == steps - 1:
                if lv.penetration(unit["u"], unit["v"], unit["layer"], r) > 0.01:
                    wedged.append(dict(unit))
                    break
                sn = lv.snap(unit["u"], unit["v"], unit["layer"], r, reach=0.6)
                if sn < 0 or not np.isfinite(home[sn]):
                    lost.append(dict(unit))
                    break
        moved = False
        for k2 in range(16):
            t = dict(unit)
            lv.move(t, 0.2 * math.cos(k2 * math.pi / 8), 0.2 * math.sin(k2 * math.pi / 8))
            if math.hypot(t["u"] - unit["u"], t["v"] - unit["v"]) > 0.05:
                moved = True
                break
        if not moved:
            wedged.append(dict(unit))
    return wedged, lost


def followers(lv, n=24, r=0.5, seed=2, fields=None):
    """units following A* paths between random spots with the continuous mover: they must arrive"""
    rng = random.Random(seed)
    home = fields.get(("west", r)) if fields else lv.field([origin_node(lv, "west", r)], r)
    cand = [int(k) for k in np.nonzero(np.isfinite(home))[0]]
    fails, lens = [], []
    for _ in range(n):
        a, b = rng.choice(cand), rng.choice(cand)
        (ua, va), (ub, vb) = lv.centre(a), lv.centre(b)
        la, lb = a // lv.N, b // lv.N
        p = lv.find_path((ua, va, la), (ub, vb, lb), r)
        if p is None:
            fails.append(("no path", (ua, va, la), (ub, vb, lb)))
            continue
        lens.append(p["length"])
        unit = dict(u=ua, v=va, layer=la, r=r)
        ok = follow(lv, unit, p["points"])
        if not ok:
            fails.append(("stuck", (ua, va, la), (ub, vb, lb), (unit["u"], unit["v"])))
    return fails, lens


def follow(lv, unit, pts, speed=0.2, patience=60):
    """walk a unit along path points; False when it stops making progress"""
    i, still = 1, 0
    best = math.inf
    for _ in range(4000):
        if i >= len(pts):
            return True
        tu, tv = pts[i][0], pts[i][1]
        du, dv = tu - unit["u"], tv - unit["v"]
        d = math.hypot(du, dv)
        if d < 0.12:
            i += 1; best = math.inf; still = 0
            continue
        s = min(speed, d)
        lv.move(unit, du / d * s, dv / d * s)
        d2 = math.hypot(tu - unit["u"], tv - unit["v"])
        if d2 < best - 0.01:
            best, still = d2, 0
        else:
            still += 1
            if still > patience:
                return False
    return False


# ---------------------------------------------------------------- the art agreement
def occ_mask(art: Path = None):
    art = art or ART
    from PIL import Image
    occ = json.loads((Path(art) / "occ.json").read_text())
    atlas = np.asarray(Image.open(Path(art) / "occ.png"))
    L = json.loads((Path(art) / "level.json").read_text())
    W, H = L["projection"]["map_w"], L["projection"]["map_h"]
    m = np.zeros((H, W), bool)
    for o in occ:
        a = atlas[o["ay"]:o["ay"] + o["h"], o["ax"]:o["ax"] + o["w"], 3] > 0
        m[o["y"]:o["y"] + o["h"], o["x"]:o["x"] + o["w"]] |= a
    return m


def art_samples(lv, art: Path = None):
    art = art or ART
    """per collider: the share of its projected samples that land on a drawn prop (an occluder cut-out)"""
    from PIL import Image
    m = occ_mask(art)
    zones = np.asarray(Image.open(Path(art) / "zones.png"))
    pr = lv.L["projection"]
    H, W = m.shape
    proj = lambda u, v, z: (pr["x0"] + u * pr["ppm"], pr["y0"] - (v * pr["sin_el"] + z * pr["cos_el"]) * pr["ppm"])
    res = []
    for s in lv.shapes:
        if s["kind"] not in ART_KINDS:
            continue
        if s["shape"] == "circle":
            pts = [(s["u"], s["v"])] + [(s["u"] + 0.6 * s["r"] * math.cos(a), s["v"] + 0.6 * s["r"] * math.sin(a))
                                         for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
        elif s["shape"] == "box":
            c, sn = math.cos(s["a"]), math.sin(s["a"])
            pts = [(s["u"], s["v"])] + [(s["u"] + c * x * s["hu"] * 0.6 - sn * y * s["hv"] * 0.6,
                                         s["v"] + sn * x * s["hu"] * 0.6 + c * y * s["hv"] * 0.6)
                                        for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        else:
            pts = [(s["u0"] + (s["u1"] - s["u0"]) * t, s["v0"] + (s["v1"] - s["v0"]) * t) for t in (0.2, 0.5, 0.8)]
        lo = s["z0"] + 0.35
        hi = min(s["z1"], lo + 2.0)
        zs = [lo + (hi - lo) * f for f in (0.25, 0.6)] if hi > lo else [s["z0"] + 0.5 * (s["z1"] - s["z0"])]
        hits = tot = 0
        for (u, v) in pts:
            for z in zs:
                x, y = proj(u, v, z)
                xi, yi = int(round(x)), int(round(y))
                if 0 <= xi < W and 0 <= yi < H:
                    tot += 1
                    win = m[max(0, yi - 1):yi + 2, max(0, xi - 1):xi + 2]
                    hits += bool(win.any())
        if tot == 0:
            continue                                            # off the picture (the ring past the frame's edge)
        res.append(dict(id=s["id"], kind=s["kind"], share=hits / max(tot, 1), u=s.get("u", s.get("u0")),
                        v=s.get("v", s.get("v0"))))
    # the terrace walls: 1.2 m up the face, just past the foot, is the masonry (frame), not the field
    walls = [s for s in lv.shapes if s["kind"] == "wall" and s["z1"] - s["z0"] > 2.0]
    wh = nwall = 0
    for s in walls:
        u, v = (s["u0"] + s["u1"]) / 2, (s["v0"] + s["v1"]) / 2
        eu, ev = s["u1"] - s["u0"], s["v1"] - s["v0"]
        n = math.hypot(eu, ev)
        nu_, nv_ = ev / n, -eu / n
        if lv.clear_at(u + 0.3 * nu_, v + 0.3 * nv_, 0) > lv.clear_at(u - 0.3 * nu_, v - 0.3 * nv_, 0):
            nu_, nv_ = -nu_, -nv_
        if nv_ < 0.3:
            continue                                            # a face turned away from the camera: not drawn
        nwall += 1
        x, y = proj(u + 0.3 * nu_, v + 0.3 * nv_, s["z0"] + 0.3 + 1.2)
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < W and 0 <= yi < H:
            wh += zones[yi, xi] in (2, 3)
    return res, (wh, nwall)


# ---------------------------------------------------------------- the report
def run(art: Path = None, quick: bool = False, out=print) -> int:
    art = art or ART
    lv = load(art)
    fails = []
    lines = []
    say = lines.append
    say(f"{TITLE} level check (level.json v{lv.L['version']}, nav {lv.nu} x {lv.nv} cells of {lv.cell} m, "
        f"{len(lv.shapes)} collider shapes)")
    radii = lv.L["rules"]["radii"]
    fields = {}
    say("\nREACHABILITY (from both spawns)")
    for r in radii:
        un, fields = reach(lv, r, fields)
        walk = int((lv.clear[0] >= r).sum() + (lv.clear[1] >= r).sum())
        isl = islands(lv, sorted(set(un["west"]) | set(un["east"])))
        say(f"  r {r}: {walk * lv.cell ** 2:7.1f} m2 walkable, unreached {len(un['west']) * lv.cell ** 2:.2f} m2 from the "
            f"west, {len(un['east']) * lv.cell ** 2:.2f} m2 from the east" +
            ("" if not isl else "; islands " + ", ".join(f"{a:.2f} m2 at ({u:.1f}, {v:.1f})" for a, u, v in isl[:4])))
        decl = [a for a in lv.L["nav"].get("alcoves", []) if a["r"] == r]
        undeclared = [x for x in isl if not any(math.hypot(x[1] - a["u"], x[2] - a["v"]) < 2.0 for a in decl)]
        if undeclared:
            fails.append(f"r {r}: {len(undeclared)} undeclared islands")
        elif isl:
            say(f"    (all declared alcoves: " + ", ".join(a["name"] for a in decl) + ")")
    pk = lv.L["nav"]["pockets"]
    say(f"  pockets filled in by the export (cut off, < 2 m2): {len(pk)}" +
        ("" if not pk else " (" + ", ".join(f"r {p['r']}: {p['area_m2']} m2 at ({p['u']}, {p['v']})" for p in pk) + ")"))
    say("\nOBJECTIVES AND FAIRNESS (smoothed path length in m from each spawn's origin; mirrored targets)")
    fair_rows = {}
    for r in ([0.5] if quick else radii):
        rows = fairness(lv, r, fields)
        fair_rows[r] = rows
        for row in rows:
            if row["west"] is None or row["east"] is None:
                fails.append(f"r {r}: {row['target']} unreachable")
            elif not row["ok"]:
                fails.append(f"r {r}: {row['target']} unfair by {row['diff']:.2f} m")
        say(f"  r {r}: " + "; ".join(f"{x['target']} W {x['west']:.2f} / E {x['east']:.2f} (diff {x['diff']:.2f})"
                                     for x in rows if x['west'] is not None and x['east'] is not None))
    say("\nSPAWN SAFETY")
    seen = spawn_los(lv)
    say(f"  spawn point pairs in line of sight across the map: {len(seen)}")
    if seen:
        fails.append(f"{len(seen)} spawn pairs see each other")
    say("\nCHOKEPOINTS (wall-to-wall width on the cross line) and ROUTES (narrowest gap: the widest disc that passes)")
    say("  " + "; ".join(f"{c['name']} {c['width']:.2f} m" for c in lv.L["zones"]["chokepoints"]))
    rt = routes(lv)
    say("  " + "; ".join(f"{k} {w:.2f} m at ({p[0]:.1f}, {p[1]:.1f})" for k, (w, p) in rt.items() if p))
    say("\nSTUCK TESTS (r 0.5)")
    n, bad = sweep(lv, 0.5)
    say(f"  sweep: {n} nav steps, {len(bad)} with a midpoint inside a collider" +
        ("" if not bad else f" (worst {max(b[3] for b in bad):.3f} m)"))
    if bad:
        fails.append(f"sweep: {len(bad)} nav steps cut a collider")
    wedged, lost = walkers(lv, *((40, 150) if quick else (200, 300)), fields=fields)
    say(f"  random walkers: {40 if quick else 200} x {150 if quick else 300} steps of 0.15 m: {len(wedged)} wedged, "
        f"{len(lost)} where the nav cannot take them home")
    if wedged or lost:
        fails.append(f"walkers: {len(wedged)} wedged, {len(lost)} lost")
    ff, lens = followers(lv, 6 if quick else 30, fields=fields)
    say(f"  path followers: {len(lens)} paths ({min(lens):.1f}-{max(lens):.1f} m) walked with the continuous mover, "
        f"{len(ff)} failed")
    if ff:
        fails.append(f"followers: {len(ff)} failed")
    say("\nART AGREEMENT")
    res, (wh, wn) = art_samples(lv, art)
    by = {}
    for x in res:
        by.setdefault(x["kind"], []).append(x["share"])
    say("  share of collider samples on drawn props: " + ", ".join(f"{k} {np.mean(v):.0%}" for k, v in sorted(by.items())))
    poor = [x for x in res if x["share"] < 0.5]
    say(f"  colliders under half on their prop: {len(poor)}" +
        ("" if not poor else " (" + ", ".join(f"{x['kind']} at ({x['u']:.1f}, {x['v']:.1f}) {x['share']:.0%}"
                                              for x in poor[:6]) + ")"))
    say(f"  terrace walls whose face reads as masonry 1.2 m up: {wh} / {wn}")
    if poor:
        fails.append(f"{len(poor)} colliders off their props")
    say("\n" + ("PASS" if not fails else "FAIL\n  " + "\n  ".join(fails)))
    out("\n".join(lines))
    run.last = dict(fair=fair_rows, routes=rt, fields=fields, lv=lv)
    return 1 if fails else 0


_bind()
