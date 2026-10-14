"""Queries on the exported level (art/level.json), the same code as web/level.js: where an agent may stand, paths
(A* / Dijkstra on the 0.25 m nav with clearance), line of sight and shots, moving a circle through the colliders.

    from arena.game import Level
    lv = Level(json.load(open("arena/art/level.json")))
    p = lv.find_path((-18.0, 0.5, 0), (0.0, -2.2, 0), r=0.5)    # (u, v, layer): layer 0 the height field, 1 the deck
    lv.los((-18, 0.5, 0), (0, -2.2, 0))                          # eye to eye (rules.eye_height over each floor)
    unit = dict(u=-18.0, v=0.5, layer=0, r=0.5); lv.move(unit, 0.2, 0.0)

A position is (u, v, layer). Layer 0 is the height field (its level is 1, the terrace, where the floor is higher than
rules.high_ground_z, else 0, the ground); layer 1 is the bridge deck (level 2).
"""
from __future__ import annotations

import base64
import heapq
import math

import numpy as np

R2 = math.sqrt(2.0)
NB8 = [(0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0), (1, 1, R2), (1, -1, R2), (-1, 1, R2), (-1, -1, R2)]
BUCKET = 2.0


def _arr(s, dt):
    return np.frombuffer(base64.b64decode(s), dt)


