"""First Snow, the place: everything in metres, and the one composed camera that sees it.

The painted view (paint3d.py -> web/layers.*) is built from this module and nothing else knows where things stand:
the Blender export (paint3d.export -> scene3d.json, terrain.npz, road.npz), the pixel sprites laid over the render
(draw2d.py: posts, ropes, wires, poles, the car) and the runtime's scene.json (the walk route, the car's anchors) all
read it. Axes: x across (right), y up, z into the picture, measured from the foot of the stair.

    the camera    a locked third-person view pulled well back, raised to about the crest, a long lens, plus a
                  near-field lens that draws the ground at the bottom of the frame bigger and steeper (ppm, proj)
    the ground    a hill with no shelf, one wind drift, a shallow groove for the stair
    the road      a plough-cleared lane along the crest, cut into the snow: ruts, plough ridges, a trodden shoulder
    the stair     irregular flagstones along an S (path_x), bigger in metres near the camera, up to the road
    the props     rope fence posts and their ropes, an old fence buried in the drift, snow pillows, spruces, poles
    the car       an old estate parked on the road's near half, nose toward the sun-side pole
    the walk      the route up the stones and along the road to stand by the car's nose

The scattered things come from one seeded stream (layout()), so the place is the same on every run.
"""
from __future__ import annotations

import math

import numpy as np

NAME, TITLE = "first_snow", "First Snow"   # the layout this place paints (fp/art/<NAME>, blender/<NAME>.py) and its name

# ---------------------------------------------------------------- the camera and the picture
# The canvas is a little taller than the composed frame so a short establishing tilt can open on the sky and portrait
# screens can show more of it; the view settles on rows VIEW_TOP..VIEW_TOP+VIEW_H. It is much wider than a screen: the
# same camera sees a wider frame, and the view follows the walker across it.
W = 1600                   # canvas width (art px): ~2.5 screens of 16:9 at the composed height
CORE_W = 880               # the composed picture in the middle (the hand-placed clouds, rims and veils were drawn on a
CORE_X = (W - CORE_W) // 2   # canvas this wide): its column c is the canvas's column CORE_X + c
VIEW_H = 360               # the composed frame's height
SKY_PAD, GROUND_PAD = 160, 24   # sky above the frame (the opening tilt, tall screens) and a little ground below it
H = SKY_PAD + VIEW_H + GROUND_PAD
VIEW_TOP = SKY_PAD
F = 795.0                  # focal length in art px (a long lens: vertical fov ~25 deg)
ZB = 31.5                  # the camera stands this far behind the foot of the stair (m): she is small in a big world
CAMH = 7.6                 # eye height (m): about the crest, a 3/4 view down onto the stones
X0, Y0 = W / 2, VIEW_TOP + 147.0   # principal point; Y0 is the horizon row, just over the crest
CREST_ROW = VIEW_TOP + 155         # where the crest meets the sky (~43% down the frame)
XC = W / 2 - 4             # the composition's centre column (between the stair and the car): narrow screens crop to it
CRANE = (20, VIEW_TOP)     # the establishing tilt: the view's top row at the start (sky) and once settled
HILL_CUT = 30.0            # the hill layer holds the ground nearer than this (m); the tree layer holds the rest


