"""First Snow: the reference scene. A snowy slope climbs to a road; a winding stair of stone slabs, roped off on both
sides, leads up to an old car parked with its lights on. Telephone poles carry sagging wires across the road, spruce
crowd the ridge, and the sun sets pink on the left.

World frame: metres, y up. The walk starts near the origin looking toward -z (uphill); +x is to the right.
`layout(style) -> dict` is everything fp.build needs: terrain, steps, placements, ropes and wires, the walk route.
"""
from __future__ import annotations

import math

import numpy as np

from ..mesh import Lines, Mesh, catenary, sphere, spline

Y_TOP = 6.4            # the road plateau, metres above the start
Z_TOP = -30.0          # where the slope meets the road
ROAD = (-31.0, -38.0)  # road z band (near edge, far edge)
CAR = (3.25, -33.3, -80.0)      # x, z, yaw (front faces +x, angled a touch toward the camera)

PATH_CTRL = [(0.0, 3.0), (0.2, -1.0), (1.3, -4.2), (2.0, -7.4), (0.7, -10.8), (-1.4, -14.2), (-1.9, -17.6),
             (-0.3, -21.0), (1.5, -24.2), (1.4, -27.0), (0.3, -29.4), (0.0, -31.4)]
STOP_S_FROM_END = 0.9  # the walk ends this far (metres along the path) before the path's last point


# ---- terrain ---------------------------------------------------------------------------------------------------------
def _noise2(x, z, seed=0):
    """cheap smooth value noise (sum of sines with irrational frequencies), -1..1."""
    r = np.random.default_rng(seed)
    acc = 0.0
    tot = 0.0
    for k in range(5):
        f = 0.05 * (1.9 ** k)
        a = r.uniform(0, 2 * math.pi, 2)
        d = r.uniform(-1, 1, 2)
        d = d / np.linalg.norm(d)
        w = 1.0 / (1.6 ** k)
        acc = acc + w * np.sin((x * d[0] + z * d[1]) * f * 2 * math.pi + a[0]) * np.cos((x * d[1] - z * d[0]) * f * 1.3 + a[1])
        tot += w
    return acc / tot


def base_height(x, z):
    """the untouched snow surface."""
    x = np.asarray(x, np.float64)
    z = np.asarray(z, np.float64)
    # a concave climb (gentle at the foot, steepest at the lip), so the car on the crest shows from the bottom
    t = np.clip(-z / -Z_TOP, 0.0, 1.0)
    slope = Y_TOP * t ** 1.6
    behind = np.maximum(z - 5.0, 0.0)
    y = np.where(z > 0, 2.6 * (1 - np.exp(-(behind / 28.0) ** 2)), slope)
    beyond = z < ROAD[1]
    far = np.maximum(ROAD[1] - z, 0.0)
    y = np.where(beyond, Y_TOP + 9.0 * (1 - np.exp(-far / 60.0)) - 0.004 * np.maximum(far - 150, 0), y)
    # the road: a calm flat band
    road = (z <= ROAD[0]) & (z >= ROAD[1])
    y = np.where(road, Y_TOP, y)
    # banks rise on both sides so the slope reads as a hollow the path climbs out of
    ax = np.abs(x)
    side = np.maximum(ax - 9.0, 0.0)
    rise = 4.0 * (1 - np.exp(-(0.005 * side ** 2 + 0.02 * side) / 4.0))
    y = y + np.where(z > ROAD[0] + 1, rise, 0.3 * rise) - 0.004 * np.maximum(ax - 120, 0)
    # soft drifts
    calm = np.clip((np.abs(x) - 3.0) / 5.0, 0, 1) * np.where(road, 0.15, 1.0)
    y = y + 0.2 * _noise2(x, z, 4) * calm             # soft, low drifts: the field stays one calm mass
    return y


