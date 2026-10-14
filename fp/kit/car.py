"""The old car: a compact rounded plum estate with a loaded roof rack, snow on every top, headlights on, tail lights glowing."""
from __future__ import annotations

import numpy as np

from . import Asset
from ..mesh import Lines, Mesh, box, cylinder, lathe, quad, tube

# body keyframes along z (front -z): ybot, ysill, ybelt, yglass, yroof, wbot, wsill, wbelt, wglass, wroof (half widths)
KEYS = [
    (-1.80, 0.38, 0.46, 0.70, 0.72, 0.74, 0.58, 0.64, 0.63, 0.54, 0.50),
    (-1.74, 0.32, 0.42, 0.76, 0.78, 0.80, 0.67, 0.75, 0.74, 0.62, 0.56),
    (-1.55, 0.30, 0.42, 0.81, 0.83, 0.85, 0.71, 0.79, 0.79, 0.66, 0.60),
    (-0.58, 0.30, 0.42, 0.86, 0.88, 0.91, 0.72, 0.80, 0.80, 0.68, 0.62),
    (-0.06, 0.30, 0.42, 0.86, 0.89, 1.56, 0.72, 0.80, 0.80, 0.71, 0.60),
    (1.28, 0.30, 0.42, 0.86, 0.89, 1.57, 0.72, 0.80, 0.80, 0.71, 0.60),
    (1.48, 0.30, 0.42, 0.86, 0.89, 1.52, 0.72, 0.80, 0.80, 0.69, 0.58),
    (1.64, 0.31, 0.43, 0.85, 0.88, 1.33, 0.71, 0.79, 0.79, 0.67, 0.56),
    (1.75, 0.34, 0.44, 0.83, 0.86, 0.96, 0.68, 0.75, 0.74, 0.63, 0.55),
    (1.80, 0.38, 0.47, 0.80, 0.82, 0.84, 0.62, 0.70, 0.68, 0.58, 0.52),
]
SIDE_GLASS = [(-0.34, 0.60), (0.74, 1.34)]                   # door and rear quarter windows; the gaps are pillars
SCREEN = (-0.56, -0.10)                                       # windscreen span on the rake
HATCH = (1.50, 1.74)                                          # the rear glass on the rounded tail
WHEEL_Z = (-1.14, 1.12)
WHEEL_R = 0.31
CROWN = 0.13                                                  # the rounded roof edge's drop
BULGE = 0.025                                                 # the waist crease stands this far proud of the sill


def _section(z):
    """the body's cross-section at z: 16 points round the hull. Right-side edges 0-6 run sill, waist, belt ledge,
    glass, lower and upper crown; edge 7 is the roof, 8-14 mirror 6-0, 15 the floor."""
    k = np.array(KEYS)
    yb, ys, ybl, yg, yr, wb, ws, wbl, wg, wr = (float(np.interp(z, k[:, 0], k[:, i])) for i in range(1, 11))
    ch = min(CROWN, (yr - yg) * 0.5)
    inner = max(wr - 0.2, 0.05)
    right = [(wb, yb), (ws, ys), (wbl + BULGE, ys + (ybl - ys) * 0.55), (wbl, ybl), (wg, yg), (wr, yr - ch),
             (wr - 0.06, yr - ch * 0.25), (inner, yr)]
    return right + [(-x, y) for x, y in reversed(right)]


def _edge(k):
    """the right-side edge an edge index mirrors (0-6), 7 for the roof, 15 for the floor."""
    return 14 - k if 8 <= k <= 14 else k


def loft(stations, mat_of, snow_of, ao_of, caps=("car", "car")):
    """skin closed cross-sections [(z, [(x, y), ...]), ...] into a flat-shaded hull with capped ends.
    mat_of / snow_of / ao_of (z_mid, edge) name each quad's material, snow catch and occlusion."""
    P, M, S, A = [], [], [], []

    def tri(a, b, c, out, mat, snow, ao):
        n = np.cross(np.subtract(b, a), np.subtract(c, a))
        if np.linalg.norm(n) < 1e-9:
            return
        if np.dot(n, out) < 0:
            b, c = c, b
        P.extend([a, b, c])
        M.extend([mat] * 3)
        S.extend([snow] * 3)
        A.extend([ao] * 3)

    for (z0, s0), (z1, s1) in zip(stations[:-1], stations[1:]):
        n = len(s0)
        zc = (z0 + z1) / 2
        cx = (np.mean([p[0] for p in s0]) + np.mean([p[0] for p in s1])) / 2
        cy = (np.mean([p[1] for p in s0]) + np.mean([p[1] for p in s1])) / 2
        for k in range(n):
            j = (k + 1) % n
            a0, a1 = (*s0[k], z0), (*s0[j], z0)
            b0, b1 = (*s1[k], z1), (*s1[j], z1)
            mid = np.mean([a0, a1, b0, b1], 0)
            out = (mid[0] - cx, mid[1] - cy, 0.0)
            args = (out, mat_of(zc, k), snow_of(zc, k), ao_of(zc, k))
            tri(a0, a1, b1, *args)
            tri(a0, b1, b0, *args)
    for (z, s), sign, mat in ((stations[0], -1.0, caps[0]), (stations[-1], 1.0, caps[1])):
        c = (float(np.mean([p[0] for p in s])), float(np.mean([p[1] for p in s])), z)
        for k in range(len(s)):
            j = (k + 1) % len(s)
            tri(c, (*s[k], z), (*s[j], z), (0, 0, sign), mat, snow_of(z, -1), ao_of(z, -1))
    I = np.arange(len(P)).reshape(-1, 3)
    return Mesh(np.array(P, np.float32), None, M, S, A, I).flat()


