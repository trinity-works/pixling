"""The painted view's 2D drawing on the art grid: what is drawn by hand around and over the Blender render.

paint3d.py renders the place (place.py) in Blender and steps it into the Hushfall ramps. A few things stay pixel
drawing, because a hand places them better than a renderer:

    the palette     PAL: every colour the layers use (the render's ramps pick from it too)
    the backdrop    the sky behind the clouds (sky_back), the far hill, ridges with the sun's rim and the mist (far)
    the props       fence posts (post), the poles with crossarms and insulators (poles), the ropes and wires as
                    1 px lines (lines): pixel sprites over the painted hill; their Blender copies only cast and catch
    the car         the hero sprite, drawn in its own pixel grid (car_sprite) and seated in the snow (paint_car)
    the lamp        the headlamps' light as a stepped field on the art grid (lamp_field)

Nothing is dithered: masses are flat tones cleaned to clusters, lines are 1 px and pixel-perfect.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import place as P
from .place import H, W

# ---------------------------------------------------------------- the palette
PAL = {
    # sky
    "sky_top": "#8c7c8c", "sage": "#839a8c", "sage_lo": "#8e9a8c", "sage_hi": "#95938f",
    "cl_lit": "#c2928e", "glow_low": "#c0928f",
    "hot": "#fc5084", "hot2": "#e46088", "hot_deep": "#ac567e",
    # far
    "ridge_far": "#7a8c96", "ridge_far_lo": "#6f8590", "ridge": "#5b6a80", "ridge_lo": "#526079",
    # spruces (far -> near rows tf, tb, tm, tn): body, snow shelf, sun-side snow, the shaded underside
    "tf0": "#4b5b76", "tf1": "#627389", "tf2": "#6b7d92", "tfu": "#45546f",
    "tb0": "#3a4664", "tb1": "#53637e", "tb2": "#5f718a", "tbu": "#323c59",
    "tm0": "#2e3755", "tm1": "#4a5a76", "tm2": "#576a84", "tmu": "#272e4a",
    "tn0": "#272c49", "tn1": "#44526f", "tn2": "#526481", "tnu": "#1f233b", "trunk": "#232842",
    # snow
    "sn_deep": "#4b5a7c", "sn_shade": "#5a7286", "sn_mid": "#607c8a", "sn": "#66858c", "sn_hi": "#6d8b93",
    "sn_lit": "#76929a", "sn_cap": "#90afa3", "sn_warm": "#86999b", "sn_glow": "#a0a39f",
    # stair
    "slab": "#45536f", "slab_lit": "#506080", "slab_lip": "#36435e", "riser": "#3e5479", "riser_dk": "#313c5e",
    # posts, ropes, poles, wires
    "wood": "#3a4060", "wood_lit": "#4f5a78", "wood_dk": "#262c48", "rope": "#3f4c67", "wire": "#2e3956",
    "wire_hot": "#e46088", "pole_hot": "#fc5084",
    # car
    "car_under": "#1c1830", "car_dk": "#262443", "car_lo": "#3a2e4e", "car": "#4a3858", "car_lit": "#5c4a6c",
    "car_rim": "#7c6684", "glass": "#5c5878", "glass_hi": "#77738e", "glass_dk": "#564e6e", "cargo": "#342c48",
    "warm_in": "#b08484", "tail_wrap": "#c06a8a", "rack": "#2e2a48", "chrome": "#887e80",
    "tyre": "#141a30", "tail": "#fc5084", "tail_core": "#f0b4c0", "lamp": "#e8f0d0", "load": "#3c4864",
    "load_lit": "#4c5878", "load_dk": "#283050",
    # light
    "mint0": "#6f9a90", "mint1": "#80b098", "mint2": "#b4d8ac", "peach": "#a0968e",
    # the lit snow on the spruce tiers, lighter and cooler with distance
    "tn3": "#62798c", "tm3": "#687f90", "tb3": "#6f8596", "tf3": "#768a99",
    # the sky: the cumulus one value step off the sage (a lighter face, a darker belly), the far clouds and the horizon
    # deck paler and closer to the sky, the salmon glow brightest on the sun side of the horizon
    "cl_base": "#6f6a86", "cl_shade": "#887a8e", "cl_hi": "#d4a296", "cl_crown": "#e4b6a4",
    "clf_lo": "#958a96", "clf": "#a8969a", "clf_hi": "#b9a3a0",
    "dk_base": "#7a7088", "dk_lo": "#93808e", "dk": "#b08c8e", "dk_hi": "#cc9c94",
    "glow_mid": "#b0948e", "glow_hi": "#d8a698", "far_hill": "#7c7c90", "far_hill_lo": "#74768c", "mist": "#8a9096",
    # the hero props in the low sun: a salmon rim on the poles and the car, pale insulators
    "pole_rim": "#a07c8a", "ins": "#9aa8b0", "ins_dk": "#56607c", "car_salmon": "#a87c8c", "car_salmon_hi": "#c8949a",
}


def rgb(h):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


C = {k: np.array(rgb(v), np.uint8) for k, v in PAL.items()}
SNOW_KEYS = ("sn", "sn_lit", "sn_shade", "sn_cap", "sn_mid", "sn_hi", "sn_warm", "sn_glow")


def tint(rgb_, col, a):
    """move colours toward palette colour `col` by a (0..1)"""
    a = np.asarray(a, np.float64)
    return np.round(rgb_.astype(np.float64) * (1 - a) + C[col].astype(np.float64) * a).astype(np.uint8)


# ---------------------------------------------------------------- a layer
class Layer:
    """one picture of the view: colour, coverage and depth (m) per pixel; s > 1 holds it s times the art size"""
    def __init__(self, s: int = 1):
        self.s = s
        self.rgb = np.zeros((H * s, W * s, 3), np.uint8)
        self.a = np.zeros((H * s, W * s), bool)
        self.z = np.full((H * s, W * s), np.inf, np.float32)

    def put(self, mask, col, z=None, slack=0.0):
        """paint `mask` in palette colour `col`, where nothing nearer than z (+ slack) is painted already"""
        m = mask.copy()
        if z is not None:
            m &= (z <= self.z + slack) if np.ndim(z) else (self.z + slack >= z)
        self.rgb[m] = C[col] if isinstance(col, str) else col
        self.a[m] = True
        if z is not None:
            self.z[m] = z[m] if np.ndim(z) else z
        return m

    def copy(self):
        c = Layer.__new__(Layer)
        c.s, c.rgb, c.a, c.z = self.s, self.rgb.copy(), self.a.copy(), self.z.copy()
        return c

    def save(self, path, optimize=False):
        im = np.dstack([self.rgb, (self.a * 255).astype(np.uint8)])
        Image.fromarray(im, "RGBA").save(path, optimize=optimize)


YS, XS = np.mgrid[0:H, 0:W].astype(np.float64)


def ellipse_mask(cx, cy, rx, ry):
    m = np.zeros((H, W), bool)
    rx, ry = max(rx, 0.5), max(ry, 0.5)
    x0, x1 = max(int(cx - rx) - 1, 0), min(int(cx + rx) + 2, W)
    y0, y1 = max(int(cy - ry) - 1, 0), min(int(cy + ry) + 2, H)
    if x1 <= x0 or y1 <= y0:
        return m
    ys, xs = np.mgrid[y0:y1, x0:x1]
    m[y0:y1, x0:x1] = ((xs + 0.5 - cx) / rx) ** 2 + ((ys + 0.5 - cy) / ry) ** 2 <= 1.0
    return m


def binary_open(m):
    """drop single pixels and 1 px whiskers from a mask (erode then dilate, 4-neighbour)"""
    p = np.pad(m, 1)
    er = p[1:-1, 1:-1] & ((p[:-2, 1:-1] & p[2:, 1:-1]) | (p[1:-1, :-2] & p[1:-1, 2:]))
    p = np.pad(er, 1)
    return m & (p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:])


def near_snow(L):
    """where a layer shows snow"""
    s = np.zeros(L.a.shape, bool)
    for t in SNOW_KEYS:
        s |= (L.rgb == C[t]).all(-1)
    return s


def line_pixels(pts):
    """a pixel-perfect 1 px polyline through screen points: one pixel per column for flat runs, one per row for steep
    ones, no doubled corners"""
    out = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            out.append((x0, y0))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy
    px = []                                  # dedupe, then drop L-corners (a pixel whose neighbours touch diagonally)
    for p in out:
        if not px or px[-1] != p:
            px.append(p)
    clean = [px[0]] if px else []
    for i in range(1, len(px) - 1):
        a, b, c = clean[-1], px[i], px[i + 1]
        if abs(a[0] - c[0]) == 1 and abs(a[1] - c[1]) == 1 and (b[0] == a[0] or b[1] == a[1]):
            continue
        clean.append(b)
    if len(px) > 1:
        clean.append(px[-1])
    return clean


# ---------------------------------------------------------------- label cleanups (paint3d and hd2d use these too)
def mode_clean(lab, n_iter=2, keep=None, need=2, redblack=True):
    """cluster cleanup on a label image: a pixel with fewer than `need` same-label 4-neighbours takes its most common
    neighbour label (the smallest on a tie). Repeated, this removes orphans and whiskers and rounds ragged edges into
    clusters. redblack: the two checkerboard halves in turn, so a 1 px checker collapses into one cluster instead of
    swapping (the render's cleanup); else every pixel at once (the drawn fields: the sky's bands, the lamp's steps).
    keep: pixels that never change."""
    lab = lab.copy()
    if redblack:
        par = (np.add.outer(np.arange(lab.shape[0]), np.arange(lab.shape[1])) % 2).astype(bool)
        halves = (par, ~par)
    else:
        halves = (None,)
    for _ in range(n_iter):
        changed = False
        for half in halves:
            p = np.pad(lab, 1, mode="edge")
            nb = np.stack([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])
            bad = (nb == lab[None]).sum(0) < need
            if half is not None:
                bad &= half
            if keep is not None:
                bad &= ~keep
            if not bad.any():
                continue
            best, bestc = lab.copy(), np.full(lab.shape, -1)
            for v in np.unique(nb[:, bad]):
                c = (nb == v).sum(0)
                upd = c > bestc
                best[upd], bestc[upd] = v, c[upd]
            lab[bad] = best[bad]
            changed = True
        if not changed:
            break
    return lab


def mode3(lab: np.ndarray, n: int = 1) -> np.ndarray:
    """a 3x3 mode filter: each pixel takes the label most of its 3x3 window holds (it keeps its own on a tie). Not an
    orphan cleanup like mode_clean (every pixel may move, diagonals count): on an upscaled art picture it turns the
    2 px staircases of its seams into fine painted edges."""
    for _ in range(n):
        p = np.pad(lab, 1, mode="edge")
        win = [p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
        best, bestc = lab.copy(), np.zeros(lab.shape, np.int16)
        for w in win:
            bestc += (w == lab)
        for v in np.unique(lab):
            c = np.zeros(lab.shape, np.int16)
            for w in win:
                c += (w == v)
            upd = c > bestc
            best[upd], bestc[upd] = v, c[upd]
        lab = best
    return lab


def vnoise(x, y, seed, cell):
    """smooth value noise, -1..1, with features about `cell` units across"""
    rng = np.random.default_rng(seed)
    g = rng.uniform(-1, 1, (257, 257))
    g[256], g[:, 256] = g[0], g[:, 0]       # the lattice wraps seamlessly (ix % 256): inputs left of 0 (the wide
                                            # canvas past the core's left edge) meet the core without a step
    fx, fy = x / cell, y / cell
    ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - ix, fy - iy
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    ix, iy = ix % 256, iy % 256
    a, b = g[iy, ix], g[iy, ix + 1]
    c, d = g[iy + 1, ix], g[iy + 1, ix + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


# ---------------------------------------------------------------- the backdrop: sky and far hills
SKY_BANDS = [96, 150, 200, 232, 254, 278]    # the sky's seams (art rows, before they wobble): sky_top .. glow_hi
VEIL = ((150, 166, 90), (300, 182, 70), (60, 214, 60), (240, 226, 46))   # the far veil's masses (core x, y, half-width)


def sky_back(rng, s: int = 1) -> Layer:
    """the sky behind the clouds: a vertical run from sky_top through sage down to the salmon glow at the horizon,
    the glow rising higher on the sun side (right) and behind the car, each seam wobbling a few px, cleaned to
    clusters; the brightest step (glow_hi) only low on the sun side. A far veil in the quiet upper left: a few long,
    flat masses of big dabs one step off the sage, so that quarter is not one flat field. s > 1 paints it s times
    finer (the hd2d look)."""
    L = Layer(s)
    if s > 1:
        Y, X = (np.mgrid[0:H * s, 0:W * s] + 0.5) / s - 0.5      # each fine pixel's art coordinate
    else:
        X, Y = XS, YS
    X = X - P.CORE_X                                             # in the composed core's columns
    ell = lambda cx, cy, rx, ry: ((X + 0.5 - cx) / rx) ** 2 + ((Y + 0.5 - cy) / ry) ** 2 <= 1.0
    n = vnoise(X, Y * 3, 71, 40.0)
    lift = 30 * np.clip((X - 520) / 300, 0, 1) ** 1.2 + 14 * np.exp(-((X - 420) / 80) ** 2)
    y = Y + 9 * n + lift * np.clip(Y / 300, 0, 1)
    lab = np.digitize(y, SKY_BANDS)
    veil = np.zeros_like(lab, bool)
    for cx, cy, wd in VEIL:
        for _ in range(int(wd / 7)):
            veil |= ell(cx + rng.uniform(-wd, wd) * 0.8, cy + rng.uniform(-6, 5), rng.uniform(8, 18), rng.uniform(3, 7))
    lab = np.where(veil & ((lab == 2) | (lab == 3)), 7, lab)          # inside the sage bands only
    lab = mode_clean(lab, 3 * s, redblack=False)
    for i, k in enumerate(["sky_top", "sage_hi", "sage", "sage_lo", "glow_mid", "glow_low", "glow_hi", "sage_hi"]):
        L.rgb[lab == i] = C[k]
    L.a[:] = True
    return L


RIM_WINDOWS = [(320, 500), (530, 600)]   # core columns where the sun's rim shows on the far ridge (behind the car,
                                         # a gap in the tree band), never as a line across the whole width


def ridges(rng, Z) -> Layer:
    """two far ridges just over the crest. The sun sits behind the far one: its rim burns hot pink, 2-4 px thick with
    a salmon step above, only inside RIM_WINDOWS"""
    L = Layer()
    cr = P.crest_rows(Z)[P.CORE_X:P.CORE_X + P.CORE_W]          # the ridges sit over the composed crest
    base_row = float(np.median(cr[(cr < H)]))
    cols = np.arange(W) - P.CORE_X * 1.0                      # in the composed core's columns
    for i, (col, lo, base, amp, freq, seed) in enumerate([
            ("ridge_far", "ridge_far_lo", base_row - 22, 14, 2.0, 3),
            ("ridge", "ridge_lo", base_row - 8, 8, 3.4, 7)]):
        n = vnoise(cols, np.zeros(W) + i * 40, seed, P.CORE_W / freq / 2.0)
        n2 = vnoise(cols, np.zeros(W) + 7, seed + 1, 14)
        top = np.round(base - amp * (0.6 + 0.5 * n) - 2.5 * n2).astype(int)
        lo_n = vnoise(cols, np.zeros(W) + 3.0, seed + 2, 10)
        for c in range(W):
            L.rgb[top[c]:, c] = C[col]
            L.a[top[c]:, c] = True
            L.rgb[top[c] + 5 + int(3 * lo_n[c]):, c] = C[lo]
        if i == 0:
            thick = 2 + np.round(1.5 + 1.5 * vnoise(cols, np.zeros(W) + 9, 31, 9)).astype(int)
            for xa, xb in RIM_WINDOWS:
                for c in range(xa + P.CORE_X, xb + P.CORE_X):
                    edge = min(c - xa - P.CORE_X, xb + P.CORE_X - c)   # the rim fades in and out in whole pixels
                    t = int(min(thick[c], 1 + edge // 6))
                    L.rgb[top[c]:top[c] + t, c] = C["hot"]
                    if t >= 3:
                        L.rgb[top[c] + t - 1, c] = C["hot2"]
                    if edge > 8:
                        L.rgb[top[c] - 1, c] = C["glow_low"]
                        L.a[top[c] - 1, c] = True
                        if thick[c] > 3 and edge > 16:
                            L.rgb[top[c] - 2, c] = C["glow_low"]
                            L.a[top[c] - 2, c] = True
    return L


RIM_FAR_END = 1000        # the far hill's rim runs on past the core's sun side this far (core columns), then stops


def far(rng, Z) -> Layer:
    """aerial depth between the sky and the spruces: a violet-grey far hill rolling above the tree band's base (it
    shows between the crowns), a 1 px hot rim on its crest on the sun side and behind the car, then the two nearer
    ridges, and a pale mist step along the foot of it all"""
    R = ridges(rng, Z)
    xs = np.arange(W) - P.CORE_X * 1.0                        # in the composed core's columns
    n = vnoise(xs, np.zeros(W) + 5, 83, 70.0)
    n2 = vnoise(xs, np.zeros(W) + 9, 84, 18.0)
    top = np.round(266 - 12 * n - 3 * n2 + 6 * np.exp(-((xs - 470) / 60) ** 2)).astype(int)
    L = Layer()
    for c in range(W):
        L.rgb[top[c]:, c] = C["far_hill"]
        L.a[top[c]:, c] = True
        L.rgb[top[c] + 6 + int(3 * n2[c]):, c] = C["far_hill_lo"]
        k = xs[c]
        if 560 < k < RIM_FAR_END or 340 < k < 480:    # the sun's rim on the crest: the sun side and behind the car
            L.rgb[top[c], c] = C["hot2" if (600 < k < RIM_FAR_END - 40 or 380 < k < 450) else "glow_hi"]
    L.rgb[R.a] = R.rgb[R.a]
    mt = np.round(290 + 4 * vnoise(xs, np.zeros(W) + 2, 85, 30.0)).astype(int)
    for c in range(W):                          # the mist: a pale band over the foot of the hills, behind the trees
        L.rgb[mt[c]:mt[c] + 9, c] = C["mist"]
        L.rgb[mt[c] + 9:mt[c] + 13, c] = tint(L.rgb[mt[c] + 9:mt[c] + 13, c], "mist", 0.5)
    L.z[L.a] = 9999.0
    return L


# ---------------------------------------------------------------- the props: posts, poles, ropes and wires
def post(L, x, z, thick, ht, lean):
    """a fence post: a 2-3 px stake (the big foreground ones ~15 px), leaning `lean` px over its height, a lit left
    edge, a round snow cap and a little drift at its foot. Built row by row, so the lean steps in whole-pixel runs."""
    h0 = float(P.terrain(x, z))
    bx, by = P.proj(x, h0, z)
    _, ty = P.proj(x, h0 + ht, z)
    w = max(2, int(round(thick * P.ppm(z))))
    y0, y1 = int(round(ty)), int(round(by))
    span = max(y1 - y0, 1)
    m = np.zeros((H, W), bool)
    lit = np.zeros((H, W), bool)
    dk = np.zeros((H, W), bool)
    gr = np.zeros((H, W), bool)
    nl, nd = max(1, w // 4), (max(1, w // 4) if w >= 3 else 0)
    for y in range(max(y0, 0), min(y1 + 1, H)):
        xo = int(round(bx - w / 2 + lean * (y1 - y) / span))
        a, b = max(xo, 0), min(xo + w, W)
        if b <= a:
            continue
        m[y, a:b] = True
        lit[y, max(xo, 0):max(min(xo + nl, W), 0)] = True
        if nd:
            dk[y, max(xo + w - nd, 0):b] = True
        if w >= 8 and y0 + w <= y < y1 - w // 2 and 0 <= xo + w // 2 < W:
            gr[y, xo + w // 2] = True            # a grain line down the big posts
    L.put(m, "wood", z, slack=0.6)
    mine = L.z == np.float32(z)
    L.rgb[m & lit & mine] = C["wood_lit"]
    L.rgb[m & dk & mine] = C["wood_dk"]
    L.rgb[m & gr & mine] = C["wood_dk"]
    x0 = int(round(bx - w / 2 + lean))
    rx = w / 2 + 0.9                             # a round snow cap (a dome on the big posts)
    if w >= 6:
        cap = ellipse_mask(x0 + w / 2, y0 + 1, rx, rx * 0.8) & (YS <= y0 + 1.5)
    else:
        cap = ellipse_mask(x0 + w / 2, y0 + 0.2, rx, max(1.2, rx * 0.65)) & (YS <= y0 + 0.5)
        cap |= ellipse_mask(x0 + w / 2, y0 + 0.5, rx, max(1.0, rx * 0.55)) & (YS >= y0 - 1) & (YS <= y0)
    L.put(cap, "sn_lit", z - 0.01, slack=0.6)
    L.rgb[cap & (XS < x0 + w / 2) & (YS < y0) & (L.z == np.float32(z - 0.01))] = C["sn_cap"]
    foot = ellipse_mask(x0 + w / 2, y1 + 0.5, w / 2 + 1.5, max(1.0, w * 0.35)) & (YS <= y1 + 0.5)
    L.put(foot & (L.z >= z - 0.3), "sn", z - 0.01, slack=0.6)


def lines(place) -> list:
    """the ropes (place['ropes']) and the wires (place.wires) as 1 px lines: [{z, px: [(x, y, palette key)]}]"""
    out = []
    for runs, z in place["ropes"]:
        for run in runs:
            out.append(dict(z=float(z), px=[(x, y, "rope") for x, y in line_pixels([P.proj(*q) for q in run])]))
    spans, hot_x = P.wires()
    for pts in spans:
        out.append(dict(z=P.WIRE_Z, px=[(x, y, "wire_hot" if x > hot_x else "wire") for x, y in line_pixels(pts)]))
    return out


def props(hill: Layer, place, lines_: list, rec: dict) -> None:
    """posts, ropes and poles as pixel sprites over the painted hill (the Blender copies only cast and catch light):
    every fence post 2-3 px with a lit and a dark side, its lean, a round snow cap and a snow collar at its foot; the
    ropes and wires laid as 1 px lines; the poles with a salmon rim on the sun side, a two-row crossarm with 2 px
    insulators and the hot pink glint up the sun-side pole. rec keeps what the lines covered (hd2d relays them)."""
    pl = Layer()
    for x, z, thick, ht, lean in place["posts"]:
        post(pl, x, z, thick, ht, lean)
    wood = (pl.rgb == C["wood"]).all(-1) & pl.a
    right_open = ~np.roll(wood | (pl.rgb == C["wood_lit"]).all(-1), -1, axis=1)
    pl.rgb[wood & right_open] = C["wood_dk"]
    m = pl.a & (pl.z <= hill.z + 0.6)
    hill.rgb[m], hill.a[m], hill.z[m] = pl.rgb[m], True, pl.z[m]
    rec["zpre"], rec["rgbpre"] = hill.z.copy(), hill.rgb.copy()
    for ln in lines_:
        z = ln["z"]
        for x, y, col in ln["px"]:
            if 0 <= x < W and 0 <= y < H and z <= hill.z[y, x] + 0.3:
                hill.rgb[y, x] = C[col]
                hill.a[y, x] = True
                hill.z[y, x] = z
    rec["lines"] = (hill.rgb != rec["rgbpre"]).any(-1) | (hill.z != rec["zpre"])
    rec["after"] = hill.copy()
    for k in range(len(P.POLES)):
        poles(hill, k)


POLE_HOT_TOP, POLE_HOT_DEEP = 0.3, 0.45    # the sun-side pole's pink glint: hot down this far, then the deep pink


def poles(hill: Layer, k: int) -> None:
    """telephone pole k: 3 px, a salmon rim on its sun side, two crossarms with 2 px insulators, a snow collar"""
    p = P.pole_screen(k)
    bx, by, ty, z = p["bx"], p["by"], p["ty"], p["z"]
    w = max(3, int(round(0.3 * p["ppm"])))
    x0 = int(round(bx - w / 2))
    y0, y1 = int(ty), int(by) + 1
    hot = k == P.HOT_POLE
    L = Layer()
    L.rgb[y0:y1, max(x0, 0):max(x0 + w, 0)] = C["wood_dk"]
    L.a[y0:y1, max(x0, 0):max(x0 + w, 0)] = True
    if 0 <= x0 < W:
        L.rgb[y0:y1, x0] = C["pole_rim"]
        if hot:
            L.rgb[y0:int(ty + (by - ty) * POLE_HOT_TOP), x0] = C["pole_hot"]
            L.rgb[int(ty + (by - ty) * POLE_HOT_TOP):int(ty + (by - ty) * POLE_HOT_DEEP), x0] = C["hot_deep"]
    if 0 <= x0 + 1 < W and w >= 3:
        L.rgb[y0:y1, x0 + 1] = C["wood"]
    for ay, f, ins in p["arms"]:
        xa, xb = int(bx - p["arm"] * f), int(bx + p["arm"] * f) + 1
        xa, xb = min(max(xa, 0), W), min(max(xb, 0), W)
        L.rgb[ay:ay + 2, xa:xb] = C["wood_dk"]
        L.a[ay:ay + 2, xa:xb] = True
        L.rgb[ay, xa:xb] = C["pole_hot" if hot and f == 0.5 else "pole_rim"]
        for ix in ins:
            if 0 <= ix < W:
                L.rgb[ay - 2, ix], L.rgb[ay - 1, ix] = C["ins"], C["ins_dk"]
                L.a[ay - 2:ay, ix] = True
    foot = ellipse_mask(bx, by + 0.5, w + 2, 1.8) & (YS <= by + 0.5)
    L.rgb[foot] = C["sn_lit"]
    L.a |= foot
    L.rgb[foot & ~np.roll(foot, 1, 0)] = C["sn_cap"]
    m = L.a & (z <= hill.z + 0.5)
    hill.rgb[m], hill.a[m], hill.z[m] = L.rgb[m], True, np.float32(z)


def pole_x() -> int:
    """the screen column of the sun-side pole (the one right of the car)"""
    x, z, h = P.POLES[P.HOT_POLE]
    return int(round(P.proj(x, float(P.terrain(x, z)), z)[0]))


# ---------------------------------------------------------------- the car (rear three-quarter, nose away right)
# The car is the hero, so it is drawn the way a pixel artist draws a hero sprite: by hand, in its own pixel grid, one
# cluster at a time (a rounded old estate seen from its rear three-quarter at eye level, about as tall as she is), then
# repainted to the low sun behind it and placed once at its spot on the road. Design coordinates: x across (the rear
# face 0..20, the flank 20..85 receding to the right), y down, the rear tyre touching the ground at CAR_DESIGN_FOOT.
CAR_SPRITE = {  # index -> palette key
    1: "tyre", 2: "car_under", 3: "car_dk", 4: "car_lo", 5: "car", 6: "car_lit", 7: "car_rim", 8: "glass",
    9: "glass_hi", 10: "cargo", 11: "warm_in", 12: "tail", 13: "tail_core", 14: "chrome", 15: "load", 16: "load_lit",
    17: "load_dk", 18: "sn_lit", 19: "sn_cap", 20: "wood_dk", 21: "lamp", 22: "rack", 23: "tail_wrap",
    # the repaint to the low sun (car_sprite)
    24: "car_salmon", 25: "hot_deep", 26: "sn_lit", 27: "sn_cap", 28: "car_salmon_hi", 29: "sn", 30: "sn_shade",
}
CAR_GRID = (92, 44, 2, 2)   # the sprite's grid: width, height and the design origin in it
CAR_WHEELS = ((27.0, 35.0, 4.5, 4.5), (75.0, 34.5, 3.5, 4.0))   # the rear and the front wheel: centre, radii
CAR_TAILS, CAR_TAIL_Y = ((1, 5), (15, 19)), 23   # the tail lights' columns, their top row (they are 2 rows)
CAR_LAMP = (84, 25)         # the headlamp on the nose
CAR_DESIGN_FOOT = (27, 39)  # the rear tyre's contact (place.CAR_AT) in the design grid
CAR_GROUND = (39.5, 38.5)   # the ground line under the rear face and under the nose (design rows)
CAR_LIFT = 1                # a painter's cheat: set back a pixel on the lane, so its banks and bloom have snow to
                            # lie on


def _car_drawing():
    """the estate as drawn: body, glass, the packed cargo, tail lights, wheels, the roof rack and its snowy load"""
    SW, SH, OX, OY = CAR_GRID
    im = Image.new("L", (SW, SH), 0)
    d = ImageDraw.Draw(im)
    P_ = lambda pts: [(x + OX, y + OY) for x, y in pts]
    E = lambda cx, cy, rx, ry: [cx - rx + OX, cy - ry + OY, cx + rx + OX, cy + ry + OY]
    R = lambda x0, y0, x1, y1, c: d.rectangle([x0 + OX, y0 + OY, x1 + OX, y1 + OY], fill=c)
    # the flank (behind the rear face): the lower body with a long round nose, the cabin's domed roof to the windscreen
    d.polygon(P_([(20, 20), (78, 20), (82, 21), (84, 23), (85, 26), (85, 30), (83, 32), (78, 33), (22, 34),
                  (20, 34)]), fill=4)
    d.polygon(P_([(19, 20), (19, 12), (21, 10), (24, 10), (46, 10), (51, 11), (55, 14), (60, 18), (63, 20)]), fill=4)
    # the rear: the cabin's rounded back and the tail panel, one value lighter than the flank
    d.polygon(P_([(1, 20), (2, 14), (3, 12), (5, 11), (8, 10), (17, 10), (19, 11), (20, 13), (20, 20)]), fill=5)
    d.rounded_rectangle([0 + OX, 19 + OY, 20 + OX, 33 + OY], radius=3, fill=5)
    # the rounded rear corner catches the sky: one lit column where the rear turns into the flank
    d.line(P_([(20, 13), (20, 31)]), fill=6)
    # glass, one value above the body: the rear window, the quarter light, the door glass (pillars between), the sky
    # along their tops
    d.rounded_rectangle([4 + OX, 12 + OY, 17 + OX, 18 + OY], radius=2, fill=8)
    d.polygon(P_([(21, 18), (21, 13), (23, 12), (33, 12), (33, 18)]), fill=8)
    d.polygon(P_([(36, 18), (36, 12), (45, 12), (50, 13), (55, 18)]), fill=8)
    for x0, x1 in ((5, 16), (23, 33), (36, 46)):
        R(x0, 12, x1, 12, 9)
    # the estate is packed for the move: boxes low in the rear window and the quarter light
    R(5, 15, 9, 18, 10)
    R(10, 16, 16, 18, 10)
    R(22, 16, 26, 18, 10)
    R(27, 17, 33, 18, 10)
    # a warm sliver through the front glass: the headlamps' snow seen through the car
    d.polygon(P_([(51, 18), (52, 16), (53, 16), (55, 18)]), fill=11)
    # the body below the glass: a lit shoulder crease, the door seam and handle, the dark sill, the bumper and plate
    d.line(P_([(21, 20), (77, 20)]), fill=6)
    d.polygon(P_([(21, 31), (80, 30), (79, 33), (21, 34)]), fill=3)
    d.line(P_([(35, 21), (35, 30)]), fill=3)
    d.line(P_([(38, 22), (39, 22)]), fill=14)
    R(0, 30, 20, 33, 3)
    d.line(P_([(1, 30), (19, 30)]), fill=4)
    R(8, 26, 12, 27, 14)
    # tail lights: pink bars with a pale core, the outer one wrapping the corner
    for x0, x1 in CAR_TAILS:
        R(x0, CAR_TAIL_Y, x1, CAR_TAIL_Y + 1, 12)
        R(x0, CAR_TAIL_Y, x0 + 1, CAR_TAIL_Y, 13)
    d.point((20 + OX, CAR_TAIL_Y + OY), fill=23)
    # the headlamp on the round nose, the front bumper
    R(CAR_LAMP[0] - 1, CAR_LAMP[1] - 1, CAR_LAMP[0], CAR_LAMP[1], 21)
    d.line(P_([(80, 31), (84, 30)]), fill=14)
    # the rear wing bulges over its wheel (a lit arc); arches, tyres, hubs; a dark crease low along the flank
    for (cx, cy, rx, ry), wing in zip(CAR_WHEELS, (True, False)):
        if wing:
            d.arc(E(cx, cy, rx + 2.5, ry + 2.5), 205, 335, fill=6)
        d.pieslice(E(cx, cy, rx + 1.5, ry + 1.5), 180, 360, fill=2)
        d.ellipse(E(cx, cy, rx, ry), fill=1)
        d.ellipse(E(cx + 0.3, cy, rx * 0.4, ry * 0.4), fill=3)
    d.line(P_([(40, 28), (66, 28)]), fill=3)
    # the roof rack: two rails on three feet
    d.line(P_([(5, 7), (46, 7)]), fill=20)
    d.line(P_([(5, 8), (46, 8)]), fill=22)
    for x in (7, 26, 44):
        d.point((x + OX, 9 + OY), fill=20)
    # the load: one lumpy bundle under a tarp, lashed with two straps, dark underneath
    for cx, cy, rx, ry in ((13, 4.5, 6.5, 2.0), (25, 3.8, 7.5, 2.8), (37, 4.5, 6.0, 2.0), (43, 5.0, 3.5, 1.4)):
        d.ellipse(E(cx, cy, rx, ry), fill=15)
    R(7, 5, 46, 6, 15)
    a = np.array(im)
    load = a == 15
    for x in range(SW):
        col = np.nonzero(load[:, x])[0]
        if len(col):
            a[col.max(), x] = 17
    for x in (19, 32):
        col = np.nonzero(load[:, x + OX])[0]
        a[col.min() + 1:col.max() + 1, x + OX] = 17
    # its snow cap: thick on the lumps and heaped a pixel over their tops, a lighter top row on the sky side
    snow = np.zeros_like(load)
    for x in range(SW):
        col = np.nonzero(load[:, x])[0]
        t = x - OX
        if len(col) and 8 <= t <= 44:
            k = int(round(1.6 + 1.0 * math.exp(-((t - 25) / 8) ** 2) + 0.9 * math.exp(-((t - 13) / 4) ** 2)
                          + 0.7 * math.exp(-((t - 37) / 3.5) ** 2)))
            up = 1 if (19 <= t <= 30 or 11 <= t <= 15) else 0
            snow[col.min() - up:col.min() + k, x] = True
    a[snow] = 18
    for x in range(SW):
        col = np.nonzero(snow[:, x])[0]
        if len(col) and x - OX < 36:
            a[col.min(), x] = 19
    for x in range(SW):                                    # the load's lit top edge where no snow lies
        col = np.nonzero(load[:, x] & ~snow[:, x])[0]
        if len(col) and not snow[:, x].any():
            a[col.min(), x] = 16
    # the lit roof edge: one pixel along every top edge of the body that meets the sky (or the load)
    body = (a >= 3) & (a <= 6)
    above = np.roll(a, 1, axis=0)
    a[body & ((above == 0) | ((above >= 15) & (above <= 19)))] = 7
    return a, (OX, OY)


def car_sprite():
    """the hand-drawn estate repainted to the painted scene's light: a salmon rim along the roof and the rear
    silhouette (the low sun behind), the roof load's snow in three steps with a drip edge, snow on the hood and the
    sill, dark hubs with one catch-light, a 1 px hot halo round the tail lights. Returns (index grid, design origin);
    CAR_SPRITE maps the indices to palette keys."""
    a, (OX, OY) = _car_drawing()
    hgt, wid = a.shape
    body = (a >= 3) & (a <= 7)
    a[a == 7] = 28                                         # the roof's lit edge: the sun's salmon
    for y in range(11 + OY, 30 + OY):                      # the rear silhouette (its left edge), upper body
        xs = np.nonzero(a[y] > 0)[0]
        if len(xs) and body[y, xs[0]]:
            a[y, xs[0]] = 24
    # the roof load's snow: cap / lit / a shaded bottom row, and drips hanging off its lower edge
    snow = (a == 18) | (a == 19)
    for x in range(wid):
        col = np.nonzero(snow[:, x])[0]
        if len(col) >= 3:
            a[col.max(), x] = 29
        if len(col) and (x - OX) % 5 == 1 and 9 <= x - OX <= 42 and col.max() + 1 < hgt \
                and a[col.max() + 1, x] in (15, 16, 17):
            a[col.max() + 1, x] = 26
    # snow on the hood: a lumpy cap along the flank's top from the windscreen foot to the nose
    for x in range(61 + OX, 83 + OX):
        col = np.nonzero(body[:, x])[0]
        if not len(col):
            continue
        t = col.min()
        k = 1 + int(((x - OX) % 6) in (2, 3))
        for j in range(k):
            if t - 1 - j >= 0:
                a[t - 1 - j, x] = 27 if j == k - 1 else 26
    # snow on the sill between the wheels: one lit row on the dark sill
    for x in range(34 + OX, 68 + OX):
        col = np.nonzero(a[29 + OY:, x] == 3)[0]
        if len(col):
            a[29 + OY + col.min(), x] = 26
    # the hubs: dark discs in the tyres, one 1 px catch-light on the rim's sun side (no light glyph)
    for hx, hy, _, _ in CAR_WHEELS:
        cx, cy = int(round(hx + OX)), int(round(hy + OY))
        win = a[cy - 2:cy + 3, cx - 2:cx + 3]
        win[(win == 28) | (win == 14) | (win == 7)] = 3
        ys, xs = np.nonzero(win == 3)
        if len(ys):
            i = np.lexsort((xs, ys))[0]
            win[ys[i], xs[i]] = 14
    # the tail lights' halo: body pixels touching a light take the deep hot pink
    tl = (a == 12) | (a == 13) | (a == 23)
    near = np.zeros_like(tl)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            near |= np.roll(np.roll(tl, dy, 0), dx, 1)
    a[near & ~tl & ((a >= 3) & (a <= 6) | (a == 24))] = 25
    return a, (OX, OY)


def paint_car(L: Layer, sprite) -> dict:
    """the hero sprite placed once on the road's near half and seated in it: a blue contact pool under the sills, a
    little snow banked at the tyres with lit crowns (pink-lit by the tail lights at the rear), the tail lights' pink
    on the snow behind it as a soft two-step bloom and on the bumper as a blush. Returns its screen anchors (the lamp,
    the tail lights, the exhaust, the ground line) and depth."""
    a, (OX, OY) = sprite
    g = float(P.terrain(*P.CAR_AT))
    ax, ay = P.proj(P.CAR_AT[0], g, P.CAR_AT[1])
    ox = int(round(ax)) - CAR_DESIGN_FOOT[0] - OX            # screen = design + (ox + OX, oy + OY)
    oy = int(round(ay)) - CAR_DESIGN_FOOT[1] - OY - CAR_LIFT
    zc = P.CAR_AT[1] + 0.6
    S = lambda dx, dy: (ox + OX + dx, oy + OY + dy)
    body = np.zeros((H, W), bool)
    sh, sw = a.shape
    sub = (slice(max(oy, 0), min(oy + sh, H)), slice(max(ox, 0), min(ox + sw, W)))
    asub = a[sub[0].start - oy:sub[0].stop - oy, sub[1].start - ox:sub[1].stop - ox]
    body[sub] = asub > 0
    put = lambda m, col, dz=0.0: L.put(m, col, zc + dz, slack=0.8)
    for k, col in CAR_SPRITE.items():
        m = np.zeros((H, W), bool)
        m[sub] = asub == k
        put(m, col)
    nose = CAR_LAMP[0] + 1
    ground = lambda dx: CAR_GROUND[0] + (CAR_GROUND[1] - CAR_GROUND[0]) * dx / nose

    def band(x0, x1, ry):
        m = np.zeros((H, W), bool)
        for t in np.linspace(0, 1, 16):
            cx, cy = S(x0 + (x1 - x0) * t, ground(x0 + (x1 - x0) * t))
            m |= ellipse_mask(cx, cy, (x1 - x0) / 15 + 2, ry)
        return m
    # the contact pool: the ground seen under the sills in the car's own shade, a blue shade under the whole car on
    # the snow, darkest right under the sill between the tyres
    under = np.zeros((H, W), bool)
    for dx in range(-1, nose + 1):
        x_, y0_ = S(dx, 33.5 - dx / nose)
        _, y1_ = S(dx, ground(dx))
        under[int(y0_):int(y1_) + 1, int(x_)] = True
    L.put(under & ~body, "sn_shade", zc + 0.3, slack=0.8)
    snow = near_snow(L) & ~body
    L.rgb[band(-2, nose + 1, 1.8) & snow] = C["sn_shade"]
    L.rgb[(band(31, 71, 1.2) | band(-1, 20, 0.9)) & snow] = C["sn_deep"]
    # a little snow banked at the tyres: a lump either side of each, a lit crown on each lump
    bank = np.zeros((H, W), bool)
    for (cx, _, rx, _), w in zip(CAR_WHEELS, (1.0, 0.8)):
        for dx, r in ((-rx - 1.0, 2.6), (rx + 1.2, 2.2), (0.0, rx + 0.5)):
            x_, y_ = S(cx + dx * w, ground(cx) + 0.5)
            bank |= ellipse_mask(x_, y_, r * w, 1.5 * w)
    bank = binary_open(bank)
    put(bank, "sn_lit", -0.3)
    bk = bank & (L.z == np.float32(zc - 0.3))
    crown = bk & ~np.roll(bank, 1, axis=0)
    L.rgb[crown] = C["sn_glow"]
    L.rgb[bk & ~np.roll(bank, -1, axis=0)] = C["sn"]               # each lump's shaded foot
    # the tail lights' pink: a soft two-step bloom on the snow behind the rear (flat steps, clean round edges), a
    # thin pink rim on the crowns under the lights, and a blush on the bumper and the paint round each bar
    snow = near_snow(L) & ~body
    cx, cy = S(10, CAR_GROUND[0])
    outer = ellipse_mask(cx - 3, cy + 1, 17, 3.2) & (YS >= cy - 2)
    inner = ellipse_mask(cx - 1, cy, 10, 2.0) & (YS >= cy - 2)
    L.rgb[outer & snow] = tint(L.rgb[outer & snow], "hot", 0.16)
    L.rgb[inner & snow] = tint(L.rgb[inner & snow], "hot", 0.3)
    rim = crown & (XS < S(22, 0)[0])
    L.rgb[rim] = tint(L.rgb[rim], "hot", 0.45)
    for x0, x1 in CAR_TAILS:
        halo = np.zeros((H, W), bool)
        (hx0, hy0), (hx1, hy1) = S(x0 - 1, CAR_TAIL_Y - 1), S(x1 + 1, CAR_TAIL_Y + 2)
        halo[int(hy0):int(hy1) + 1, int(hx0):int(hx1) + 1] = True
        for col in ("car", "car_lo", "car_lit"):
            m = halo & body & (L.rgb == C[col]).all(-1)
            L.rgb[m] = tint(L.rgb[m], "hot", 0.28)
        (bx0, by0), (bx1, _) = S(x0, 31), S(x1, 31)
        bm = np.zeros((H, W), bool)
        bm[int(by0):int(by0) + 2, int(bx0):int(bx1) + 1] = True
        bm &= body
        L.rgb[bm] = tint(L.rgb[bm], "hot", 0.3)
    tails = [tuple(int(round(v)) for v in S((x0 + x1) / 2, CAR_TAIL_Y)) for x0, x1 in CAR_TAILS]
    lamp = tuple(int(round(v)) for v in S(*CAR_LAMP))
    ex = tuple(int(round(v)) for v in S(5, 33))
    (gx0, gy), (gx1, _) = S(0, CAR_GROUND[0]), S(nose, CAR_GROUND[1])
    return dict(z=zc, tail=tails[0], tails=tails, lamp=lamp, exhaust=ex, gx0=int(gx0), gx1=int(gx1), gy=int(gy),
                wc=float(gx1 - gx0))


# ---------------------------------------------------------------- the headlamps' light
def lamp_field(car):
    """the headlamps' light as a step field 0..3: a low dome rising off the snow ahead of the nose (brightest at the
    bumper, longest along the ground), the lamp's own spot, and a round glow in the air where she stops, so her dark
    hood stands against light. Seams wobble at a few px and are cleaned into clusters: flat steps, never dither."""
    lx, ly = car["lamp"]
    hx, hy = P.hold_screen()
    dx = XS + 0.5 - lx - 15
    dome = np.clip(1 - np.hypot(dx / np.where(dx > 0, 64.0, 22.0), (YS + 0.5 - ly - 15) / 16.0), 0, 1) ** 0.75
    nose = np.clip(1 - np.hypot((XS + 0.5 - lx - 2) / 8.0, (YS + 0.5 - ly - 3) / 5.0), 0, 1) ** 0.8
    air = np.clip(1 - np.hypot((XS + 0.5 - hx - 3) / 17.0, (YS + 0.5 - hy - 2) / 13.0), 0, 1) ** 0.9
    b = np.maximum(np.maximum(dome, nose), 0.85 * air)
    b = b + (vnoise(XS, YS, 47, 7.0) - 0.5) * 0.12 * (b > 0.05)
    lab = np.digitize(b, [0.14, 0.4, 0.68]).astype(np.int8)
    return mode_clean(lab, 4, redblack=False)