class Path:
    def __init__(self):
        ctrl = [(x, 0.0, z) for x, z in PATH_CTRL]
        p = spline(ctrl, 700)
        p[:, 1] = base_height(p[:, 0], p[:, 2])
        self.p = p
        seg = np.linalg.norm(np.diff(p[:, [0, 2]], axis=0), axis=1)
        self.s = np.concatenate([[0], np.cumsum(seg)])
        self.L = float(self.s[-1])
        t = np.gradient(p[:, [0, 2]], axis=0)
        self.t = t / np.linalg.norm(t, axis=1, keepdims=True)
        self.n = np.stack([-self.t[:, 1], self.t[:, 0]], 1)     # left normal in (x, z)

    def at(self, s):
        k = np.clip(np.searchsorted(self.s, s), 1, len(self.s) - 1)
        a = (s - self.s[k - 1]) / max(self.s[k] - self.s[k - 1], 1e-9)
        a = np.clip(a, 0, 1)
        P = self.p[k - 1] * (1 - a)[..., None] + self.p[k] * a[..., None] if np.ndim(s) else self.p[k - 1] * (1 - a) + self.p[k] * a
        return P

    def width(self, s):
        """half width of the cleared stair."""
        return 0.62 + 0.10 * np.sin(np.asarray(s) * 0.83 + 1.0) + 0.05 * np.sin(np.asarray(s) * 2.3)

    def nearest(self, x, z):
        """distance to the centre line and the arc length there, for arrays of points."""
        x = np.asarray(x, np.float64)
        z = np.asarray(z, np.float64)
        flat_x, flat_z = x.reshape(-1), z.reshape(-1)
        best_d = np.full(flat_x.shape, np.inf)
        best_s = np.zeros(flat_x.shape)
        P = self.p[::2]
        S = self.s[::2]
        for k in range(0, len(P) - 1):
            ax, az = P[k, 0], P[k, 2]
            bx, bz = P[k + 1, 0], P[k + 1, 2]
            dx, dz = bx - ax, bz - az
            L2 = dx * dx + dz * dz
            u = np.clip(((flat_x - ax) * dx + (flat_z - az) * dz) / L2, 0, 1)
            px, pz = ax + u * dx, az + u * dz
            d = np.hypot(flat_x - px, flat_z - pz)
            m = d < best_d
            best_d[m] = d[m]
            best_s[m] = S[k] + u[m] * (S[k + 1] - S[k])
        return best_d.reshape(x.shape), best_s.reshape(x.shape)


def make_steps(path: Path, rise=0.15, max_len=1.55, min_len=0.6, seed=11):
    """split the path into slabs: a new step whenever the slope has climbed `rise`, or the slab got long."""
    rng = np.random.default_rng(seed)
    cuts = [0.0]
    s = 0.0
    while s < path.L - 0.3:
        y0 = path.at(s)[1]
        ln = min_len
        while ln < max_len and s + ln < path.L and path.at(s + ln)[1] - y0 < rise:
            ln += 0.05
        ln *= rng.uniform(0.92, 1.06)
        s = min(s + ln, path.L)
        cuts.append(s)
    if path.L - cuts[-1] < 0.3:
        cuts[-1] = path.L
    steps = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        top = float(path.at(b - 0.15)[1]) if b - a > 0.3 else float(path.at(b)[1])
        top = float(path.at((a + b) / 2)[1])
        steps.append((a, b, top))
    # tops never go down the hill
    out = []
    last = -1e9
    for a, b, top in steps:
        top = max(top, last + 0.04) if last > -1e8 else top
        out.append((a, b, top))
        last = top
    return out


def step_polygon(path: Path, a, b, rng=None, n=5, round_ends=False):
    """slab outline (x, z), counter-clockwise from above. With rng the sides wander a little; round_ends bows the
    front and back edges and cuts the corners, like a worn flagstone."""
    ss = np.linspace(a, b, n)
    left, right = [], []
    for s in ss:
        k = min(np.searchsorted(path.s, s), len(path.s) - 1)
        c = path.at(s)
        w = float(path.width(s))
        nl = path.n[k]
        wl = w * (rng.uniform(0.94, 1.06) if rng is not None else 1.03)
        wr = w * (rng.uniform(0.94, 1.06) if rng is not None else 1.03)
        left.append((c[0] + nl[0] * wl, c[2] + nl[1] * wl))
        right.append((c[0] - nl[0] * wr, c[2] - nl[1] * wr))
    poly = right + left[::-1]
    if round_ends:
        # bow the ends outward along the path, then cut every corner (one Chaikin pass)
        for s, idx in ((a, (0, -1)), (b, (n - 1, n))):
            k = min(np.searchsorted(path.s, s), len(path.s) - 1)
            t = path.t[k] * (-1 if s == a else 1)
            mid = (np.array(poly[idx[0]]) + np.array(poly[idx[1]])) / 2 + t * rng.uniform(0.04, 0.09)
            poly.insert(idx[1] if idx[1] > 0 else len(poly), tuple(mid))
        P = np.array(poly)
        Q = np.roll(P, -1, 0)
        poly = [tuple(v) for pair in zip(P * 0.78 + Q * 0.22, P * 0.22 + Q * 0.78) for v in pair]
    area = 0.0
    for i in range(len(poly)):
        x0, z0 = poly[i]
        x1, z1 = poly[(i + 1) % len(poly)]
        area += x0 * z1 - x1 * z0
    return poly if area < 0 else poly[::-1]