def plate(poly, z0, z1, mat, snow=0.0, ao=1.0):
    """a polygon [(x, y), ...] extruded along z from z0 to z1 (lamps, arches, panels)."""
    return loft([(z0, poly), (z1, poly)], lambda z, k: mat, lambda z, k: snow, lambda z, k: ao, caps=(mat, mat))


def _hull():
    zs = sorted(set([k[0] for k in KEYS] + [z for span in SIDE_GLASS for z in span] + list(SCREEN) + list(HATCH)
                    + [-1.2, -0.95, 0.15, 1.0]))
    stations = [(z, _section(z)) for z in zs]

    def inside(z, spans):
        return any(a <= z <= b for a, b in spans)

    def mat_of(z, k):
        e = _edge(k)
        if e == 4 and inside(z, SIDE_GLASS):
            return "glass"
        if e in (5, 6, 7) and (SCREEN[0] <= z <= SCREEN[1] or HATCH[0] <= z <= HATCH[1]):
            return "glass"
        return "car"

    def snow_of(z, k):
        return 0.25 if mat_of(z, k) == "glass" else 0.95

    def ao_of(z, k):
        e = _edge(k)
        if mat_of(z, k) == "glass":
            return 0.72 if z > HATCH[0] - 0.01 else 0.85        # the rear glass faces the low sun: keep it dark
        return 0.55 if e in (0, 15) else 1.0

    return loft(stations, mat_of, snow_of, ao_of)


def _arch(x, z, side):
    """a shaded half-disc on the body side above a wheel: the wheel well."""
    r = WHEEL_R + 0.09
    pts = [(np.cos(a) * r, 0.30 + np.sin(a) * (r + 0.02)) for a in np.linspace(0, np.pi, 9)]
    m = plate(pts, -0.012, 0.012, "car", ao=0.55)
    # built along z; swap x and z so the half-disc lies in the car's side plane, proud of the panel
    m.P = m.P[:, [2, 1, 0]].copy()
    m.N = m.N[:, [2, 1, 0]].copy()
    m.I = m.I[:, ::-1].copy()
    return m.flat().at(side * x, 0, z)


def blanket(keys, t, end=0.12):
    """a soft cushion of snow lying along z: keys [(z, y, half_width), ...], thickness t, rounded ends."""
    k = np.array(keys)
    z0, z1 = float(k[0, 0]), float(k[-1, 0])
    zs = [z0, z0 + end * 0.4, z0 + end] + list(np.linspace(z0 + end, z1 - end, 5)[1:-1]) + [z1 - end, z1 - end * 0.4, z1]
    stations = []
    for i, z in enumerate(zs):
        y = float(np.interp(z, k[:, 0], k[:, 1]))
        w = float(np.interp(z, k[:, 0], k[:, 2]))
        f = 0.55 if i in (0, len(zs) - 1) else 0.85 if i in (1, len(zs) - 2) else 1.0
        ww, tt = w * (0.92 + 0.08 * f), t * f
        stations.append((z, [(-ww + 0.02, y - 0.03), (ww - 0.02, y - 0.03), (ww + 0.02, y + tt * 0.45),
                             (ww - 0.08, y + tt), (-ww + 0.08, y + tt), (-ww - 0.02, y + tt * 0.45)]))
    m = loft(stations, lambda z, e: "drift", lambda z, e: 0.0, lambda z, e: 1.0, caps=("drift", "drift"))
    return m.smooth()