class Level:
    def __init__(self, L: dict):
        self.L = L
        R = L["rules"]
        self.step, self.agent_h, self.eye, self.chest = R["max_step"], R["agent_height"], R["eye_height"], R["chest_height"]
        self.high = R["high_ground_z"]
        n = L["nav"]
        self.nu, self.nv, self.cell, self.u0, self.v0 = n["nu"], n["nv"], n["cell"], n["u0"], n["v0"]
        self.N = self.nu * self.nv
        q = n["clear_q"]
        self.clear = [_arr(n["hf"]["clear"], np.uint8).astype(np.float64) * q,
                      _arr(n["deck"]["clear"], np.uint8).astype(np.float64) * q]
        self.surf = [_arr(n["hf"]["surf"], np.uint8), _arr(n["deck"]["surf"], np.uint8)]
        self.z = _arr(n["hf"]["z_cm"], np.int16).astype(np.float64) / 100.0
        dk = n["deck"]
        self.dk = dk
        self.ramp_bit = n["surfaces"]["ramp_bit"]
        self.speed = {int(k): n["surfaces"]["speed"][v] for k, v in n["surfaces"]["legend"].items()}
        self.links = {}
        for lk in n["links"]:
            for a, b in lk.get("pairs", []):
                self.links.setdefault(a, []).append(self.N + b)
                self.links.setdefault(self.N + b, []).append(a)
        self.shapes = L["colliders"]["shapes"]
        self.bu0, self.bv0 = self.u0 - 8.0, self.v0 - 8.0
        self.bnu = int(math.ceil((self.nu * self.cell + 16.0) / BUCKET))
        self.bnv = int(math.ceil((self.nv * self.cell + 16.0) / BUCKET))
        self.buckets = [[] for _ in range(self.bnu * self.bnv)]
        for k, s in enumerate(self.shapes):
            x0, y0, x1, y1 = bbox(s)
            for bi in range(self._bi(y0, self.bv0, self.bnv), self._bi(y1, self.bv0, self.bnv) + 1):
                for bj in range(self._bi(x0, self.bu0, self.bnu), self._bi(x1, self.bu0, self.bnu) + 1):
                    self.buckets[bi * self.bnu + bj].append(k)

    @staticmethod
    def _bi(x, x0, n):
        return min(n - 1, max(0, int(math.floor((x - x0) / BUCKET))))

    # ------------------------------------------------------------ the floor
    def deck_z(self, v):
        dk = self.dk
        t = min(1.0, max(0.0, (v - dk["v0"]) / (dk["v1"] - dk["v0"])))
        return dk["z0"] + (dk["z1"] - dk["z0"]) * t

    def hf_z(self, u, v):
        fi = (v - self.v0) / self.cell - 0.5
        fj = (u - self.u0) / self.cell - 0.5
        i = min(self.nv - 2, max(0, int(math.floor(fi))))
        j = min(self.nu - 2, max(0, int(math.floor(fj))))
        a = min(1.0, max(0.0, fi - i)); b = min(1.0, max(0.0, fj - j))
        k = i * self.nu + j
        z = self.z
        return (z[k] * (1 - a) * (1 - b) + z[k + self.nu] * a * (1 - b) + z[k + 1] * (1 - a) * b
                + z[k + self.nu + 1] * a * b)

    def floor_z(self, u, v, layer):
        return self.deck_z(v) if layer == 1 else self.hf_z(u, v)

    def level_of(self, u, v, layer):
        return 2 if layer == 1 else int(self.hf_z(u, v) >= self.high)

    def in_deck(self, u, v):
        dk = self.dk
        return abs(u) <= dk["half_width"] and dk["v0"] <= v <= dk["v1"]

    def cell_of(self, u, v):
        i = int(math.floor((v - self.v0) / self.cell)); j = int(math.floor((u - self.u0) / self.cell))
        if i < 0 or j < 0 or i >= self.nv or j >= self.nu:
            return -1
        return i * self.nu + j

    def centre(self, k):
        i, j = divmod(k % self.N, self.nu)
        return self.u0 + (j + 0.5) * self.cell, self.v0 + (i + 0.5) * self.cell

    def node_z(self, node):
        u, v = self.centre(node)
        return self.deck_z(v) if node >= self.N else self.z[node]

    def clear_at(self, u, v, layer):
        """bilinear clearance (m) at a point"""
        c = self.clear[layer]
        fi = (v - self.v0) / self.cell - 0.5
        fj = (u - self.u0) / self.cell - 0.5
        i = int(math.floor(fi)); j = int(math.floor(fj))
        if i < 0 or j < 0 or i >= self.nv - 1 or j >= self.nu - 1:
            return 0.0
        a = fi - i; b = fj - j
        k = i * self.nu + j
        return (c[k] * (1 - a) * (1 - b) + c[k + self.nu] * a * (1 - b) + c[k + 1] * (1 - a) * b
                + c[k + self.nu + 1] * a * b)

    def snap(self, u, v, layer, r, reach=1.5):
        """the nearest node (cell) where an agent of radius r may stand, or -1"""
        k0 = self.cell_of(u, v)
        if k0 < 0:
            return -1
        i0, j0 = divmod(k0, self.nu)
        c = self.clear[layer]
        best, bd = -1, 1e9
        n = int(math.ceil(reach / self.cell))
        for i in range(max(0, i0 - n), min(self.nv, i0 + n + 1)):
            for j in range(max(0, j0 - n), min(self.nu, j0 + n + 1)):
                k = i * self.nu + j
                if c[k] < r:
                    continue
                cu, cv = self.u0 + (j + 0.5) * self.cell, self.v0 + (i + 0.5) * self.cell
                d = (cu - u) ** 2 + (cv - v) ** 2
                if d < bd:
                    best, bd = k, d
        return -1 if best < 0 else best + layer * self.N

    # ------------------------------------------------------------ the graph
    def neighbours(self, node, r):
        """(node, cost m) of every step an agent of radius r can take from a node"""
        layer = 1 if node >= self.N else 0
        k = node - layer * self.N
        i, j = divmod(k, self.nu)
        c, z = self.clear[layer], self.node_z(node)
        hf = layer == 0
        out = []
        for di, dj, w in NB8:
            ii, jj = i + di, j + dj
            if ii < 0 or jj < 0 or ii >= self.nv or jj >= self.nu:
                continue
            kk = ii * self.nu + jj
            if c[kk] < r:
                continue
            if di and dj and (c[i * self.nu + jj] < r or c[ii * self.nu + j] < r):
                continue
            z2 = self.z[kk] if hf else self.deck_z(self.v0 + (ii + 0.5) * self.cell)
            if abs(z2 - z) > self.step:
                continue
            if hf and (z >= self.high) != (z2 >= self.high) and not (
                    self.surf[0][k] & self.ramp_bit and self.surf[0][kk] & self.ramp_bit):
                continue
            out.append((kk + layer * self.N, w * self.cell))
        for nb in self.links.get(node, ()):
            l2 = 1 if nb >= self.N else 0
            if self.clear[l2][nb - l2 * self.N] >= r:
                a, b = self.centre(node), self.centre(nb)
                out.append((nb, math.hypot(a[0] - b[0], a[1] - b[1])))
        return out

    def field(self, starts, r):
        """Dijkstra from start nodes: grid distance (m) to every node (inf where unreachable)"""
        dist = np.full(2 * self.N, np.inf)
        h = []
        for s in starts:
            if s >= 0:
                dist[s] = 0.0
                h.append((0.0, s))
        heapq.heapify(h)
        while h:
            d, n = heapq.heappop(h)
            if d > dist[n]:
                continue
            for m, w in self.neighbours(n, r):
                nd = d + w
                if nd < dist[m]:
                    dist[m] = nd
                    heapq.heappush(h, (nd, m))
        return dist

    def descend(self, dist, node, r):
        """the grid path from a node back down a Dijkstra field to its start"""
        out = [node]
        while dist[node] > 0:
            best, bd = -1, dist[node]
            for m, w in self.neighbours(node, r):
                if dist[m] + w <= bd + 1e-9 and dist[m] < dist[node]:
                    best, bd = m, dist[m] + w
            if best < 0:
                return None
            node = best
            out.append(node)
        return out[::-1]

    def astar(self, s, g, r):
        if s < 0 or g < 0:
            return None
        gu, gv = self.centre(g)
        H = lambda n: (lambda a, b: (max(a, b) + (R2 - 1) * min(a, b)))(*map(abs, (self.centre(n)[0] - gu,
                                                                              self.centre(n)[1] - gv)))
        best = {s: 0.0}
        prev = {s: -1}
        h = [(H(s), 0.0, s)]
        while h:
            f, d, n = heapq.heappop(h)
            if n == g:
                path = [n]
                while prev[path[-1]] >= 0:
                    path.append(prev[path[-1]])
                return path[::-1]
            if d > best.get(n, 1e18):
                continue
            for m, w in self.neighbours(n, r):
                nd = d + w
                if nd < best.get(m, 1e18) - 1e-12:
                    best[m] = nd
                    prev[m] = n
                    heapq.heappush(h, (nd + H(m), nd, m))
        return None

    def walk_line(self, a, b, layer, r):
        """can an agent of radius r walk straight from a to b (u, v) on a layer: clearance, steps, ramps"""
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(math.ceil(L / 0.1)))
        zp, lp, rp = None, None, None
        for k in range(n + 1):
            t = k / n
            u, v = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            if self.clear_at(u, v, layer) < r:
                return False
            z = self.floor_z(u, v, layer)
            if layer == 0:
                kk = self.cell_of(u, v)
                lv, rm = z >= self.high, bool(self.surf[0][kk] & self.ramp_bit)
                if lp is not None and lv != lp and not (rm and rp):
                    return False
                lp, rp = lv, rm
            if zp is not None and abs(z - zp) > self.step:
                return False
            zp = z
        return True

    def smooth(self, nodes, r, start=None, end=None):
        """string-pull a grid path: points (u, v, z, layer)"""
        pts = [(self.centre(n)[0], self.centre(n)[1], 1 if n >= self.N else 0) for n in nodes]
        if start is not None and start[2] == pts[0][2] and self.walk_line(start[:2], pts[0][:2], start[2], r):
            pts[0] = tuple(start)
        if end is not None and end[2] == pts[-1][2] and self.walk_line(pts[-1][:2], end[:2], end[2], r):
            pts[-1] = tuple(end)
        out = [pts[0]]
        i = 0
        while i < len(pts) - 1:
            j = i + 1
            k = i + 2
            while k < len(pts) and all(p[2] == pts[i][2] for p in pts[i:k + 1]) and \
                    self.walk_line(pts[i][:2], pts[k][:2], pts[i][2], r):
                j = k
                k += 1
            out.append(pts[j])
            i = j
        return [(u, v, self.floor_z(u, v, ly), ly) for u, v, ly in out]

    @staticmethod
    def length(points):
        return sum(math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2)
                   for a, b in zip(points, points[1:]))

    def find_path(self, a, b, r=0.5):
        """a, b = (u, v, layer). {points: [(u, v, z, layer)], length: m (smoothed, 3D), grid: m} or None"""
        s, g = self.snap(*a, r), self.snap(*b, r)
        nodes = self.astar(s, g, r)
        if nodes is None:
            return None
        pts = self.smooth(nodes, r, a, b)
        grid = sum(math.hypot(*(np.subtract(self.centre(p), self.centre(q)))) for p, q in zip(nodes, nodes[1:]))
        return dict(points=pts, length=self.length(pts), grid=grid, nodes=nodes)

    # ------------------------------------------------------------ line of sight
    def los(self, a, b, mode="sight"):
        """a, b = (u, v, layer): eye to eye ("sight") or chest to chest ("shot") over each one's floor"""
        h = self.eye if mode == "sight" else self.chest
        A = (a[0], a[1], self.floor_z(a[0], a[1], a[2]) + h)
        B = (b[0], b[1], self.floor_z(b[0], b[1], b[2]) + h)
        return self.clear_line(A, B, mode)

    def clear_line(self, A, B, mode="sight"):
        """is the 3D segment A -> B (u, v, z) free of the terrain and of every shape flagged for `mode`"""
        du, dv, dz = B[0] - A[0], B[1] - A[1], B[2] - A[2]
        L = math.hypot(du, dv)
        n = max(1, int(math.ceil(L / 0.25)))
        for k in range(n + 1):                                   # the terrain (the height field)
            t = k / n
            if t * L < 0.35 or (1 - t) * L < 0.35:
                continue
            u, v = A[0] + du * t, A[1] + dv * t
            if A[2] + dz * t < self.hf_z(u, v) - 0.05:
                return False
        seen = set()
        x0, x1 = min(A[0], B[0]), max(A[0], B[0])
        y0, y1 = min(A[1], B[1]), max(A[1], B[1])
        for bi in range(self._bi(y0, self.bv0, self.bnv), self._bi(y1, self.bv0, self.bnv) + 1):
            for bj in range(self._bi(x0, self.bu0, self.bnu), self._bi(x1, self.bu0, self.bnu) + 1):
                for k in self.buckets[bi * self.bnu + bj]:
                    if k in seen:
                        continue
                    seen.add(k)
                    s = self.shapes[k]
                    if not s[mode] or not seg_hits(s, A, B):
                        continue
                    return False
        return True

    # ------------------------------------------------------------ moving a unit
    def near(self, u, v, rad):
        seen = set()
        for bi in range(self._bi(v - rad, self.bv0, self.bnv), self._bi(v + rad, self.bv0, self.bnv) + 1):
            for bj in range(self._bi(u - rad, self.bu0, self.bnu), self._bi(u + rad, self.bu0, self.bnu) + 1):
                for k in self.buckets[bi * self.bnu + bj]:
                    if k not in seen:
                        seen.add(k)
                        yield self.shapes[k]

    def blocks(self, s, z):
        return s["move"] and s["z1"] > z + self.step and s["z0"] < z + self.agent_h

    def penetration(self, u, v, layer, r):
        """the deepest overlap (m) of a circle with the colliders at a spot (0 = free)"""
        z = self.floor_z(u, v, layer)
        worst = 0.0
        for s in self.near(u, v, r + 0.1):
            if self.blocks(s, z):
                worst = max(worst, r - dist(s, u, v))
        return worst

    def switch(self, pu, pv, u, v, ly):
        """the layer after a step from (pu, pv) to (u, v): onto the deck off a landing (never from below), off it at
        its ends"""
        if ly == 0 and self.in_deck(u, v) and self.hf_z(u, v) < self.deck_z(v) - 0.6 \
                and self.hf_z(pu, pv) > self.deck_z(pv) - 0.6:
            return 1
        if ly == 1 and not (self.dk["v0"] <= v <= self.dk["v1"]):
            return 0
        return ly

    def move(self, unit, du, dv):
        """slide a unit {u, v, layer, r} by (du, dv) through the colliders; it changes level on and off the deck's
        ends. Returns the unit (moved in place)."""
        r = unit["r"]
        L = math.hypot(du, dv)
        n = max(1, int(math.ceil(L / (0.5 * r))))
        for _ in range(n):
            pu, pv, ly0 = unit["u"], unit["v"], unit["layer"]
            u, v = pu + du / n, pv + dv / n
            ly = self.switch(pu, pv, u, v, ly0)
            for _it in range(4):
                z = self.floor_z(u, v, ly)
                pushed = False
                for s in self.near(u, v, r + 0.1):
                    if not self.blocks(s, z):
                        continue
                    d, nu_, nv_ = push(s, u, v, pu, pv)
                    if d < r:
                        u += nu_ * (r - d + 1e-4); v += nv_ * (r - d + 1e-4)
                        pushed = True
                if not pushed:
                    break
            ly = self.switch(pu, pv, u, v, ly0)
            if self.penetration(u, v, ly, r) > 2e-3:
                break                                             # wedged: stay
            unit["u"], unit["v"], unit["layer"] = u, v, ly
        unit["z"] = self.floor_z(unit["u"], unit["v"], unit["layer"])
        return unit