def slab_mesh(poly, top, rng, lip=0.03, depth=0.5):
    """a flagstone: buried sides, a chamfered lip all round, a top tilted a hair off level.
    Returns the mesh and the top plane y(x, z), so seams can lie on it."""
    poly = np.asarray(poly, np.float64)
    c = poly.mean(0)
    r = np.linalg.norm(poly - c, axis=1).mean()
    inset = c + (poly - c) * (1 - lip / r)
    ax, az = rng.uniform(-0.025, 0.025, 2)

    def y_at(x, z):
        return top + ax * (x - c[0]) + az * (z - c[1])
    rings = [[(x, top - depth, z) for x, z in poly], [(x, y_at(x, z) - lip * 0.8, z) for x, z in poly],
             [(x, y_at(x, z), z) for x, z in inset]]
    P, A = [], []
    n = len(poly)
    for lo, hi, ao in ((rings[0], rings[1], 0.75), (rings[1], rings[2], 1.0)):
        for i in range(n):
            j = (i + 1) % n
            P += [lo[i], lo[j], hi[j], lo[i], hi[j], hi[i]]
            A += [ao * 0.8, ao * 0.8, ao, ao * 0.8, ao, ao]
    ct = (c[0], y_at(*c), c[1])
    for i in range(n):
        P += [ct, rings[2][(i + 1) % n], rings[2][i]]
        A += [1.0] * 3
    P = np.array(P, np.float32)
    I = np.arange(len(P)).reshape(-1, 3)
    m = Mesh(P, None, ["stone"] * len(P), [0.0] * len(P), A, I).flat()
    # wind every face outward (sides away from the centre, the top up)
    cen = np.array([c[0], top - depth / 2, c[1]])
    tri = m.P.reshape(-1, 3, 3)
    out = tri.mean(1) - cen
    out[-n:] = (0, 1, 0)
    flip = (m.N.reshape(-1, 3, 3)[:, 0] * out).sum(1) < 0
    m.I[flip] = m.I[flip][:, ::-1]
    return m.flat(), y_at


def terrain_grid():
    """a tensor grid: 0.25 m cells around the path, growing to 40 m at the far edge (no T-junctions)."""
    def axis(lo_dense, hi_dense, lo, hi, step=0.25):
        core = np.arange(lo_dense, hi_dense + 1e-6, step)
        grow_hi, x, d = [], hi_dense, step
        while x < hi:
            d = min(d * 1.22, 40.0)
            x += d
            grow_hi.append(x)
        grow_lo, x, d = [], lo_dense, step
        while x > lo:
            d = min(d * 1.22, 40.0)
            x -= d
            grow_lo.append(x)
        return np.array(sorted(grow_lo) + list(core) + grow_hi)
    xs = axis(-11.0, 11.0, -700.0, 700.0)
    zs = axis(-48.0, 6.0, -900.0, 120.0)
    return xs, zs


def carve(path: Path, steps, X, Z, Y):
    """lower the snow along the stair and pile soft banks on both sides."""
    d, s = path.nearest(X, Z)
    w = path.width(s)
    starts = np.array([a for a, b, t in steps])
    tops = np.array([t for a, b, t in steps])
    k = np.clip(np.searchsorted(starts, s, side="right") - 1, 0, len(steps) - 1)
    floor = tops[k]
    inner = d < w + 0.05
    Y = np.where(inner, floor - 0.12, Y)
    # banks: a lip of snow just outside the slab edge, easing back into the slope
    u = np.clip((d - w - 0.05) / 1.25, 0, 1)
    bank_top = np.maximum(Y, floor) + 0.16 * np.sin(np.clip(u, 0, 1) * math.pi) ** 0.7
    blend = u * u * (3 - 2 * u)
    near = (d >= w + 0.05) & (d < w + 1.3) & (s < path.L + 0.5)
    Y = np.where(near, floor + 0.06 + (bank_top - floor - 0.06) * (0.35 + 0.65 * blend) * 1.0, Y)
    Y = np.where(near, np.maximum(Y, floor + 0.05), Y)
    return Y