def _glint(side, zc, w):
    """a slanted band of sky reflection lying just proud of a side window (open AO: one band lighter)."""
    k = np.array(KEYS)
    yg = float(np.interp(zc, k[:, 0], k[:, 4]))
    top = float(np.interp(zc, k[:, 0], k[:, 5])) - CROWN     # where the glass meets the roof chamfer
    wg = float(np.interp(zc, k[:, 0], k[:, 9]))
    wr = float(np.interp(zc, k[:, 0], k[:, 10]))
    y0, y1 = yg + 0.05, top - 0.04

    def on(y, z):
        return [side * (wg + (wr - wg) * (y - yg) / (top - yg) + 0.008), y, z]
    q = quad(on(y0, zc - w), on(y0, zc), on(y1, zc + 0.16), on(y1, zc + 0.16 - w), "glass")
    if q.N[0, 0] * side < 0:
        q.I = q.I[:, ::-1].copy()
        q = q.flat()
    return q


def _hatch_glint(x0, w, lean=0.5):
    """a slanted band of sky reflection lying on the rounded rear glass, one quad per facet of the slope."""
    k = np.array(KEYS)
    out = Mesh()
    for za, zb in ((HATCH[0] + 0.02, 1.64), (1.64, HATCH[1] - 0.02)):
        ya, yb = (float(np.interp(z, k[:, 0], k[:, 5])) + 0.012 for z in (za, zb))
        xa, xb = x0 + (za - HATCH[0]) * lean, x0 + (zb - HATCH[0]) * lean
        q = quad([xa, ya, za + 0.01], [xa + w, ya, za + 0.01], [xb + w, yb, zb + 0.01], [xb, yb, zb + 0.01], "glass")
        if q.N[0, 1] + q.N[0, 2] < 0:
            q.I = q.I[:, ::-1].copy()
            q = q.flat()
        out = out + q
    return out


def _wheel(x, z, side):
    tyre = cylinder(WHEEL_R, 0.21, "tyre", segs=10, ao=0.8).at(0, -0.105, 0).turn(roll=90).at(side * x, WHEEL_R, z)
    hub = cylinder(0.14, 0.04, "chrome", segs=8).at(0, -0.02, 0).turn(roll=90).at(side * (x + 0.135), WHEEL_R, z)
    return tyre + hub


def _dome(rx, rz, h, mat, snow=1.0, segs=10):
    """a rounded flat-bottomed mound, rx by rz half sizes, h tall (a tarp over a load, a cushion of snow)."""
    prof = [(1.0, 0.0), (1.0, 0.22), (0.88, 0.55), (0.62, 0.84), (0.3, 0.97), (0.001, 1.0)]
    return lathe([(r, y * h) for r, y in prof], mat, segs=segs, snow=snow, cap_top=False).scale(rx, 1.0, rz)


def _over(rx, rz, h, x, z):
    """height of a _dome's top at (x, z) in its own frame (for ropes lying over it)."""
    rho = min(np.hypot(x / rx, z / rz), 1.0)
    return float(np.interp(rho, [0.0, 0.3, 0.62, 0.88, 1.0], [1.0, 0.97, 0.84, 0.55, 0.22])) * h


def _load(rng):
    """the roof rack: rails on four feet and one big tarp mound over the bags, a suitcase corner at the back,
    everything roped down and under snow"""
    y0 = 1.60
    m = Mesh()
    for x in (-0.55, 0.55):
        m = m + tube([(x, y0 - 0.03, -0.04), (x, y0 + 0.07, 0.02), (x, y0 + 0.07, 1.36), (x, y0 - 0.03, 1.42)], 0.022,
                     "metal", segs=4)
    for z in (0.03, 1.34):
        m = m + box(1.16, 0.04, 0.05, "metal").at(0, y0 + 0.04, z)
    # the mound: one long tarp hump, a lower hump in front where the duffel lies; both catch snow on top
    rx, rz, h, zc = 0.50, 0.64, 0.52, 0.76
    tarp = _dome(rx, rz, h, "canvas").at(-0.02, y0 + 0.06, zc)
    tarp = tarp + _dome(0.40, 0.34, 0.30, "canvas").turn(yaw=float(rng.uniform(-8, 8))).at(0.05, y0 + 0.06, 0.24)
    tarp = tarp.jitter(0.025, int(rng.integers(0, 999)))
    # a suitcase corner and a rolled mat poking out at the back, under the tarp's hem
    case = box(0.42, 0.20, 0.20, "canvas", snow=1.0).turn(yaw=float(rng.uniform(-10, 4))).at(-0.18, y0 + 0.07, 1.28)
    lines = Lines()
    for z in (0.52, 1.02):
        pts = [[-0.56, y0 + 0.08, z]]
        for x in np.linspace(-0.46, 0.46, 7):
            pts.append([x - 0.02, y0 + 0.06 + _over(rx, rz, h, x + 0.02, z - zc) + 0.015, z])
        pts.append([0.56, y0 + 0.08, z])
        lines.add("rope", pts)
    lines.add("rope", [[-0.56, y0 + 0.08, 0.24], [-0.2, y0 + 0.30, 0.22], [0.25, y0 + 0.33, 0.26], [0.56, y0 + 0.08, 0.24]])
    return m + tarp + case, lines