def smooth(a, b, x):
    t = np.clip((np.asarray(x, np.float64) - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# The near-field lens: a pixel artist draws the ground at her feet bigger and steeper than a long lens would (huge
# cropped flagstones, fat posts), while the crest keeps the long-lens view. Below the seam (z < LENS_ZS) the scale
# grows faster than perspective (LENS_A) and the ground drops further (LENS_B px), smoothly from the seam; above it the
# projection is the plain pinhole. Everything goes through ppm()/proj(), so posts, stones, ropes and the walker grow
# together. Blender draws the same lens as a vertex warp (blender/first_snow.py).
LENS_ZS, LENS_ZB, LENS_A, LENS_B = 12.0, 1.0, 1.4, 60.0


def _lens(z):
    return smooth(LENS_ZS, LENS_ZB, z)


def ppm(z):
    """art px per metre at depth z"""
    z = np.asarray(z, np.float64)
    return F / (z + ZB) * (1 + LENS_A * _lens(z))


def ground_row(z):
    """how far below the horizon row the ground plane y=0 lies at depth z (art px)"""
    z = np.asarray(z, np.float64)
    return CAMH * F / (z + ZB) + LENS_B * _lens(z)


def proj(x, y, z):
    """a point in metres -> screen (art px); verticals stay vertical, as a pixel artist draws them"""
    k = ppm(z)
    sx, sy = X0 + k * x, Y0 + ground_row(z) - k * y
    if np.ndim(sx) == 0:
        return float(sx), float(sy)
    return sx, sy


# ---------------------------------------------------------------- the ground
Z_FOOT, Z_CREST = 6.0, 21.0  # the climb: the foot of the slope and the crest (m)
Z_STAIR0 = 3.4             # the flagstones start below the frame's bottom edge (the nearest are cut by it)
HS = 1.36                  # the hill's height scale: the crest stands ~7 m over the foot
PATH = [(-2.0, 3.4), (2.0, 2.6), (5.2, 1.0), (8.0, -1.6), (11.0, -1.0), (14.2, 3.4), (17.4, 4.2), (19.8, 3.0),
        (22.0, 1.3), (25.0, 0.2)]  # the stair's bends (z, x): on screen a dark S
# wind drift lobes, each from, to (x, z) left to right, and its height (m): the one left of the stair, then two out in
# the wider world (one on the left plateau, one on the right slope)
DRIFTS = [((-20.0, 14.5), (-5.0, 9.4), 1.0), ((-46.0, 20.5), (-27.0, 15.5), 0.9), ((16.5, 9.4), (34.0, 13.6), 0.8)]


_SEGMENTS = {}


def _catmull(knots, t):
    """a Catmull-Rom curve through knots [(t, value)] (t ascending), at t. The segment index is clamped to the inner
    knots, so the curve runs flat before the second knot and past the second-to-last one; the committed art (the
    stair's foot, the road's far ends) is drawn from it as it is, so it stays. Each segment's terms are worked out
    once per knot list (the same arithmetic, so the same values) and gathered per point."""
    key = tuple(knots)
    if key not in _SEGMENTS:
        kt = np.array([k[0] for k in knots])
        kv = np.array([k[1] for k in knots])
        i = np.arange(1, len(kt) - 2)
        dt = kt[i + 1] - kt[i]
        m1 = (kv[i + 1] - kv[i - 1]) / (kt[i + 1] - kt[i - 1]) * dt
        m2 = (kv[i + 2] - kv[i]) / (kt[i + 2] - kt[i]) * dt
        _SEGMENTS[key] = (kt, np.stack([kt[i], dt, kv[i], kv[i + 1], m1, m2], 1))
    kt, seg = _SEGMENTS[key]
    t = np.asarray(t, np.float64)
    i = np.clip(np.searchsorted(kt, t) - 1, 1, len(kt) - 3)
    t0, dt, p1, p2, m1, m2 = np.moveaxis(seg[i - 1], -1, 0)
    u = np.clip((t - t0) / dt, 0, 1)
    u2, u3 = u * u, u * u * u
    return (2 * u3 - 3 * u2 + 1) * p1 + (u3 - 2 * u2 + u) * m1 + (-2 * u3 + 3 * u2) * p2 + (u3 - u2) * m2


def path_x(z):
    """the stair's centre line (a Catmull-Rom curve through PATH): a long swing left at the foot, across to the right
    in mid-slope, then up and a little back to arrive beside the car's nose"""
    return _catmull(PATH, z)


def brow(x):
    """the hill's height along its brow: no shelf. It rises from a lower shoulder on the left to a rounded top under
    the car, then falls away to the right behind the tree band"""
    x = np.asarray(x, np.float64)
    return (4.15 + 1.0 * np.exp(-((x + 2.4) / 6.8) ** 2) - 0.065 * np.maximum(x - 1.5, 0)
            - 0.3 * smooth(-7.0, -11.0, x))


def drift(x, z):
    """the wind drifts (DRIFTS), each a long lobe with a gentle side and a steep side, so it shows a lit crest line
    over a soft shaded face"""
    return sum(drift_lobe(x, z, *lobe) for lobe in DRIFTS)


def drift_lobe(x, z, a, b, hh):
    (ax, az), (bx, bz) = a, b
    dx, dz = bx - ax, bz - az
    ln = math.hypot(dx, dz)
    ux, uz = dx / ln, dz / ln
    t = ((x - ax) * ux + (z - az) * uz) / ln
    d = (x - ax) * uz - (z - az) * ux                    # >0: behind the crest line (away from the camera)
    d = d - 0.9 * np.sin(t * 5.5) * (t > 0) * (t < 1)    # the crest line meanders
    taper = smooth(-0.05, 0.25, t) * smooth(1.05, 0.7, t) * (0.75 + 0.25 * np.sin(t * 3.0 + 0.5))
    return hh * taper * np.exp(-(d / np.where(d > 0, 3.6, 0.9)) ** 2)


def ground(x, z):
    """the snow's height (m) before the road is cut"""
    x = np.asarray(x, np.float64)
    z = np.asarray(z, np.float64)
    zc_x = Z_CREST - 0.10 * x                                       # the crest runs diagonally, high on the left
    s = smooth(Z_FOOT, zc_x, z)
    h = HS * brow(x) * s
    h = h + 0.02 * np.maximum(z - zc_x, 0)                          # the plateau rises gently to the trees
    h = h - np.maximum(z - 58, 0) * 0.6                             # and drops away behind the tree band
    zc = np.clip(z, Z_FOOT, Z_CREST + 0.6)
    groove = np.exp(-((x - path_x(zc)) / 2.6) ** 2) * (z < Z_CREST + 1.0)
    h = h - 0.08 * groove * s                                       # the stair runs in a shallow groove
    h = h + 0.5 * np.sin(0.13 * x + 0.05 * z + 0.4) * smooth(4, 12, z) * (1 - smooth(Z_CREST, Z_CREST + 4, z))
    return h + drift(x, z)


def terrain(x, z):
    """the ground (m): the snow with the road cut into it (road_cut)"""
    x = np.asarray(x, np.float64)
    z = np.asarray(z, np.float64)
    return road_cut(x, z, ground(x, z))


# ---------------------------------------------------------------- the road
# A plough-cleared country lane along the crest: in from the left plateau, over the brow where the car is parked, down
# the right slope, and away behind the tree band at both ends. It is cut into the snow: the lane lies a little below
# the snow beside it, two darker tyre ruts run in its near half (the car pulled over onto them), a low banked plough
# ridge lies along each edge, and where the stair arrives the near ridge is trodden flat into a lighter shoulder.
# A painter's cheat: the lane falls toward the camera across its width (ROAD_FALL), so from an eye this close to the
# crest it reads as a calm band, not a sliver.
ROAD = [(-90.0, 50.0), (-74.0, 41.0), (-62.0, 33.6), (-50.0, 28.2), (-36.0, 25.0), (-20.0, 22.2), (-9.0, 19.3),
        (-2.0, 20.5), (4.0, 22.6), (12.0, 24.0), (22.0, 25.0), (32.0, 27.0), (42.0, 30.4), (54.0, 35.8), (76.0, 46.0)]
ROAD_HW = 2.8              # the lane's half width (m)
ROAD_FALL = 0.15           # its fall toward the camera across its width (m per m)
ROAD_SINK = 0.18           # the lane lies this far below the snow at its centre line (m), at least
ROAD_BLEND = 2.4           # past the ridges the snow meets the old ground over this (m)
ROAD_SMOOTH = 3.0          # the lane's long profile: the ground along the centre line smoothed over this (m)
TRACK_W = -0.7             # the tyre track runs this far toward the camera of the centre line (m): the near half
RUT_OFF, RUT_HW = 0.85, 0.3    # each rut this far either side of the track, this wide either side of its middle (m)
RUT_DEPTH = 0.04           # how far the ruts are pressed in (m)
RUT_DARK = 0.24            # the darker packed snow of a rut: this far either side of its middle (m)
BANK_HW = 0.55             # a plough ridge's half width (m), its middle BANK_HW past the lane's edge
BANK_H = (0.14, 0.3)       # its height (m), the near ridge and the far one: the near one low, so it hides no lane
ROAD_EDGE = ROAD_HW + 2 * BANK_HW   # the road's half width with its ridges (m)
STAIR_GAP = 1.4            # the near ridge is trodden flat this far either side of where the stair arrives (m)
SHOULDER = 2.2             # and the trodden shoulder reaches this far along the road from it (m)
SHOULDER_IN = 0.9          # and this far into the lane (m), short of the near rut
ROAD_OFF, ROAD_LANE, ROAD_RUT, ROAD_BANK, ROAD_SHOULDER = 0, 1, 2, 3, 4   # what road_label calls each part


def road_z(x):
    """the road's centre line: its depth z at column x (a Catmull-Rom curve through ROAD)"""
    return _catmull(ROAD, x)


def road_slope(x):
    """dz/dx of the centre line"""
    return (road_z(np.asarray(x, np.float64) + 0.05) - road_z(np.asarray(x, np.float64) - 0.05)) / 0.1


def road_w(x, z, slope=None):
    """the signed distance (m) from the centre line, across the road: < 0 toward the camera (slope: road_slope(x),
    when the caller has it)"""
    return (z - road_z(x)) / np.sqrt(1 + (road_slope(x) if slope is None else slope) ** 2)


_PROFILE = {}


def road_level(x):
    """the lane's height on its centre line: the snow along it less ROAD_SINK, but never so low that the snow beside
    its near edge would stand over it (a lip toward the camera hides the lane), smoothed over ROAD_SMOOTH"""
    if not _PROFILE:
        xs = np.arange(ROAD[0][0], ROAD[-1][0] + 1e-6, 0.25)
        m = road_slope(xs)
        n = np.sqrt(1 + m * m)
        near = ground(xs + ROAD_EDGE * m / n, road_z(xs) - ROAD_EDGE / n)
        g = np.maximum(ground(xs, road_z(xs)) - ROAD_SINK, near + ROAD_FALL * ROAD_HW)
        k = np.exp(-0.5 * (np.arange(-48, 49) * 0.25 / ROAD_SMOOTH) ** 2)
        g = np.convolve(np.pad(g, 48, mode="edge"), k / k.sum(), mode="valid")
        _PROFILE.update(xs=xs, h=g)
    return np.interp(x, _PROFILE["xs"], _PROFILE["h"])


_STAIR = []


def stair_top():
    """where the stair's centre line meets the lane's near edge (x, z)"""
    if not _STAIR:
        zs = np.linspace(Z_FOOT, Z_CREST + 4, 2000)
        xs = path_x(zs)
        k = int(np.argmax(road_w(xs, zs) > -ROAD_HW))
        _STAIR.append((float(xs[k]), float(zs[k])))
    return _STAIR[0]


def _bump(d):
    """a rounded ridge across its width: 1 on its middle, 0 at |d| = 1 (like the pillows' domes)"""
    return np.clip(1 - d * d, 0, 1) ** 1.5


def road_parts(x, z):
    """per point: the distance across the road (w), the near ridge's gap where the stair arrives (0..1, 1 = trodden
    flat) and the distance along the road from the stair's top"""
    m = road_slope(x)
    w = road_w(x, z, m)
    sx, _ = stair_top()
    along = np.abs(x - sx) * np.sqrt(1 + m ** 2)
    gap = smooth(STAIR_GAP + 0.6, STAIR_GAP - 0.2, along) * (w < 0)
    return w, gap, along


def road_cut(x, z, h):
    """the road cut into the snow h: the lane falling ROAD_FALL toward the camera, ruts pressed in, the ridges banked
    along its edges (the near one trodden flat where the stair arrives), the snow beyond easing back to h"""
    w, gap, _ = road_parts(x, z)
    aw = np.abs(w)
    lane = road_level(x) + ROAD_FALL * w
    t = smooth(ROAD_HW, ROAD_EDGE + ROAD_BLEND, aw)
    base = lane * (1 - t) + h * t
    rut = np.zeros_like(aw)
    for o in (-RUT_OFF, RUT_OFF):
        rut = np.maximum(rut, _bump((w - TRACK_W - o) / RUT_HW))
    bank = np.where(w < 0, BANK_H[0], BANK_H[1]) * _bump((aw - ROAD_HW - BANK_HW) / BANK_HW) * (1 - gap)
    return base - RUT_DEPTH * rut * (aw < ROAD_HW) + bank


def road_label(x, z):
    """what the road is at each point: ROAD_OFF, ROAD_LANE (packed snow), ROAD_RUT, ROAD_BANK (a plough ridge) or
    ROAD_SHOULDER (trodden, where the stair arrives)"""
    w, gap, along = road_parts(x, z)
    aw = np.abs(w)
    lab = np.where(aw < ROAD_HW, ROAD_LANE, np.where(aw < ROAD_EDGE, ROAD_BANK, ROAD_OFF)).astype(np.uint8)
    for o in (-RUT_OFF, RUT_OFF):
        lab[(np.abs(w - TRACK_W - o) < RUT_DARK) & (aw < ROAD_HW)] = ROAD_RUT
    trod = (w < -ROAD_HW + SHOULDER_IN) & (w > -ROAD_EDGE) & (along < SHOULDER)
    lab[trod | ((lab == ROAD_BANK) & (gap > 0.5))] = ROAD_SHOULDER
    return lab


_RASTER = {}


def raster_terrain(zmin=Z_STAIR0 - 3.0, zmax=110.0):
    """the ground as the camera sees it: depth z per screen pixel (inf where no ground shows). Each column is marched
    from near to far; the running highest point drawn so far tells, for every row, the first depth that reaches it.
    Computed once per (zmin, zmax); the array is read-only."""
    if (zmin, zmax) not in _RASTER:
        Z = _raster_terrain(zmin, zmax)
        Z.flags.writeable = False
        _RASTER[zmin, zmax] = Z
    return _RASTER[zmin, zmax]


def _raster_terrain(zmin, zmax):
    zs = zmin + (zmax - zmin) * np.linspace(0, 1, 2400) ** 1.6
    cols = np.arange(W) + 0.5
    k = ppm(zs)[:, None]
    x = (cols[None, :] - X0) / k
    y = Y0 + ground_row(zs)[:, None] - k * terrain(x, zs[:, None])          # (nz, W) screen row of each sample
    run = np.minimum.accumulate(y, axis=0)                                  # the silhouette so far
    Z = np.full((H, W), np.inf)
    rows = np.arange(H) + 0.5
    for c in range(W):
        k = np.searchsorted(-run[:, c], -rows, side="left")                 # first sample whose silhouette <= row
        ok = k < len(zs)
        Z[ok, c] = zs[k[ok]]
    return Z


def crest_rows(Z):
    """the first ground row of every column: where the snow meets what is behind it"""
    seen = np.isfinite(Z)
    return np.where(seen.any(0), seen.argmax(0), H)


ROAD_STEP, ROAD_ACROSS = 0.2, 41   # the road's strip for Blender: a sample every ROAD_STEP m along it, this many across


def road_strip():
    """the road as a strip of quads for Blender: sampled along every ROAD_STEP and across at even steps plus every
    part's seam (so the ruts' and ridges' edges run clean), each vertex on the ground; vertex grids x, y, z (along,
    across) and each quad's part (road_label)"""
    xs = np.arange(ROAD[1][0], ROAD[-2][0], ROAD_STEP)
    seams = [-ROAD_HW + SHOULDER_IN] + [TRACK_W + o + k * RUT_DARK for o in (-RUT_OFF, RUT_OFF) for k in (-1, 1)]
    seams += [k * e for k in (-1, 1) for e in (ROAD_HW, ROAD_EDGE)]
    ws = np.unique(np.round(np.concatenate([np.linspace(-ROAD_EDGE, ROAD_EDGE, ROAD_ACROSS), seams]), 4))
    m = road_slope(xs)[:, None]
    n = np.sqrt(1 + m * m)
    X = xs[:, None] - ws[None, :] * m / n
    Z = road_z(xs)[:, None] + ws[None, :] / n
    Y = terrain(X, Z)
    lab = road_label(0.25 * (X[1:, 1:] + X[:-1, :-1] + X[1:, :-1] + X[:-1, 1:]),
                     0.25 * (Z[1:, 1:] + Z[:-1, :-1] + Z[1:, :-1] + Z[:-1, 1:]))
    return X, Y, Z, lab


# ---------------------------------------------------------------- the stair
def stair_slabs(rng):
    """big flat flagstones laid along the centre line, each turned to the path, with a snow seam between. A painter's
    cheat on top of perspective: the stones near the camera are also bigger in metres (fewer, bigger stones at the
    foot, smaller and closer-set ones toward the crest), so near to far they shrink ~4x on screen.
    Returns the slabs and the centre line sampled by arc length (s, x, z)."""
    zs = np.linspace(Z_STAIR0, Z_CREST + 0.9, 4000)
    xs = path_x(zs)
    seg = np.hypot(np.diff(xs), np.diff(zs))
    s = np.concatenate([[0], np.cumsum(seg)])
    slabs = []
    at = 0.1
    while at < s[-1] - 0.3:
        k = int(np.searchsorted(s, at))
        f = float(smooth(Z_STAIR0, Z_CREST, zs[min(k, len(zs) - 1)]))   # 0 at the frame's bottom .. 1 at the crest
        d = rng.uniform(0.85, 1.15) * (1.25 - 0.55 * f)
        gap = rng.uniform(0.08, 0.16) * (1.0 - 0.35 * f)
        c = at + d / 2
        i = int(np.searchsorted(s, c))
        i = min(max(i, 1), len(zs) - 2)
        cx, cz = xs[i], zs[i]
        tx, tz = xs[i + 1] - xs[i - 1], zs[i + 1] - zs[i - 1]
        n = math.hypot(tx, tz)
        tx, tz = tx / n, tz / n
        w = rng.uniform(0.86, 1.12) * (1.95 - 0.8 * f)
        slabs.append(dict(cx=cx, cz=cz, tx=tx, tz=tz, d=d, w=w, off=rng.uniform(-0.1, 0.1) * (1 - 0.6 * f),
                          rot=rng.uniform(-0.18, 0.18), skew=rng.uniform(-0.18, 0.18),
                          harm=[(int(rng.integers(2, 5)), rng.uniform(0, 2 * math.pi), rng.uniform(0.03, 0.08))
                                for _ in range(2)],
                          sq=rng.uniform(3.4, 5.0)))
        at += d + gap
    return slabs, (s, xs, zs)


def slab_outline(sb, n=28):
    """an irregular rounded flagstone in the ground plane: a squarish superellipse with a couple of slow wobbles in
    its radius and a little skew, so no two stones share a shape"""
    r = math.atan2(sb["tz"], sb["tx"]) + sb["rot"]
    tx, tz = math.cos(r), math.sin(r)
    nx, nz = tz, -tx
    hw, hd = sb["w"] / 2, sb["d"] / 2
    e = 2.0 / sb["sq"]
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        c, s_ = math.cos(a), math.sin(a)
        lx = hw * math.copysign(abs(c) ** e, c)
        lz = hd * math.copysign(abs(s_) ** e, s_)
        rad = 1.0 + sum(amp * math.sin(m * a + ph) for m, ph, amp in sb["harm"])
        lx, lz = lx * rad, lz * rad + sb["skew"] * lx * 0.5
        pts.append((sb["cx"] + sb["off"] * nx + lx * nx + lz * tx,
                    sb["cz"] + sb["off"] * nz + lx * nz + lz * tz))
    return pts


def stone_top(sb, x, z):
    """the height of a stone's top at (x, z): it follows a little of the slope, so it stands proud of the snow at its
    front edge (a riser) and sinks into the drift at its back"""
    hc = float(terrain(sb["cx"], sb["cz"]))
    return hc + 0.42 * (float(terrain(x, z)) - hc) + 0.1


# ---------------------------------------------------------------- the car, the poles, the trees
# an old rounded estate parked on the road's near half, its tyres in the ruts, its nose toward the sun-side pole: we
# see its rear and its right flank. Drawn about 1.15 x a real old estate, so she stands about as tall as its roof.
CAR = dict(L=4.9, W=2.08)  # the estate's length and width (m) before CS
CS = 1.05                  # its scale
CAR_MID = -2.0             # the car's middle stands over this column of the road (m)
# the headlamps: one spot between the two lamps, this far along the car from its tail and this high (m, on the car as
# drawn at CAR["L"] long, scaled with it), aimed along the nose and LAMP_TILT degrees down. Blender's spot
# (blender/first_snow.py, via scene3d.json), the walk grid's lamp light and the beam drawn in the air all use lamp3d()
LAMP_U, LAMP_V, LAMP_TILT = 5.15, 0.72, 13.0


def _car_pose():
    """the car's tail centre (x, z), its yaw (deg, the road's heading there) and its near rear tyre's contact"""
    m = float(road_slope(CAR_MID))
    n = math.hypot(1, m)
    mx, mz = CAR_MID - TRACK_W * m / n, float(road_z(CAR_MID)) + TRACK_W / n      # on the tyre track
    a = math.atan(m)
    du, dw = (math.cos(a), math.sin(a)), (math.sin(a), -math.cos(a))
    tx, tz = mx - 0.5 * CS * CAR["L"] * du[0], mz - 0.5 * CS * CAR["L"] * du[1]
    at = (tx + CS * (0.95 * du[0] + 0.86 * dw[0]), tz + CS * (0.95 * du[1] + 0.86 * dw[1]))
    return (tx, tz), math.degrees(a), at


(CAR["x"], CAR["z"]), CAR["yaw"], CAR_AT = _car_pose()   # CAR_AT: the near rear tyre's contact (m), where the
                                                        # hand-drawn sprite stands


def car3d() -> dict:
    """the car as a box in metres for Blender, where it only casts its shadow under the hand-drawn sprite: its tail
    centre, yaw, size and the road's height under it"""
    a = math.radians(CAR["yaw"])
    L, Wd = CAR["L"] * CS, CAR["W"] * CS
    pts = [(CAR["x"] + u * L * math.cos(a) + w * math.sin(a), CAR["z"] + u * L * math.sin(a) - w * math.cos(a))
           for u in (0, 0.5, 1) for w in (-Wd / 2, 0, Wd / 2)]
    y = float(np.mean([float(terrain(px, pz)) for px, pz in pts]))
    return dict(x=CAR["x"], z=CAR["z"], yaw=CAR["yaw"], L=L, W=Wd, y=y)


def lamp3d(c: dict = None) -> dict:
    """the headlamps' spot in metres: where it sits (x, y, z), the car's heading (yaw, deg) and the aim's tilt below
    the horizontal (deg); c is car3d()"""
    c = c or car3d()
    a = math.radians(c["yaw"])
    k = c["L"] / CAR["L"]
    return dict(x=c["x"] + k * LAMP_U * math.cos(a), y=c["y"] + k * LAMP_V, z=c["z"] + k * LAMP_U * math.sin(a),
                yaw=c["yaw"], tilt=LAMP_TILT)


def lamp_ahead(far: float, c: dict = None) -> tuple:
    """the point on the headlamps' aim `far` metres ahead of them (along the ground) (x, y, z)"""
    lp = lamp3d(c)
    a = math.radians(lp["yaw"])
    return (lp["x"] + far * math.cos(a), lp["y"] - far * math.tan(math.radians(lp["tilt"])),
            lp["z"] + far * math.sin(a))


# telephone poles along the crest (x, z, height m), the two either side of the car framing it; the line goes on off
# both sides of the world. Three wires of different sag run pole to pole, pink toward the sun.
POLES = [(-78.0, 36.0, 8.4), (-44.0, 33.0, 8.6), (-10.8, 31.0, 9.0), (10.6, 34.0, 9.2), (42.0, 37.0, 8.4),
         (75.0, 41.0, 8.8)]
HOT_POLE = 3               # the pole on the sun side (right of the car) catches the pink
WIRE_SAG = (0.15, 0.1, 0.06)       # each wire's sag, as a fraction of the span on screen
WIRE_Z = 26.0              # the wires' depth for the depth test (m): in front of the tree band


def pole_screen(k):
    """pole k on screen: its column (bx), foot and top rows, its width, and its two crossarms (row, half-length as a
    fraction of the arm, the insulators' columns); the wires hang from the top arm's three insulators"""
    x, z, h = POLES[k]
    g = float(terrain(x, z))
    bx, by = proj(x, g, z)
    _, ty = proj(x, g + h, z)
    k_ = float(ppm(z))
    arm = 2.1 * k_
    arms = [(int(round(ty + 0.5 * k_)), 0.5, [int(round(bx + f * arm)) for f in (-0.45, -0.15, 0.45)]),
            (int(round(ty + 1.3 * k_)), 0.3, [int(round(bx + -0.25 * arm))])]
    return dict(x=x, z=z, bx=bx, by=by, ty=ty, ppm=k_, arm=arm, arms=arms)


def wires():
    """the three wires between neighbouring poles as screen polylines (each one catenary-like sag), with the column
    past which they take the sun's pink"""
    tops = []
    for k in range(len(POLES)):
        ay, _, ins = pole_screen(k)["arms"][0]
        tops.append([(ix, ay - 1) for ix in ins])
    out = []
    for A, B in zip(tops[:-1], tops[1:]):
        span = abs(B[0][0] - A[0][0])
        for (xa, ya), (xb, yb), sag in zip(A, B, WIRE_SAG):
            out.append([(xa + (xb - xa) * t, ya + (yb - ya) * t + sag * span * 4 * t * (1 - t))
                        for t in np.linspace(0, 1, 160)])
    hot_x = proj(POLES[HOT_POLE][0], 0, POLES[HOT_POLE][1])[0] - 10
    return out, hot_x


CLEARING = (330, 452)      # core columns kept clear of the near spruce rows: the car stands against the burning rim
WINGS = [(-17.5, 26.0, 7.2), (-21.0, 28.5, 6.0), (16.6, 27.0, 6.4), (20.5, 29.0, 7.4)]   # two framing spruces each side,
                                                                                        # nearer, on the plateau


def tree_band(rng):
    """the spruce band behind the crest, edge to edge: a front row of tall dark spruces (spires grouped in stands,
    rounder low ones between), two lighter rows behind that fill every gap, and far small blue ones. Behind the car
    the band dips low, so the roof breaks the burning ridge rim. Returns (x, z, height) in metres."""
    trees = []
    for z0, gap, hlo, hhi, p_skip in ((35.0, 3.0, 4.6, 7.8, 0.0), (42.0, 2.7, 3.8, 6.0, 0.0),
                                      (50.0, 2.6, 3.2, 5.0, 0.0), (66.0, 3.2, 2.6, 3.8, 0.15)):
        x = -95.0 + rng.uniform(0, gap)
        while x < 95.0:
            z = z0 + rng.uniform(-2.5, 2.5)
            stand = 0.5 + 0.5 * math.sin(x * 0.21 + z0) * math.cos(x * 0.083 + 1.3)   # stands of spires
            h = hlo + (hhi - hlo) * float(np.clip(stand + rng.uniform(-0.35, 0.35), 0, 1))
            dip = math.exp(-((x + 3.6 * (z / 40.0)) / (5.5 * z / 40.0)) ** 2)      # behind the car
            if z0 < 60:
                h *= 1 - 0.62 * dip
            bx = X0 + x * F / (z + ZB) - CORE_X
            clear = CLEARING[0] < bx < CLEARING[1] and z0 < 60
            if rng.random() >= p_skip and h > 1.6 and not clear:
                trees.append((x, z, h))
            x += gap * rng.uniform(0.75, 1.2) * (h / ((hlo + hhi) / 2)) ** 0.5
    return trees


def spruces(seed=7):
    """every spruce in the picture as (x, z, height, depth class) and how many of them belong to the composed core: the
    core's band far to near and its framing pairs, then the wider world's band and its near spruces. The class picks
    the ramp (tn the near ones on the hill layer, then tm, tb, tf into the distance)."""
    core, wide = [], []
    for x, z, h in sorted(tree_band(np.random.default_rng(seed + 3)), key=lambda t: -t[1]):
        bx = proj(x, terrain(x, z), z)[0]
        if -60 <= bx <= W + 60:
            row = core if -60 <= bx - CORE_X <= CORE_W + 60 else wide
            row.append((float(x), float(z), float(h), "tf" if z > 60 else "tb" if z > 46 else "tm"))
    near = lambda ts: [(float(x), float(z), float(h), "tn") for x, z, h in ts]
    core += near(WINGS)
    return core + wide + near(NEAR_SPRUCES), len(core)


# ---------------------------------------------------------------- the wider world
# The composed picture (the core) was laid out first; the world past its edges came after, drawn from streams of its
# own or from the end of the shared one, so everything in the core stands where it stood.
RAKERS = [(-16.0, 6.6, 5.5, 0.7), (-17.0, 9.0, 5.5, 0.6), (-21.0, 12.2, 6.5, 1.0), (-23.0, 16.2, 6.5, 0.75),
          (-26.0, 21.6, 7.0, 1.2)]     # cones left of the core (x, z, height, radius): under a low side light their
                                       # shadows rake across the core's near snow (the rake pass); spruces stand on them
# near spruces on the wings, all past the near-field lens (z > LENS_ZS), so they keep the band's scale and tiers
NEAR_SPRUCES = [(-29.0, 13.6, 5.0), (-33.5, 18.6, 5.6), (-22.4, 12.4, 6.3), (-24.4, 16.4, 6.4), (-27.4, 21.8, 7.0),
                (-40.0, 15.5, 6.0), (27.5, 15.4, 4.8), (30.5, 12.6, 5.4), (37.8, 16.4, 6.6), (44.0, 18.0, 5.4)]
# snow pillows (x, z, r): soft domes in the open snow, the core's near-right group first
NEAR_PILLOWS = [(5.2, 7.7, 0.72), (7.5, 8.4, 0.85), (8.9, 6.9, 0.5),
                (-22.8, 7.6, 0.8), (-25.6, 9.2, 0.55), (-41.0, 14.8, 0.9), (-44.5, 17.6, 0.7),
                (13.6, 7.9, 0.62), (26.4, 11.0, 0.75), (34.6, 12.0, 0.9), (43.0, 15.6, 0.7)]
# the lip of drifts along the frame's bottom edge (from, to (x, z), thickness, height m, seed): either side of the stair
LIPS = [((-8.5, 4.55), (-1.0, 4.85), 0.8, 0.30, 11), ((3.0, 4.9), (9.5, 4.55), 0.8, 0.34, 12),
        ((-19.5, 5.3), (-10.5, 4.7), 0.8, 0.32, 13), ((11.0, 4.6), (19.5, 5.2), 0.8, 0.3, 14)]
# the old buried fence goes on along the left plateau's drift, and a short rope fence crosses the right slope
BURIED_MORE = [(-27.0, 13.4, 0.55), (-29.4, 14.0, 0.42), (-31.8, 14.6, 0.6), (-34.2, 15.2, 0.4)]
FIELD_FENCE = [(16.5, 9.2), (19.0, 10.0), (21.5, 10.9), (24.0, 11.9)]


# ---------------------------------------------------------------- the fence, the pillows, the walk
FENCE_STUBS = [(-10.4, 10.2, 0.62), (-8.2, 9.3, 0.44), (-6.1, 8.7, 0.56)]   # an old fence buried in the drift (x, z, ht)
POST_OFF = 1.5             # the rope fence stands this far either side of the stair's centre (m)
FOOT_GAPS = {7: 1.2, 9: 1.1}     # ropes (counted far to near along the stair) that sag into the snow by the foot,
                                  # so she can step off the stair from the start: their sag (m)
WALK_Z0 = 7.6              # the walk starts here, on the first stones of the climb (~15% above the frame bottom)
HOLD = (1.0, 0.55)         # where she stops: this far ahead of the car's nose and toward us (m), in the lamps' glow
FIG_H = 1.32               # her height (m)


def _hold():
    a = math.radians(CAR["yaw"])
    L = CS * CAR["L"] + HOLD[0]
    return (round(CAR["x"] + L * math.cos(a) + HOLD[1] * math.sin(a), 3),
            round(CAR["z"] + L * math.sin(a) - HOLD[1] * math.cos(a), 3))


END = _hold()


HERO = (0.4, 10.0, 21.0)   # the hero scale's growth and the depths (m) over which it grows


def hero(z):
    """a painter's figure scale: she is drawn a little larger as she nears the crest (x1 at the foot, x1.4 at the
    hold), so the hero beat by the car reads at ~28 px instead of shrinking to a speck"""
    k, z0, z1 = HERO
    return 1.0 + k * smooth(z0, z1, z)


def hold_screen():
    """her head on screen where she stops (the headlamps' glow in the air is centred on it)"""
    hx, hy = proj(END[0], float(terrain(*END)), END[1])
    return hx, hy - 0.85 * FIG_H * ppm(END[1]) * hero(END[1])


def _rope_runs(a, b, ya, yb, sag, n, clear):
    """a rope from (x, z) a to b, its ends at heights ya, yb (m), sagging by `sag` m, cut wherever it comes within
    `clear` m of the snow: a list of runs of (x, y, z) points"""
    (xa, za), (xb, zb) = a, b
    run, runs = [], []
    for t in np.linspace(0, 1, n):
        x, z = xa + (xb - xa) * t, za + (zb - za) * t
        y = ya * (1 - t) + yb * t - sag * 4 * t * (1 - t)
        if y < float(terrain(x, z)) + clear:
            if len(run) > 1:
                runs.append(run)
            run = []
            continue
        run.append((x, float(y), z))
    if len(run) > 1:
        runs.append(run)
    return runs


def _spend_on_cracks(rng, slabs):
    """the first painter drew a crack across each big stone here, and grass tufts below; neither is drawn any more,
    but their draws stay, so the pillows, posts and ropes drawn after them stand where the committed art has them"""
    for sb in sorted(slabs, key=lambda s: -s["cz"]):
        if sb["w"] * ppm(float(sb["cz"])) > 34:
            rng.uniform(size=9)


def _spend_on_grass(rng):
    tufts = [(rng.uniform(), rng.choice([-1, 1]), rng.uniform()) for _ in range(9)]
    for _ in range(len(tufts) + 2):
        for _ in range(int(rng.integers(3, 6))):
            rng.uniform(size=3)


_LAYOUT = {}


def layout(seed=7):
    """the scattered things of the place, from one seeded stream in a fixed order (change the order and everything
    after it moves). Built once per seed and shared: treat it as read-only. Returns a dict, all in metres:
        slabs, curve    the flagstones and the stair's centre line (stair_slabs)
        pillows         snow pillows (x, z, r): by the stones, at the fence stubs and at post feet
        posts           fence posts (x, z, thick, height, lean in px over its height): the buried fence, the rope
                        fence far to near, then the wider world's fences
        ropes           [(runs, z)]: each rope's runs of (x, y, z) points, and the depth it is drawn at
        trees           spruces(): (x, z, height, depth class), the first trees_core of them the composed core's"""
    if seed not in _LAYOUT:
        _LAYOUT[seed] = _layout(seed)
    return _LAYOUT[seed]


def _layout(seed):
    rng = np.random.default_rng(seed)
    slabs, curve = stair_slabs(rng)
    _spend_on_cracks(rng, slabs)
    # snow pillows: rounded mounds along the stair's edges, by about a third of the stones
    by_stones = []
    for sb in slabs:
        if rng.random() < 0.3:
            side = rng.choice([-1, 1])
            nx, nz = sb["tz"], -sb["tx"]
            o = sb["w"] / 2 + rng.uniform(0.3, 0.5)
            by_stones.append((sb["cx"] + side * o * nx, sb["cz"] + side * o * nz, rng.uniform(0.2, 0.3)))
    pillows = sorted(by_stones, key=lambda p: -p[1])
    _spend_on_grass(rng)
    ropes, posts = [], []
    _buried_fence(rng, FENCE_STUBS, posts, pillows, ropes)
    # the rope fence: posts on both sides of the stair, ropes sagging between their tops; two big posts in the
    # foreground, cut by the bottom corners of the frame, roped to the first posts of the stair
    s, cxs, czs = curve
    sides = {-1: [], 1: []}
    at = 2.6
    while at < s[-1] - 5.6:
        i = int(np.searchsorted(s, at))
        tx, tz = cxs[i + 1] - cxs[i - 1], czs[i + 1] - czs[i - 1]
        nrm = math.hypot(tx, tz)
        nx, nz = tz / nrm, -tx / nrm
        for side in (-1, 1):
            off = POST_OFF + rng.uniform(-0.06, 0.14)
            sides[side].append((cxs[i] + side * off * nx, czs[i] + side * off * nz))
        at += rng.uniform(2.5, 3.1)
    for fx, fz in [(float(path_x(Z_STAIR0 + 0.7)) - 2.5, Z_STAIR0 + 0.7), (float(path_x(Z_STAIR0 + 0.5)) + 2.3, Z_STAIR0 + 0.5)]:
        side = min(sides, key=lambda k: math.hypot(sides[k][0][0] - fx, sides[k][0][1] - fz))
        sides[side].insert(0, (fx, fz))
    items = []
    for side in (-1, 1):
        ps = sides[side]
        items += [("post", p) for p in ps] + [("rope", (a, b)) for a, b in zip(ps[:-1], ps[1:])]
    items.sort(key=lambda it: -(it[1][1] if it[0] == "post" else max(it[1][0][1], it[1][1][1])))   # far to near
    tops = {}
    for kind, p in items:
        if kind == "post":
            big = p[1] < Z_STAIR0 + 1.0
            ht = rng.uniform(0.95, 1.05) if big else rng.uniform(0.72, 0.98)
            lean = (rng.choice([-1, 1]) * rng.uniform(1.0, 2.2)) if big else rng.uniform(-1.6, 1.6)
            posts.append((p[0], p[1], 0.32 if big else 0.11, ht, lean))
            if big or rng.random() < 0.5:           # a pillow at its foot
                pillows.append((p[0] + rng.uniform(-0.1, 0.1), p[1] - 0.08, (0.36 if big else 0.2) * rng.uniform(0.9, 1.2)))
            tops[p] = ht - 0.16
    n_rope = 0
    for kind, p in items:
        if kind == "rope":
            a, b = p
            n_rope += 1
            sag = 0.68 if n_rope == 3 else rng.uniform(0.14, 0.38)        # one rope sags into the snow
            sag = FOOT_GAPS.get(n_rope, sag)      # and two by the foot sag low enough to step over (draws kept)
            ends = terrain(*a) + tops.get(a, 0.74), terrain(*b) + tops.get(b, 0.74)
            ropes.append((_rope_runs(a, b, *ends, sag, 48, 0.03), min(a[1], b[1]) + 0.05))
    # the wider world, from the end of the stream
    _buried_fence(rng, BURIED_MORE, posts, pillows, ropes)
    _field_fence(rng, FIELD_FENCE, posts, pillows, ropes)
    as_float = lambda t: tuple(float(v) for v in t)
    trees, n_core = spruces(seed)
    # the stair ends at the road's shoulder (its last stone in the trodden gap of the near ridge): the stones and
    # pillows the road was cut through are gone, dropped after the stream was drawn, so the rest stand where they stood
    slabs = [sb for sb in slabs if float(road_w(sb["cx"], sb["cz"])) < -ROAD_HW - sb["d"] / 2]
    pillows = [p for p in pillows if float(road_w(p[0], p[1])) < -ROAD_EDGE - p[2]]
    return dict(slabs=slabs, curve=curve, pillows=[as_float(p) for p in pillows], posts=[as_float(p) for p in posts],
                ropes=ropes, trees=trees, trees_core=n_core)


def _buried_fence(rng, stubs, posts, pillows, ropes):
    """an old fence buried in a drift: stubs (x, z, height) with a pillow at each foot, the rope between them half
    under the snow"""
    for (xa, za, ha), (xb, zb, hb) in zip(stubs[:-1], stubs[1:]):
        ends = terrain(xa, za) + ha - 0.06, terrain(xb, zb) + hb - 0.06
        ropes.append((_rope_runs((xa, za), (xb, zb), *ends, 0.42, 40, 0.02), min(za, zb) + 0.05))
    for x, z, ht in stubs:
        posts.append((x, z, 0.17, ht, rng.uniform(-1.2, 1.2)))
        pillows.append((x + 0.12, z - 0.1, 0.3))


def _field_fence(rng, pts, posts, pillows, ropes):
    """a run of rope fence posts (x, z) across open snow, roped top to top like the stair's"""
    tops = []
    for x, z in pts:
        ht = rng.uniform(0.72, 0.98)
        posts.append((x, z, 0.11, ht, rng.uniform(-1.6, 1.6)))
        if rng.random() < 0.5:
            pillows.append((x + rng.uniform(-0.1, 0.1), z - 0.08, 0.2 * rng.uniform(0.9, 1.2)))
        tops.append(ht - 0.16)
    for (a, ta), (b, tb) in zip(zip(pts, tops), zip(pts[1:], tops[1:])):
        ends = terrain(*a) + ta, terrain(*b) + tb
        ropes.append((_rope_runs(a, b, *ends, rng.uniform(0.14, 0.38), 48, 0.03), min(a[1], b[1]) + 0.05))


def walk_route(curve):
    """the auto-walk's route: up the stair's centre line onto the road's shoulder, then a few steps along the road
    to stand by the car's nose, as samples {s (m along), x, z}"""
    s, xs, zs = curve
    i0 = int(np.searchsorted(zs, WALK_Z0))
    i1 = int(np.searchsorted(zs, stair_top()[1]))
    route = [(xs[i], zs[i]) for i in range(i0, i1, 6)]
    ex, ez = route[-1]                                   # then onto the lane, curving to the car's nose
    tx, tz = END
    for t in np.linspace(0, 1, 40)[1:]:
        tt = t * t * (3 - 2 * t)
        route.append((ex + (tx - ex) * tt, ez + (tz - ez) * t))
    out, acc = [], 0.0
    for k, (x, z) in enumerate(route):
        if k:
            acc += math.hypot(x - route[k - 1][0], z - route[k - 1][1])
        out.append({"s": round(acc, 3), "x": round(float(x), 3), "z": round(float(z), 3)})
    return out


# ---------------------------------------------------------------- where she can walk
# The runtime walks her on the ground in metres: a grid of the ground's height, what it is underfoot, how far inside
# the walkable area each cell lies and how much of the headlamps' light falls there; plus the things she walks round.
WALK_D = 0.25                     # the grid's cell (m)
WALK_X, WALK_Z = (-64.0, 64.0), (4.0, 30.0)     # its extent (m): the whole canvas from the frame's foot to the trees
NEAR_ROW = VIEW_TOP + VIEW_H - 20   # her feet stay above this row, so the composed frame shows all of her
EDGE_PX = 28                      # and this far inside the canvas's sides
TREE_LINE = 29.0                  # and nearer than this (m): the tree band and the hill layer's far edge are beyond
ROWS_MIN = 1.5                    # past the crest the ground turns away: she stops where it climbs fewer rows per metre
CAR_REACH = 3.0                   # but round the car she walks wherever the ground is in sight (m)
ROOM_STEPS = 4                    # the walkable area's soft edge, in cells
ON_SNOW, ON_PATH, ON_STONE, ON_ROAD, ON_BANK = 0, 1, 2, 3, 4   # what is underfoot: deep snow, the trodden path, the
                                                               # flagstones, the road's packed lane, a plough ridge
PACE = {ON_SNOW: 0.7, ON_PATH: 1.0, ON_STONE: 1.0, ON_ROAD: 1.0, ON_BANK: 0.85}   # her pace on each (of a full stride)
PATH_W = 0.8                      # the trodden path's half width along the route (m)
STONE_GROW = 0.1                  # each flagstone's top reaches this far over its seam (m): no dips between stones
HOLD_R = 0.8                      # she stands at the hold within this of END (m)
TREE_R = 0.7                      # a near spruce blocks this much of its lowest tier's radius
PILLOW_BLOCK = 0.5                # snow pillows at least this big (radius, m) are walked round


_WALK = {}


def walk_grid(lay: dict) -> dict:
    """the walk grid (cells WALK_D across over WALK_X x WALK_Z, row-major from the near left): per cell the ground's
    height (m, the flagstones' tops on the stair), the surface (ON_*), room (0 outside the walkable area, up to 1 a
    soft edge inside it) and lamp (0..1, the headlamps' light on the ground). Computed once per layout (its arrays are
    read-only)."""
    if id(lay) not in _WALK:
        g = _walk_grid(lay)
        for v in g.values():
            if isinstance(v, np.ndarray):
                v.flags.writeable = False
        _WALK[id(lay)] = (lay, g)            # the layout is held, so its id stays its own
    return _WALK[id(lay)][1]


def _walk_grid(lay: dict) -> dict:
    xs = np.arange(WALK_X[0], WALK_X[1] + 1e-6, WALK_D)
    zs = np.arange(WALK_Z[0], WALK_Z[1] + 1e-6, WALK_D)
    X, Z = np.meshgrid(xs, zs)
    G = terrain(X, Z)
    surface = np.full(X.shape, ON_SNOW, np.uint8)
    route = walk_route(lay["curve"])
    rx, rz = np.array([q["x"] for q in route]), np.array([q["z"] for q in route])
    near_route = np.full(X.shape, np.inf)
    for k in range(0, len(rx), 50):                  # the distance to the route, in chunks
        d = np.hypot(X[..., None] - rx[None, None, k:k + 50], Z[..., None] - rz[None, None, k:k + 50]).min(-1)
        near_route = np.minimum(near_route, d)
    road = road_label(X, Z)
    surface[(road == ROAD_LANE) | (road == ROAD_RUT)] = ON_ROAD
    surface[road == ROAD_BANK] = ON_BANK
    surface[(near_route < PATH_W) | (road == ROAD_SHOULDER)] = ON_PATH
    for sb in lay["slabs"]:
        cx, cz = sb["cx"], sb["cz"]
        pts = [(cx + (x - cx) * k, cz + (z - cz) * k) for x, z in slab_outline(sb, 24)
               for k in [1 + STONE_GROW / max(math.hypot(x - cx, z - cz), 1e-3)]]
        on = _inside(X, Z, pts)
        hc = float(terrain(cx, cz))
        G = np.where(on, np.maximum(G, hc + 0.42 * (G - hc) + 0.12), G)
        surface[on] = ON_STONE
    room = _walkable(X, Z, G, near_route, route)
    lp = lamp3d()
    a = math.radians(lp["yaw"])
    lx, lz = lp["x"], lp["z"]
    dist = np.hypot(X - lx, Z - lz)
    ahead = ((X - lx) * math.cos(a) + (Z - lz) * math.sin(a)) / np.maximum(dist, 1e-3)
    lamp = np.maximum(smooth(math.cos(math.radians(42)), math.cos(math.radians(24)), ahead) * smooth(17.0, 7.0, dist),
                      smooth(2.8, 1.2, np.hypot(X - END[0], Z - END[1])))
    return dict(x0=float(xs[0]), z0=float(zs[0]), d=WALK_D, nx=len(xs), nz=len(zs), height=G, surface=surface,
                room=room, lamp=lamp)


def _inside(X, Z, pts):
    """the grid cells inside a polygon (even-odd ray casting)"""
    inside = np.zeros(X.shape, bool)
    for (xa, za), (xb, zb) in zip(pts, pts[1:] + pts[:1]):
        cross = (za > Z) != (zb > Z)
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = xa + (Z - za) * (xb - xa) / (zb - za)
        inside ^= cross & (X < xc)
    return inside


def _walkable(X, Z, G, near_route, route):
    """room per cell: inside the frame (her feet above NEAR_ROW, the canvas's sides), nearer than the tree line and
    short of the crest (where the ground climbs fewer than ROWS_MIN rows per metre, smoothed across), except along the
    route, round the hold, and on the road and round the car where the ground is in sight; the one piece she starts
    in, its edge softened over ROOM_STEPS cells"""
    sx, sy = proj(X, G, Z)
    ok = (sy <= NEAR_ROW) & (sx >= EDGE_PX) & (sx <= W - EDGE_PX) & (Z <= TREE_LINE)
    _, sy1 = proj(X, terrain(X, Z + WALK_D), Z + WALK_D)
    rows = (sy - sy1) / WALK_D                                   # rows climbed per metre
    k = int(round(1.5 / WALK_D))
    rows = np.cumsum(np.pad(rows, ((k, 0), (0, 0))), 0)
    rows = (rows[k:] - rows[:-k]) / k                            # averaged over the 1.5 m nearer
    climb = Z < Z_FOOT + 2
    for i in range(1, len(Z)):
        climb[i] |= climb[i - 1] & (rows[i] >= ROWS_MIN)
    zf = np.where(climb, Z, -np.inf).max(0)                      # the far bound per column, smoothed across
    zf = np.convolve(np.pad(zf, 6, mode="edge"), np.ones(13) / 13, mode="valid")
    c = car3d()
    a = math.radians(c["yaw"])
    u = (X - c["x"]) * math.cos(a) + (Z - c["z"]) * math.sin(a) - c["L"] / 2
    w = (X - c["x"]) * math.sin(a) - (Z - c["z"]) * math.cos(a)
    by_car = np.hypot(np.maximum(np.abs(u) - c["L"] / 2, 0), np.maximum(np.abs(w) - c["W"] / 2, 0)) < CAR_REACH
    D = raster_terrain()
    r, k = np.clip(np.round(sy).astype(int), 0, H - 1), np.clip(np.round(sx).astype(int), 0, W - 1)
    seen = np.abs(D[r, k] - Z) < np.maximum(0.6, 0.05 * Z)
    on_road = np.abs(road_w(X, Z)) < ROAD_EDGE
    hold = np.hypot(X - END[0], Z - END[1]) < 2.5
    ok &= (Z <= zf[None, :]) | (near_route < 1.5) | hold | ((by_car | on_road) & seen)
    start = (int(round((route[0]["z"] - WALK_Z[0]) / WALK_D)), int(round((route[0]["x"] - WALK_X[0]) / WALK_D)))
    ok = _piece(ok, start)
    room = ok.astype(np.float32)
    inner = ok
    for _ in range(ROOM_STEPS - 1):                              # each erosion is a step further inside
        p = np.pad(inner, 1)
        inner = inner & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
        room += inner
    return room / ROOM_STEPS


def _piece(m, seed):
    """the 4-connected piece of mask m holding the cell seed"""
    i, j = seed
    if not (0 <= i < m.shape[0] and 0 <= j < m.shape[1] and m[i, j]):
        return np.zeros_like(m)
    lab, _ = label4(m)
    return lab == lab[i, j]


# ---------------------------------------------------------------- grid helpers
def label4(mask: np.ndarray, val: np.ndarray = None):
    """the 4-connected components of a mask (with val: of its pixels with equal values, so each colour of a label
    image is cut into its own patches), vectorized union-find: every pair of joined neighbours hooks the larger root
    to the smaller, then the roots are compressed, until no pair differs. Returns a label per pixel (-1 outside the
    mask; 0.. numbered by each component's first pixel in raster order) and the number of components."""
    h, w = mask.shape
    idx = np.arange(h * w, dtype=np.int64).reshape(h, w)
    jr = mask[:, :-1] & mask[:, 1:]
    jd = mask[:-1] & mask[1:]
    if val is not None:
        jr &= val[:, :-1] == val[:, 1:]
        jd &= val[:-1] == val[1:]
    a = np.concatenate([idx[:, :-1][jr], idx[:-1][jd]])
    b = np.concatenate([a[:jr.sum()] + 1, a[jr.sum():] + w])
    parent = np.arange(h * w, dtype=np.int64)
    while len(a):
        pa, pb = parent[a], parent[b]
        ne = pa != pb
        a, b, pa, pb = a[ne], b[ne], pa[ne], pb[ne]
        if not len(a):
            break
        parent[np.maximum(pa, pb)] = np.minimum(pa, pb)      # roots hook to a smaller root: no cycles
        while True:
            pp = parent[parent]
            if np.array_equal(pp, parent):
                break
            parent = pp
    root = parent.reshape(h, w)
    u, inv = np.unique(root[mask], return_inverse=True)       # a component's root is its first pixel
    lab = np.full((h, w), -1, np.int64)
    lab[mask] = inv.ravel()
    return lab, len(u)


STEP_OVER = 0.4             # a rope lower than this over the snow (m) is stepped over; higher, it fences her in


def _high_spans(run):
    """the stretches of one rope run that hang higher than STEP_OVER over the snow, as ((x0, z0), (x1, z1)) pairs"""
    spans, cur = [], []
    for x, y, z in run:
        if y - float(terrain(x, z)) > STEP_OVER:
            cur.append((x, z))
            continue
        if len(cur) > 1:
            spans.append((cur[0], cur[-1]))
        cur = []
    if len(cur) > 1:
        spans.append((cur[0], cur[-1]))
    return spans


def walk_blocks(lay: dict) -> dict:
    """what she walks round, in metres: circles (x, z, r) for the posts, the near spruces' lowest boughs, the big snow
    pillows and the poles; segments (x0, z0, x1, z1) along every rope that hangs higher than STEP_OVER (lower, or
    sunk into the drift, she steps over it); the car as a box (centre x, z, yaw in degrees, half length, half width)"""
    r3 = lambda *v: [round(float(t), 3) for t in v]
    circles = [r3(x, z, t / 2) for x, z, t, _, _ in lay["posts"]]
    circles += [r3(x, z, TREE_R * (0.3 * h + 0.18)) for x, z, h, cls in lay["trees"] if cls == "tn"]
    circles += [r3(x, z, r * 1.1) for x, z, r in NEAR_PILLOWS if r >= PILLOW_BLOCK]
    circles += [r3(x, z, 0.16) for x, z, _ in POLES]
    segs = [r3(*a, *b) for runs, _ in lay["ropes"] for run in runs for a, b in _high_spans(run)]
    c = car3d()
    a = math.radians(c["yaw"])
    box = r3(c["x"] + c["L"] / 2 * math.cos(a), c["z"] + c["L"] / 2 * math.sin(a), c["yaw"], c["L"] / 2, c["W"] / 2)
    return dict(circles=circles, segs=segs, boxes=[box])