# ---- scatter ---------------------------------------------------------------------------------------------------------
def poisson(rng, n, xr, zr, min_d, keep):
    pts = []
    tries = 0
    while len(pts) < n and tries < n * 60:
        tries += 1
        x = rng.uniform(*xr)
        z = rng.uniform(*zr)
        if not keep(x, z):
            continue
        if any((x - a) ** 2 + (z - b) ** 2 < min_d * min_d for a, b in pts):
            continue
        pts.append((x, z))
    return pts


def layout(style: dict) -> dict:
    rng = np.random.default_rng(7)
    path = Path()
    steps = make_steps(path)

    # terrain
    xs, zs = terrain_grid()
    X, Z = np.meshgrid(xs, zs)
    Y = base_height(X, Z)
    Y = carve(path, steps, X, Z, Y)

    def ground(x, z):
        return float(_bilinear(xs, zs, Y, x, z))

    # slabs: worn flagstones with a chamfered lip and a thin snow-filled gap between steps, paving seams as 1 px lines,
    # snow tucked against the edges. The stair has its own random stream, so it never moves the placements.
    srng = np.random.default_rng(23)
    prng = np.random.default_rng(31)          # the snow pillows have their own stream too
    slab = Mesh()
    seams = Lines()
    step_list = []
    for i, (a, b, top) in enumerate(steps):
        gap = srng.uniform(0.05, 0.11) if i else 0.0
        poly = step_polygon(path, a + gap, b, srng, round_ends=True)
        m, y_at = slab_mesh(poly, top, srng)
        slab = slab + m
        walk = step_polygon(path, a, b)
        step_list.append({"poly": [[round(float(x), 3), round(float(z), 3)] for x, z in walk], "top": round(top, 3)})

        def on(s, off, lift=0.006):
            k = min(np.searchsorted(path.s, s), len(path.s) - 1)
            c = path.at(s)
            x, z = c[0] + path.n[k][0] * off, c[2] + path.n[k][1] * off
            return [x, y_at(x, z) + lift, z]
        # paving in running bond: rows across the path, joints between the pavers staggered row to row
        a0, b0 = a + gap + 0.05, b - 0.05
        rows = max(1, int(round((b0 - a0) / 0.42)))
        edges = np.linspace(a0, b0, rows + 1)
        for s in edges[1:-1]:
            w = float(path.width(s)) * 0.86
            seams.add("seam", [on(s, -w), on(s, 0.0), on(s, w)])
        phase = srng.uniform(0, 1)
        for r, (s0, s1) in enumerate(zip(edges[:-1], edges[1:])):
            w = float(path.width((s0 + s1) / 2))
            n = max(2, int(round(2 * w / 0.48)))
            for j in range(n):
                x = -w + ((j + phase + 0.5 * r) % n) * 2 * w / n
                if abs(x) < w * 0.8:
                    seams.add("seam", [on(s0 + 0.02, x), on(s1 - 0.02, x)])
        # soft rounded pillows of snow along both edges, bulging a little over the stone: the reference's friendly lips
        for side in (1, -1):
            s = a + gap + prng.uniform(0.0, 0.15)
            while s < b - 0.05:
                k = min(np.searchsorted(path.s, s), len(path.s) - 1)
                c = path.at(s)
                r = prng.uniform(0.2, 0.34)
                off = side * (float(path.width(s)) + r * 0.35 + prng.uniform(-0.03, 0.05))
                x, z = c[0] + path.n[k][0] * off, c[2] + path.n[k][1] * off
                sq = prng.uniform(0.32, 0.42)
                pillow = sphere(r, "drift", segs=10, rings=5, squash=sq, smooth=True).scale(1.0, 1.0, prng.uniform(1.2, 1.6))
                yaw = math.degrees(math.atan2(path.t[k][0], path.t[k][1]))
                slab = slab + pillow.turn(yaw=yaw).at(x, top - r * sq * 0.95, z)
                s += r * prng.uniform(0.75, 1.0)         # overlapping: one scalloped bank, not a row of buns

    inst = {}

    def place(name, seed, x, z, yaw=0.0, y=None, scale=1.0):
        inst.setdefault("%s:%d" % (name, seed), []).append(
            [round(float(x), 3), round(float(ground(x, z) if y is None else y), 3), round(float(z), 3),
             round(float(yaw), 2), round(float(scale), 3)])

    # rope fence: bollards on both sides, a rope sagging between neighbours
    ropes = Lines()
    posts = []
    for side in (1, -1):
        prev = None
        s = 0.9 if side > 0 else 2.1
        while s < path.L - (3.4 if side > 0 else 1.4):    # the car side stops short: nothing stands before the car
            c = path.at(s)
            k = min(np.searchsorted(path.s, s), len(path.s) - 1)
            nl = path.n[k] * side
            off = float(path.width(s)) + 0.42 + rng.uniform(-0.05, 0.08)
            x, z = c[0] + nl[0] * off, c[2] + nl[1] * off
            seed = int(rng.integers(0, 8))
            y = ground(x, z)
            place("post", seed, x, z, yaw=rng.uniform(0, 360), y=y - 0.08)
            eye = [x, y - 0.08 + 0.68, z]
            if prev is not None:
                ropes.add("rope", catenary(prev, eye, sag=0.13 + rng.uniform(0, 0.06), n=12))
            prev = eye
            posts.append((x, z))
            s += rng.uniform(2.6, 3.3)

    # grass tufts: thick along the banks and round the posts, thin elsewhere
    tufts = 0
    for _ in range(420):
        s = rng.uniform(0, path.L)
        c = path.at(s)
        k = min(np.searchsorted(path.s, s), len(path.s) - 1)
        side = 1 if rng.random() < 0.5 else -1
        off = float(path.width(s)) + 0.12 + rng.uniform(0.0, 1.6) ** 1.6
        x, z = c[0] + path.n[k][0] * off * side, c[2] + path.n[k][1] * off * side
        if rng.random() < (0.34 if s < path.L - 4.0 else 0.1):     # sparse at the top: the car stays clear
            place("grass", int(rng.integers(0, 12)), x, z, yaw=rng.uniform(0, 360), scale=rng.uniform(0.8, 1.3))
            tufts += 1
    for x, z in posts:
        for _ in range(int(rng.integers(0, 3))):
            a = rng.uniform(0, 2 * math.pi)
            place("grass", int(rng.integers(0, 12)), x + math.cos(a) * 0.2, z + math.sin(a) * 0.2, yaw=rng.uniform(0, 360))

    # the car
    cx, cz, cyaw = CAR
    place("car", 0, cx, cz, yaw=cyaw, y=Y_TOP)

    # telephone poles along the far side of the road: two of them flank the car the way the reference's do, and the
    # wires sag across the sky above it for the whole climb; each crossarm stands square to its wires
    pole_xz = [(-64.0, -21.0), (-37.0, -28.5), (-8.5, -37.5), (14.5, -42.0), (40.0, -47.5), (67.0, -53.0)]
    wires = Lines()
    pole_tops = []
    from ..kit import build as build_asset
    for i, (x, z) in enumerate(pole_xz):
        a = build_asset("pole", i)
        (px, pz), (qx, qz) = pole_xz[max(i - 1, 0)], pole_xz[min(i + 1, len(pole_xz) - 1)]
        yaw = math.degrees(math.atan2(qx - px, qz - pz)) + 3.0 * (i % 2) - 1.5
        y = ground(x, z) - a.sink
        place("pole", i, x, z, yaw=yaw, y=y)
        R = np.radians(yaw)
        tops = []
        for k in sorted(a.anchors):
            if k == "w3":            # three conductors read lighter against the sky than four
                continue
            ax, ay, az = a.anchors[k]
            tops.append([x + ax * math.cos(R) + az * math.sin(R), y + ay, z - ax * math.sin(R) + az * math.cos(R)])
        pole_tops.append(tops)
    for p, q in zip(pole_tops[:-1], pole_tops[1:]):
        for a, b in zip(p, q):
            span = math.dist(a, b)
            wires.add("wire", catenary(a, b, sag=0.018 * span + 0.2, n=24))

    # spruce: a crowd along the ridge behind the road, stands on both flanks, a few young ones near the stair
    def clear(x, z, r):
        d, s = path.nearest(np.array([x]), np.array([z]))
        if d[0] < r + 1.6:
            return False
        if ROAD[1] - 1.5 < z < ROAD[0] + 1.0 and abs(x - cx) < 9:
            return False
        for px, pz in pole_xz:
            if (x - px) ** 2 + (z - pz) ** 2 < 4.0:
                return False
        return True

    def backdrop(x, z):
        """from the start the car stands against the pale hill: no ridge trees in a narrow wedge behind it."""
        sx, sz = PATH_CTRL[0]
        off = math.degrees(math.atan2(x - sx, sz - z) - math.atan2(cx - sx, sz - cz))
        return abs(off) > 5.5 or math.hypot(x - sx, z - sz) > 95
    def stand(x, z):
        """trees grow in stands with clearings between, not as an even comb along the horizon."""
        return _noise2(x * 1.7, z * 1.7, 9) > -0.12
    ridge = poisson(rng, 160, (-110, 110), (-130, -39.5), 3.4,
                    lambda x, z: backdrop(x, z) and stand(x, z) and clear(x, z, 2))
    flank = poisson(rng, 90, (-70, 70), (-39, 40), 3.4, lambda x, z: abs(x) > 11 + 0.08 * max(z, 0) and clear(x, z, 2))
    def open_view(x, z):
        """keep the climb an open snow field: young trees stay off the stair and out of the line to the car."""
        return abs(x) > 5.5 and not (z < -17 and -6.5 < x < 9.0) and clear(x, z, 1.4)
    near = poisson(rng, 8, (-11, 11), (-28, 6), 3.2, open_view)
    for x, z in ridge + flank:
        place("pine", int(rng.integers(0, 10)), x, z, yaw=rng.uniform(0, 360), scale=rng.uniform(0.85, 1.25))
    for x, z in near:
        place("pine_small", int(rng.integers(0, 8)), x, z, yaw=rng.uniform(0, 360), scale=rng.uniform(0.8, 1.2))
    # the dark stands either side behind the car, the way the reference frames it, the gap between them left open
    for x, z, sc in ((-13.0, -42.5, 1.15), (-16.0, -40.0, 1.05), (11.5, -40.2, 1.0), (16.5, -43.4, 1.2), (19.5, -39.8, 0.95)):
        place("pine", int(rng.integers(0, 10)), x, z, yaw=rng.uniform(0, 360), scale=sc)

    # the walk: along the centre line, eye over the slab tops
    stop_s = path.L - STOP_S_FROM_END
    route = []
    for s in np.arange(0.0, stop_s + 1e-6, 0.25):
        c = path.at(s)
        route.append([round(float(c[0]), 3), round(float(c[2]), 3)])
    look_end = [cx + 1.3, Y_TOP + 1.0, cz - 0.4]      # a little past the car: it sits left, its light falls right

    terrain = Mesh(np.stack([X, Y, Z], -1).reshape(-1, 3), None, ["snow"] * X.size, [1.0] * X.size, [1.0] * X.size,
                   _grid_tris(len(zs), len(xs))).smooth()
    return {
        "name": "first_snow",
        "terrain": terrain,
        "slabs": slab,
        "lines": ropes + wires + seams,
        "heights": {"xs": xs, "zs": zs, "y": Y},
        "steps": step_list,
        "instances": inst,
        "route": route,
        "look_end": look_end,
        "start": {"x": route[0][0], "z": route[0][1], "yaw": 0.0, "pitch": 4.0},   # the intro looks up the climb
        "bounds": [-28.0, -60.0, 28.0, 10.0],
        "stats": {"steps": len(steps), "posts": len(posts), "tufts": tufts, "pines": len(ridge) + len(flank) + 5,
                  "path_m": round(path.L, 1)},
    }


def _grid_tris(nz, nx):
    i = np.arange(nz - 1)[:, None] * nx + np.arange(nx - 1)[None, :]
    i = i.reshape(-1)
    a, b, c, d = i, i + 1, i + nx, i + nx + 1
    # grid rows run toward +z: (a, c, b) winds counter-clockwise seen from above (+y)
    return np.concatenate([np.stack([a, c, b], 1), np.stack([b, c, d], 1)])


def _bilinear(xs, zs, Y, x, z):
    i = int(np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2))
    k = int(np.clip(np.searchsorted(zs, z) - 1, 0, len(zs) - 2))
    u = (x - xs[i]) / (xs[i + 1] - xs[i])
    v = (z - zs[k]) / (zs[k + 1] - zs[k])
    u, v = min(max(u, 0), 1), min(max(v, 0), 1)
    return (Y[k, i] * (1 - u) * (1 - v) + Y[k, i + 1] * u * (1 - v) + Y[k + 1, i] * (1 - u) * v + Y[k + 1, i + 1] * u * v)