def build(seed=0) -> Asset:
    """the parked car (front toward -z), a compact old estate ~3.6 m long, lights on"""
    rng = np.random.default_rng(900 + seed)
    m = _hull()
    for side in (-1, 1):
        for z in WHEEL_Z:
            m = m + _wheel(0.70, z, side) + _arch(0.832, z, side)
    # bumpers: dulled chrome bars that wrap round the corners, snow along their tops
    for z, s in ((-1.85, -1), (1.85, 1)):
        m = m + box(1.42, 0.12, 0.10, "chrome", snow=1.0).at(0, 0.31, z)
        for x in (-0.72, 0.72):
            m = m + box(0.10, 0.12, 0.24, "chrome", snow=1.0).turn(yaw=-s * np.sign(x) * 20).at(x, 0.31, z - s * 0.08)
    # front: grille, round headlamps in chrome rings
    m = m + box(0.52, 0.16, 0.04, "tyre").at(0, 0.48, -1.80)
    for x in (-0.47, 0.47):
        m = m + cylinder(0.115, 0.05, "chrome", segs=10).turn(pitch=90).at(x, 0.60, -1.79)
        m = m + cylinder(0.09, 0.05, "headlamp", segs=10).turn(pitch=90).at(x, 0.60, -1.81)
    # rear: round tail lamps with a pale hot core high on the corners, a small reflector under each, a number plate
    for x in (-0.50, 0.50):
        m = m + cylinder(0.085, 0.04, "taillight", segs=10).turn(pitch=90).at(x, 0.66, 1.815)
        m = m + cylinder(0.04, 0.04, "tailcore", segs=8).turn(pitch=90).at(x, 0.66, 1.83)
        m = m + cylinder(0.04, 0.03, "taillight", segs=6).turn(pitch=90).at(x, 0.50, 1.815)
    m = m + box(0.34, 0.10, 0.02, "canvas").at(0, 0.48, 1.81)
    # wing mirrors on stalks
    for x in (-0.86, 0.86):
        m = m + box(0.10, 0.08, 0.05, "chrome", snow=1.0).at(x, 0.94, -0.46)
    load, lines = _load(rng)
    m = m + load
    # thick snow on the hood, along the roof edges round the load, and drifted on the rear bumper
    m = m + blanket([(-1.70, 0.81, 0.54), (-1.2, 0.85, 0.60), (-0.66, 0.89, 0.62)], 0.08)
    m = m + blanket([(-0.08, 1.55, 0.56), (1.30, 1.56, 0.56)], 0.06)
    m = m + blanket([(-0.68, 0.44, 0.06), (0.68, 0.44, 0.06)], 0.05, end=0.08).turn(yaw=90).at(0, 0.0, 1.86)
    # the sky caught in the glass: one broad band on the door, a thin one on the quarter light and the hatch
    for side in (-1, 1):
        for (z0, z1), stripes in zip(SIDE_GLASS, (((0.38, 0.2),), ((0.55, 0.06),))):
            for f, w in stripes:
                m = m + _glint(side, z0 + (z1 - z0) * f, w)
    m = m + _hatch_glint(-0.24, 0.07)
    # body lines: a chrome strip along the waist crease, the door shuts and handles, 1 px each
    for side in (-1, 1):
        x = side * (0.80 + BULGE + 0.004)
        lines.add("chrome", [[x, 0.66, -1.62], [x, 0.66, 1.70]])
        for z in (-0.48, 0.66):
            lines.add("tyre", [[side * 0.812, 0.44, z], [side * 0.806, 0.86, z]])
        lines.add("chrome", [[side * 0.808, 0.80, 0.50], [side * 0.808, 0.80, 0.60]])
    lines.add("wire", [[0.68, 0.88, -1.50], [0.70, 1.80, -1.62]])         # radio aerial
    lights = [{"pos": [x, 0.60, -1.88], "dir": [0.0, -0.10, -1.0], "angle": 26, "range": 19, "power": 1.25}
              for x in (-0.47, 0.47)]
    # the tail lamps throw a small pink halo on the snow and bumper behind the car
    lights += [{"pos": [x, 0.66, 1.95], "dir": [0.0, -0.55, 1.0], "angle": 55, "range": 2.2, "power": 0.6,
                "ramp": "tailglow"} for x in (-0.50, 0.50)]
    m = m + cylinder(0.03, 0.12, "tyre", segs=6).turn(pitch=90).at(-0.42, 0.20, 1.86)       # exhaust pipe
    return Asset(m.jitter(0.004, seed), lines=lines, box=(0.92, 1.92), lights=lights,
                 anchors={"exhaust": [-0.42, 0.20, 1.95]})