# ---------------------------------------------------------------- shape geometry (level.js has the same)
def bbox(s):
    if s["shape"] == "circle":
        return s["u"] - s["r"], s["v"] - s["r"], s["u"] + s["r"], s["v"] + s["r"]
    if s["shape"] == "box":
        c, sn = abs(math.cos(s["a"])), abs(math.sin(s["a"]))
        eu, ev = s["hu"] * c + s["hv"] * sn, s["hu"] * sn + s["hv"] * c
        return s["u"] - eu, s["v"] - ev, s["u"] + eu, s["v"] + ev
    t = s["t"]
    return min(s["u0"], s["u1"]) - t, min(s["v0"], s["v1"]) - t, max(s["u0"], s["u1"]) + t, max(s["v0"], s["v1"]) + t


def dist(s, u, v):
    return push(s, u, v, u, v)[0]


def push(s, u, v, pu, pv):
    """(distance from (u, v) to the shape, unit normal pointing away from it); (pu, pv) = where the mover came from,
    to pick the side of a zero-thickness wall"""
    if s["shape"] == "circle":
        du, dv = u - s["u"], v - s["v"]
        L = math.hypot(du, dv)
        if L < 1e-9:
            du, dv, L = pu - s["u"], pv - s["v"], max(1e-9, math.hypot(pu - s["u"], pv - s["v"]))
        return L - s["r"], du / L, dv / L
    if s["shape"] == "box":
        c, sn = math.cos(s["a"]), math.sin(s["a"])
        du, dv = u - s["u"], v - s["v"]
        x, y = du * c + dv * sn, -du * sn + dv * c
        qx, qy = abs(x) - s["hu"], abs(y) - s["hv"]
        if qx > 0 or qy > 0:
            ox, oy = max(qx, 0.0) * math.copysign(1, x), max(qy, 0.0) * math.copysign(1, y)
            L = math.hypot(ox, oy)
            nx, ny = ox / L, oy / L
            d = L
        else:                                                     # inside: out along the nearest face
            if qx > qy:
                nx, ny, d = math.copysign(1, x), 0.0, qx
            else:
                nx, ny, d = 0.0, math.copysign(1, y), qy
        return d, nx * c - ny * sn, nx * sn + ny * c
    au, av, bu, bv = s["u0"], s["v0"], s["u1"], s["v1"]
    eu, ev = bu - au, bv - av
    L2 = eu * eu + ev * ev
    t = 0.0 if L2 < 1e-12 else min(1.0, max(0.0, ((u - au) * eu + (v - av) * ev) / L2))
    cu, cv = au + t * eu, av + t * ev
    du, dv = u - cu, v - cv
    L = math.hypot(du, dv)
    if L < 1e-6:                                                  # on the line: back to the side it came from
        nu_, nv_ = -ev, eu
        if (pu - cu) * nu_ + (pv - cv) * nv_ < 0:
            nu_, nv_ = -nu_, -nv_
        n = max(1e-9, math.hypot(nu_, nv_))
        return -s["t"], nu_ / n, nv_ / n
    return L - s["t"], du / L, dv / L


def seg_hits(s, A, B):
    """does the 3D segment A -> B pass through the shape's prism (its footprint over z0..z1); a segment shape is
    taken as its box (round ends squared)"""
    du, dv = B[0] - A[0], B[1] - A[1]
    if s["shape"] == "circle":
        fu, fv = A[0] - s["u"], A[1] - s["v"]
        a = du * du + dv * dv
        b = 2 * (fu * du + fv * dv)
        c = fu * fu + fv * fv - s["r"] * s["r"]
        if a < 1e-12:
            if c > 0:
                return False
            t0, t1 = 0.0, 1.0
        else:
            disc = b * b - 4 * a * c
            if disc < 0:
                return False
            sq = math.sqrt(disc)
            t0, t1 = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
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
        t0, t1 = -1e18, 1e18
        for o, d, h in ((ox, dx, hu), (oy, dy, hv)):
            if abs(d) < 1e-12:
                if abs(o) > h:
                    return False
                continue
            ta, tb = (-h - o) / d, (h - o) / d
            if ta > tb:
                ta, tb = tb, ta
            t0, t1 = max(t0, ta), min(t1, tb)
            if t0 > t1:
                return False
    t0, t1 = max(t0, 0.0), min(t1, 1.0)
    if t0 > t1:
        return False
    za, zb = A[2] + (B[2] - A[2]) * t0, A[2] + (B[2] - A[2]) * t1
    return max(za, zb) >= s["z0"] and min(za, zb) <= s["z1"]
