"""The hd2d look (the default): a painted world, pixel actors.

The world layers stay at the render's own size (s = 2 or 3 x the art, one screen pixel each at 720p or 1080p): every
material's lit value is stepped into its ramp per render pixel (crisp toon bands, no block mode) and only true orphan
specks are cleaned. What paint3d.pixelize drew over the render on the art grid (posts, poles, the car and its contact,
the lamp's glints) comes back on top as s x s art pixels, the ropes and wires refitted, the lamp's and the tail
lights' light re-applied as tints with fine seams. The runtime (web/layers.js) draws hd_*.png (2x) or hd3_*.png (3x)
under its art-pixel actors: the walker, snow, breath, exhaust.

Lessons (v4): the raw render is the target, so when in doubt do less to it; every cleanup that merges dabs (blur,
wide mode filters, big blob absorbs) costs the painterly read. Pixel accents belong on things (actors, props, wires).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import draw2d as D
from . import place as P
from .draw2d import mode3
from .paint3d import (KIDX, LAYERS, MAT, PALRGB, SEED, SNOWY, classify, clean, components, contact, lantern_ring,
                      load_raw, min_rows, pixelize, rim_lip, stair_craft, to_layer, trees_air)

# the fine cleanup per layer (passes, same-colour neighbours a pixel needs): 1 = lone specks only; 2 also takes 1 px
# whiskers and lines (the clouds, whose dark base specks read as dirt)
HD_CLEAN = {"sky": (2, 2), "trees": (2, 1), "hill": (2, 1)}
# lengths below are in fine px at 2x and scale with s
HD_SNOW_SOFT = 0.8       # the snow field's stroke: the lit value blurred this much inside the snow before it is
HD_SNOW_STROKE = 2       # stepped, then a mode filter of this radius: cast shadows and bands become gouache strokes
HD_SNOW_THIN = 10        # a snow colour holding fewer pixels than this in its 5x5 window is a dot or a dash: absorbed
HD_SNOW_BLOB = 64        # a snow colour patch smaller than this, cut off from its own colour, is a bead: absorbed
# the near spruce row: its needle pockets one step deeper and its shelves one step lighter (ramp threshold shifts), so
# the trees next to the walker and the car carry the raw render's depth
HD_NEAR_TREES = {"needle_tn": 0.07, "snowc_tn": -0.07}
# the tree band's values grouped by distance (a dark near forest against a bright sky): the back rows hold two values
# only (needles, snow), the middle row loses its darkest navy, the darkest values stay in the near row
HD_ROWS = {"tb": {"tbu": "tb0", "tb1": "tb2", "tb3": "tb2"}, "tf": {"tfu": "tf0", "tf1": "tf2", "tf3": "tf2"},
           "tm": {"tmu": "tm0"}}
HD_ROWS_AIR = {"tb": 0.14, "tf": 0.22}    # and the back rows one more step into the mist (after trees_air)
# the cumulus keeps the render's dabs, each stepped on its own, the hot pink only the render's crown clusters (a blur
# before stepping read as camouflage, a pink rim band as a neon outline). Only cleaned:
HD_CLOUD_UNDER = 24      # the base value stays only this close above the cloud's lower edge (a step lighter above)
HD_CLOUD_STROKE = 1      # a mode filter of this radius: smaller than a dab
HD_CLOUD_BLOB = 12       # a value patch smaller than this is absorbed by the mass around it
HD_CLOUD_SLIVER = 40     # and a base-value patch smaller than this (a gap's shadow between dabs)
HD_FINE_LINES = 3        # from this view scale on, the relaid lines and the car's edges are drawn on the fine grid
HD_LINE_W = 2            # the fine lines' width (fine px)
HD_CAR_ROUND = 2         # the radius of the mode filter that rounds the car's edges on the fine grid
LAMP_SHELF, LAMP_NEEDLE = 1.25, 0.45     # the lamp's mint on the fine spruces: strong on the shelves, faint in the pockets
POOL_FEATHER = ((0.24, 6), (0.12, 6))   # the lamp pool's soft edge on the snow: (mint0 alpha, width)
LANTERN = ((7.0, 0.05), (5.6, 0.12), (4.3, 0.24), (3.1, 0.5))   # the lantern's halo: (radius, mint2 alpha), stepped
                                                                # down so no disc edge shows
LANTERN_CORE = 1.6       # its crisp hot core (radius)
POST_MIN_H = 14          # posts at least this tall (art px) are the near ones, redrawn as clean slabs

TREE_SHELF = [KIDX[k + i] for k in ("tn", "tm", "tb", "tf") for i in "123"]
TREE_NEEDLE = [KIDX[k + i] for k in ("tn", "tm", "tb", "tf") for i in "u0"]
SNOW_LIT = [KIDX[k] for k in ("sn", "sn_hi", "sn_lit", "sn_warm", "sn_glow", "sn_cap")]
SNOW_ALL = [KIDX[k] for k in ("sn_deep", "sn_shade", "sn_mid")] + SNOW_LIT
TINTS = ("mint0", "mint1", "mint2", "peach", "hot")      # the light colours a tinted art pixel is fitted to
TINTRGB = np.array([D.C[k] for k in TINTS] + [[0, 0, 0]] * (8 - len(TINTS)), np.float64)
MINT = [TINTS.index(k) for k in ("mint0", "mint1", "mint2")]


# ---------------------------------------------------------------- fine-grid helpers
def _up(a: np.ndarray, s: int) -> np.ndarray:
    """nearest upscale by s (art pixels -> s x s blocks)"""
    return np.repeat(np.repeat(a, s, 0), s, 1)


def _labels(rgb: np.ndarray, a: np.ndarray):
    """an rgba image -> (label image, the colour table): label 0 = empty"""
    key = (rgb[..., 0].astype(np.int64) << 16) | (rgb[..., 1].astype(np.int64) << 8) | rgb[..., 2]
    key = np.where(a, key + 1, 0)
    u, inv = np.unique(key, return_inverse=True)
    return inv.reshape(key.shape).astype(np.int32), u


def _rgb(u: np.ndarray, lab: np.ndarray) -> np.ndarray:
    """the colours of a label image (_labels' table)"""
    k = np.maximum(u[lab] - 1, 0)
    return np.dstack([(k >> 16) & 255, (k >> 8) & 255, k & 255]).astype(np.uint8)


def box(a: np.ndarray, r: int) -> np.ndarray:
    """sum over a (2r+1)^2 window (edges clamp)"""
    p = np.pad(a, r, mode="edge").astype(np.float32)
    c = np.pad(np.cumsum(np.cumsum(p, 0), 1), ((1, 0), (1, 0)))
    n = 2 * r + 1
    return c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]


def smooth_within(idx: np.ndarray, mid: np.ndarray, mats, n: int) -> np.ndarray:
    """a 3x3 mode filter over the pixels of the given materials only (everything else is one fixed label they may not
    take): the seams on the slab tops become calm painted curves"""
    sel = np.isin(mid, mats) & (idx >= 0)
    if not sel.any() or n <= 0:
        return idx
    ys, xs = np.nonzero(sel)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub, ss = idx[y0:y1, x0:x1].astype(np.int32), sel[y0:y1, x0:x1]
    lab = np.where(ss, sub, -2)
    out = mode3(lab, n)
    ok = ss & (out >= 0)
    idx = idx.copy()
    idx[y0:y1, x0:x1] = np.where(ok, out, sub)
    return idx


def stroke_within(idx: np.ndarray, sel: np.ndarray, r: int, n: int = 2, thin: int = 0, tr: int = 2) -> np.ndarray:
    """a (2r+1)^2 mode filter over the selected pixels only (the rest neither move nor count): band edges run as round
    painted strokes; then (thin > 0) every pixel whose colour holds fewer than `thin` pixels of its (2tr+1)^2 window
    takes the window's most common colour, so streaks thinner than ~2 px join their neighbours instead of breaking
    into dots and dashes"""
    if not sel.any():
        return idx
    ys, xs = np.nonzero(sel)
    pad = 2 * r + 3
    y0, y1 = max(ys.min() - pad, 0), ys.max() + 1 + pad
    x0, x1 = max(xs.min() - pad, 0), xs.max() + 1 + pad
    sub, ss = idx[y0:y1, x0:x1].copy(), sel[y0:y1, x0:x1]
    cols = np.unique(sub[ss])

    def counts(rr):
        best, bestc = sub.copy(), np.full(sub.shape, -1.0, np.float32)
        own = np.zeros(sub.shape, np.float32)
        for v in cols:
            c = box((sub == v) & ss, rr)
            own = np.where(sub == v, c, own)
            upd = c > bestc + 0.5
            best[upd], bestc[upd] = v, c[upd]
        return best, bestc, own
    for _ in range(n):
        best, bestc, own = counts(r)
        upd = ss & (bestc > own + 0.5)
        sub[upd] = best[upd]
    if thin:
        for _ in range(2):
            best, bestc, own = counts(tr)
            upd = ss & (own < thin)
            sub[upd] = best[upd]
    idx = idx.copy()
    idx[y0:y1, x0:x1] = np.where(ss, sub, idx[y0:y1, x0:x1])
    return idx


def absorb_blobs(idx: np.ndarray, sel: np.ndarray, amax: int, only=None) -> np.ndarray:
    """the beads a thin shadow tail breaks into: every 4-connected patch of one colour inside sel smaller than amax
    pixels takes the most common other colour around it (the snow it lies on)"""
    if not sel.any():
        return idx
    ys, xs = np.nonzero(sel)
    y0, y1 = max(ys.min() - 4, 0), ys.max() + 5
    x0, x1 = max(xs.min() - 4, 0), xs.max() + 5
    sub, ss = idx[y0:y1, x0:x1].copy(), sel[y0:y1, x0:x1]
    cols = np.unique(sub[ss])
    own = np.zeros(sub.shape, np.float32)
    for v in cols:
        own = np.where(sub == v, box((sub == v) & ss, 4), own)
    cand = ss & (own < amax)                 # few of its colour within 4 px: may be a bead
    if only is not None:
        cand &= np.isin(sub, only)
    # every patch of one colour, labelled once: a bead is a whole patch under amax pixels holding a candidate (a big
    # region's thin arm is a candidate too, but its patch is big, so no part of it is taken)
    lab, n = P.label4(ss, sub)
    size = np.bincount(lab[ss], minlength=n)
    hit = np.bincount(lab[cand], minlength=n) > 0
    small = (size < amax) & hit
    bead = ss & small[np.maximum(lab, 0)]
    if bead.any():
        best, bestc = sub.copy(), np.full(sub.shape, -1.0, np.float32)
        for v in cols:
            c = box((sub == v) & ss & ~bead, 3)
            upd = bead & (c > bestc)
            best[upd], bestc[upd] = v, c[upd]
        sub[bead] = best[bead]
    idx = idx.copy()
    idx[y0:y1, x0:x1] = np.where(ss, sub, idx[y0:y1, x0:x1])
    return idx


def up_smooth(L: D.Layer, s: int, n: int = 1) -> D.Layer:
    """an art layer painted flat (the far hills, the ridges) at s x: nearest, then a mode filter rounds its seams"""
    lab, u = _labels(L.rgb, L.a)
    lab = mode3(_up(lab, s), n)
    out = D.Layer(s)
    out.a = u[lab] > 0
    out.rgb = _rgb(u, lab)
    out.z = np.where(out.a, _up(L.z, s), np.inf).astype(np.float32)
    return out


def tint_fit(before: np.ndarray, after: np.ndarray, m: np.ndarray):
    """each changed pixel as a tint: after = before + a (C - before) for the light colour C (of TINTS) that fits it
    best; returns a (h, w) and the index of C in TINTS (h, w)"""
    b, f = before.astype(np.float64), after.astype(np.float64)
    bestA, bestC = np.zeros(m.shape), np.zeros(m.shape, np.int32)
    bestR = np.full(m.shape, np.inf)
    for i, k in enumerate(TINTS):
        v = D.C[k].astype(np.float64) - b
        a = np.clip((v * (f - b)).sum(-1) / np.maximum((v * v).sum(-1), 1e-6), 0, 1)
        r = ((b + a[..., None] * v - f) ** 2).sum(-1)
        upd = m & (r < bestR)
        bestA[upd], bestC[upd], bestR[upd] = a[upd], i, r[upd]
    return bestA, bestC


# ---------------------------------------------------------------- the world layers at the fine size
def hd_cumulus(idx: np.ndarray, mid: np.ndarray, s: int) -> np.ndarray:
    """the cumulus's dabs as the render painted them, cleaned (see HD_CLOUD_*)"""
    K = KIDX
    cl = np.isin(mid, [MAT["cloud"], MAT["pink"]]) & (idx >= 0)
    if not cl.any():
        return idx
    under = np.zeros(cl.shape, bool)
    for k in range(1, HD_CLOUD_UNDER * s // 2 + 1):
        under[:-k] |= ~cl[k:]
    idx = np.where(cl & ~under & (idx == K["cl_base"]), K["cl_shade"], idx)
    idx = stroke_within(idx, cl, max(1, HD_CLOUD_STROKE * s // 2), 1)
    idx = absorb_blobs(idx, cl, HD_CLOUD_BLOB * s * s // 4)
    return absorb_blobs(idx, cl, HD_CLOUD_SLIVER * s * s // 4, only=[K["cl_base"]])


def hd_tree_rows(idx: np.ndarray) -> np.ndarray:
    idx = idx.copy()
    for grp in HD_ROWS.values():
        for a, b in grp.items():
            idx[idx == KIDX[a]] = KIDX[b]
    return idx


def fine_world(work: Path, name: str, rake):
    """one world layer at the render's own size: stepped per render pixel, then the per-layer cleanup. Returns the
    palette index image and the layer"""
    raw = load_raw(work, name)
    s = raw.shape[1] // P.W
    soft = (HD_SNOW_SOFT * s / 2, (MAT["snow"],)) if name == "hill" else (0.0, ())
    idx, mid, dep = classify(raw, HD_NEAR_TREES if name == "trees" else None, rake if name == "hill" else None, *soft)
    n_, need = HD_CLEAN[name]
    idx, mid = clean(idx, mid, n_, alpha=False, need=need)      # orphan specks only, inside the masses
    idx, mid = clean(idx, mid, 1, alpha=True, need=1)           # and lone specks on the silhouettes
    if name == "sky":                                           # the cumulus: the render's dabs, cleaned
        idx = hd_cumulus(idx, mid, s)
    else:
        idx = min_rows(idx, mid, SNOWY, 1)
    if name == "hill":
        sn = (mid == MAT["snow"]) & (idx >= 0)
        idx = stroke_within(idx, sn, HD_SNOW_STROKE * s // 2, 2, HD_SNOW_THIN * s * s // 4, s)
        for _ in range(2):                 # twice: a bead's dark core goes first, then the halo it leaves
            idx = absorb_blobs(idx, sn, HD_SNOW_BLOB * s * s // 4)
        idx = smooth_within(idx, mid, [MAT["stone"]], 1)
    if name == "trees":
        idx = hd_tree_rows(idx)
    if name != "sky":
        idx = contact(idx, mid, [MAT["trunk"], MAT["wood"]])
    if name == "hill":
        idx = stair_craft(idx, mid)
        idx = rim_lip(idx, mid)
    return idx, to_layer(idx, dep, s)


# ---------------------------------------------------------------- the art-grid drawing laid back on top
def old_lines(snap: dict) -> np.ndarray:
    """the art pixels the ropes and wires left showing on the hill (nothing drawn after them covers them)"""
    lines, rec = snap["lines"]
    mid_ = snap["mid"]["hill"]
    return rec["lines"] & ~((mid_.rgb != rec["after"].rgb).any(-1) | (mid_.z != rec["after"].z))


def refit_line(ln: dict) -> list:
    """a 1 px rope or wire redrawn 1 px from one cubic fitted through its pixel run (sampled per column), so its old
    kinks and doubled pixels are gone; each new pixel keeps the colour of the old pixel under it (or next to it).
    Runs a cubic cannot follow within ~1 px come back as they were."""
    px = ln["px"]
    xs = np.array([p[0] for p in px], float)
    ys = np.array([p[1] for p in px], float)
    if len(px) < 4 or np.ptp(xs) <= 2 * max(np.ptp(ys), 1):
        return [tuple(p) for p in px]
    cf = np.polyfit(xs, ys, 3)
    if np.abs(np.polyval(cf, xs) - ys).max() >= 1.3:
        return [tuple(p) for p in px]
    xf = np.arange(int(xs.min()), int(xs.max()) + 1)
    old = {(x, y): c for x, y, c in px}
    return [(x, y, _near_colour(old, x, y) or px[0][2]) for x, y in D.line_pixels([(x, float(np.polyval(cf, x))) for x in xf])]


def _near_colour(old: dict, x: int, y: int):
    """the colour of the old line pixel at (x, y), or of the nearest one beside it"""
    c = old.get((x, y))
    if c is None:
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1), (0, 2), (0, -2)):
            c = old.get((x + dx, y + dy))
            if c:
                break
    return c


def fine_line(ln: dict, g: int, width: int = 1) -> list:
    """refit_line's cubic drawn on a g times finer grid (or, where none fits, a polyline through the old pixels'
    centres), `width` fine px thick (the extra pixel below a flat run, beside a steep one); each fine pixel keeps
    the colour of the art pixel it falls in (or the nearest old one)"""
    px = ln["px"]
    xs = np.array([p[0] for p in px], float)
    ys = np.array([p[1] for p in px], float)
    old = {(x, y): c for x, y, c in px}
    f = lambda v: (v + 0.5) * g - 0.5                 # an art pixel's centre on the fine grid
    cf = None
    if len(px) >= 4 and np.ptp(xs) > 2 * max(np.ptp(ys), 1):
        cf = np.polyfit(xs, ys, 3)
        if np.abs(np.polyval(cf, xs) - ys).max() >= 1.3:
            cf = None
    if cf is not None:
        xf = np.arange(int(round(f(xs.min()))), int(round(f(xs.max()))) + 1)
        pts = [(x, f(float(np.polyval(cf, (x + 0.5) / g - 0.5)))) for x in xf]
    else:
        pts = [(f(x), f(y)) for x, y, _ in px]
    fine = D.line_pixels(pts)
    out = []
    for i, (x, y) in enumerate(fine):
        a0, a1 = fine[max(i - 1, 0)], fine[min(i + 1, len(fine) - 1)]
        steep = abs(a1[1] - a0[1]) > abs(a1[0] - a0[0])
        c = _near_colour(old, x // g, y // g) or px[0][2]
        out.append((x, y, c))
        for w in range(1, width):
            out.append((x + w, y, c) if steep else (x, y + w, c))
    return out


def relay_lines(L: D.Layer, snap: dict, s: int) -> None:
    """the ropes and wires again, refitted and laid as s x s art pixels (from HD_FINE_LINES: on the fine grid,
    HD_LINE_W fine px thick): the old line pixels go back to what lay under them, a refitted pixel shows where the
    line was in front and nothing drawn later covers it"""
    lines, rec = snap["lines"]
    mid_, pre = snap["mid"]["hill"], snap["pre"]["hill"]
    old = old_lines(snap)                       # left out of the replay: the fine render shows there, or a post
    post = old & ((rec["rgbpre"] != pre.rgb).any(-1) | (rec["zpre"] != pre.z))
    P_ = _up(post, s)
    L.rgb[P_], L.a[P_], L.z[P_] = _up(rec["rgbpre"], s)[P_], True, _up(rec["zpre"], s)[P_]
    fine = s >= HD_FINE_LINES
    for ln in lines:
        z = ln["z"]
        pix = fine_line(ln, s, HD_LINE_W) if fine else refit_line(ln)
        for x, y, col in pix:
            fx, fy = (x, y) if fine else (x * s, y * s)
            x, y = (x // s, y // s) if fine else (x, y)
            if not (0 <= x < P.W and 0 <= y < P.H):
                continue
            if z > rec["zpre"][y, x] + 0.3:
                continue
            later = (mid_.rgb[y, x] != rec["after"].rgb[y, x]).any() or mid_.z[y, x] != rec["after"].z[y, x]
            if later and mid_.z[y, x] < z:
                continue
            n = 1 if fine else s
            b = (slice(fy, fy + n), slice(fx, fx + n))
            L.rgb[b] = D.C[col]
            L.a[b] = True
            L.z[b] = z


def seat_car(L: D.Layer, snap: dict, s: int) -> None:
    """the car sits IN the painted snow: its body stays art pixels, but its contact pool, the shade under the sills,
    the snow bank over the tyres and the bloom on it are the painted world's, so they are rounded to the fine grid
    (a mode filter over the car's ground, its body and everything else held) and meet the fine snow without steps"""
    pr, mid_ = snap["props"], snap["mid"]["hill"]
    car = ((mid_.rgb != pr.rgb).any(-1) | (mid_.a != pr.a)) & mid_.a
    body = car & (mid_.z == np.float32(snap["car"]["z"]))
    if not body.any():
        return
    ground = _up(car & ~body, s)
    ys, xs = np.nonzero(_up(body, s))
    y0, y1, x0, x1 = max(ys.min() - 8 * s, 0), ys.max() + 8 * s, max(xs.min() - 12 * s, 0), xs.max() + 12 * s
    sub = (slice(y0, y1), slice(x0, x1))
    held = _up(body | ((mid_.rgb != snap["pre"]["hill"].rgb).any(-1) & ~car), s)[sub]   # the body, posts, ropes
    lab, u = _labels(L.rgb[sub], L.a[sub])
    near = box(ground[sub], 2 * s) > 0                   # the car's ground and the fine snow it meets
    if s < HD_FINE_LINES:
        new = mode3(np.where(held, -1 - lab, lab), 2)
    else:                                    # 3 px teeth need a wider brush: a radius-s mode over the ground only
        new = stroke_within(lab, near & ~held & (lab > 0), s, 2)
    ok = near & ~held & (new > 0)
    L.rgb[sub][ok] = _rgb(u, np.maximum(new, 0))[ok]
    if s >= HD_FINE_LINES:
        # at 3x the body's own edges (the roofline, the arches, the windows, the roof snow) are rounded on the fine
        # grid too: its 3 px stairs become fine steps, so the car sits in the 1:1 painted world instead of on it
        B = _up(body, s)[sub]
        zone = (box(B, HD_CAR_ROUND) > 0) & L.a[sub]
        lab, u = _labels(L.rgb[sub], L.a[sub])
        new = stroke_within(lab, zone, HD_CAR_ROUND, 1)
        ok = zone & (new > 0)
        L.rgb[sub][ok] = _rgb(u, np.maximum(new, 0))[ok]


def slab_posts(rgb: np.ndarray, rep: np.ndarray):
    """the nearest fence posts as clean slabs: every row of a post takes the post's own side-to-side profile (the
    most common colour at each quarter of its width over all its rows), so the light side, the middle and the dark
    side run straight down it with its lean, without the vertical streak segments and notches of the sprite. A post
    whose lean is a single pixel step stands straight instead (the step read as a jog halfway up). Returns the
    picture and the mask of what to paint over the render."""
    rep = rep.copy()
    wood = np.zeros(rep.shape, bool)
    for k in ("wood", "wood_lit", "wood_dk"):
        wood |= (rgb == D.C[k]).all(-1)
    wood &= rep
    out = rgb.copy()
    bridged = wood.copy()                    # a rope crossing a post splits it in two: join across 1-3 row gaps
    for k in (1, 2):
        bridged[k:-k] |= wood[:-2 * k] & wood[2 * k:]
    for comp in components(bridged):
        ys, xs = comp
        if np.ptp(ys) + 1 < POST_MIN_H:
            continue
        rows = {}
        for y, x in zip(ys, xs):
            if wood[y, x]:
                rows.setdefault(y, []).append(x)
        prof = [dict() for _ in range(4)]
        for y, r in rows.items():
            x0, x1 = min(r), max(r)
            w = x1 - x0 + 1
            for x in range(x0, x1 + 1):
                if not wood[y, x]:
                    continue
                q = min(int((x - x0) * 4 / w), 3) if w > 1 else 0
                key = tuple(rgb[y, x])
                prof[q][key] = prof[q].get(key, 0) + 1
        best = [max(p, key=p.get) if p else None for p in prof]
        x0s = np.array([min(r) for r in rows.values()])
        x1s = np.array([max(r) for r in rows.values()])
        spread = lambda v: np.percentile(v, 85) - np.percentile(v, 15)     # a rope's notch or a base row aside
        straight = spread(x0s) <= 1 and spread(x1s) <= 1
        X0, X1 = int(np.median(x0s)), int(np.median(x1s))
        if straight:                         # the gap rows too (the rope is relaid over the post afterwards)
            rows = {y: rows.get(y, [X0]) for y in range(min(rows), max(rows) + 1)}
        for y, r in rows.items():
            x0, x1 = min(r), max(r)
            if straight:
                for x in r:
                    if not X0 <= x <= X1:
                        rep[y, x] = False
                for x in range(X0, X1 + 1):
                    wood[y, x] = rep[y, x] = True
                x0, x1 = X0, X1
            w = x1 - x0 + 1
            for x in range(x0, x1 + 1):
                q = min(int((x - x0) * 4 / w), 3) if w > 1 else 0
                if wood[y, x] and best[q] is not None:
                    out[y, x] = best[q]
    return out, rep


# ---------------------------------------------------------------- the light at the fine size
def feather_pool(L: D.Layer, idx: np.ndarray, mint: np.ndarray, s: int) -> None:
    """the lamp's pool ended in a hard ring where its weakest band met the unlit snow: two more stepped bands fade
    it out over the snow, the outer one only on the snow facing the light (so the edge follows the snow's form)"""
    snow = np.isin(idx, SNOW_ALL) & L.a
    src = mint & snow
    if not src.any():
        return
    ys, xs = np.nonzero(src)
    pad = sum(w for _, w in POOL_FEATHER) * s
    y0, y1, x0, x1 = max(ys.min() - pad, 0), ys.max() + pad, max(xs.min() - pad, 0), xs.max() + pad
    sub = (slice(y0, y1), slice(x0, x1))
    have = mint[sub].copy()
    lab = np.zeros(have.shape, np.int32)
    reach = 0
    for i, (al, w) in enumerate(POOL_FEATHER):
        reach += w * s // 2
        band = (box(src[sub], reach) > 0) & ~have & snow[sub]
        if i:
            band &= np.isin(idx[sub], SNOW_LIT)
        lab[band] = i + 1
        have |= band
    lab = mode3(np.where(snow[sub] & ~mint[sub], lab, -1), 2)
    rgb = L.rgb[sub]
    for i, (al, w) in enumerate(POOL_FEATHER):
        m = lab == i + 1
        rgb[m] = D.tint(rgb[m], "mint0", al)


def lantern(L: D.Layer, hd: dict, car: dict, s: int) -> None:
    """the headlamp at the fine size: a crisp hot core of a few pixels and a stepped mint halo round it (over the
    car, and over the spruces behind where the hill layer is empty)"""
    lx, ly = car["lamp"]
    cx, cy = (lx + 0.5) * s, (ly + 0.5) * s
    R = int(LANTERN[0][0] * s / 2) + 2
    y0, x0 = max(int(cy) - R, 0), max(int(cx) - R, 0)
    Y, X = np.mgrid[y0:int(cy) + R + 1, x0:int(cx) + R + 1] + 0.5
    d = np.hypot(X - cx, (Y - cy) * 1.25) / (s / 2)
    sub = (slice(y0, y0 + d.shape[0]), slice(x0, x0 + d.shape[1]))
    rgb, a, z = L.rgb[sub], L.a[sub], L.z[sub]
    back = hd["sky"].rgb[sub].copy()            # what shows behind the hill: the sky, the ridges over it, the trees
    for k in ("ridges", "trees"):
        back = np.where(hd[k].a[sub][..., None], hd[k].rgb[sub], back)
    for r, al in LANTERN:
        m = d <= r
        rgb[m & ~a] = back[m & ~a]
        z[m & ~a] = np.float32(car["z"] - 0.2)
        a[m] = True
        rgb[m] = D.tint(rgb[m], "mint2", al)
    rgb[d <= LANTERN_CORE] = D.C["lamp"]


def relight(L: D.Layer, n: str, snap: dict, fidx: np.ndarray, hd: dict, s: int) -> None:
    """the lamp's mint and the tail lights' pink on the fine layer: on the art picture each tinted pixel moved toward
    one light colour; fit which one and how far, and move the fine pixels under it the same way, the bands' seams
    rounded by a mode filter so the light has fine edges too"""
    mid_, fin = snap["mid"][n], snap["final"][n]
    t = (fin.rgb != mid_.rgb).any(-1) | (fin.a & ~mid_.a)
    A, Ci = tint_fit(mid_.rgb, fin.rgb, t)
    lab = _up(np.where(t, 1 + np.round(A * 40).astype(np.int32) * 8 + Ci, 0), s)   # alpha in 1/40 steps x colour
    if t.any():
        ys, xs = np.nonzero(lab)
        y0, y1, x0, x1 = max(ys.min() - 2, 0), ys.max() + 3, max(xs.min() - 2, 0), xs.max() + 3
        lab[y0:y1, x0:x1] = mode3(lab[y0:y1, x0:x1], 2)
    ring = np.zeros(lab.shape, bool)
    if n == "hill":                        # the lantern is painted at the fine size (lantern)
        ring = _up(lantern_ring(snap["car"]), s)
        lab[ring] = 0
    T = lab > 0
    col = np.maximum(lab - 1, 0) % 8
    a_ = (np.maximum(lab - 1, 0) // 8 / 40.0)[..., None]
    c_ = TINTRGB[col]
    if n == "hill":                        # the warm edge line of the pool reads as a hard ring here: the weakest
        peach = T & (col == TINTS.index("peach")) & _up(snap["car"]["z"] - 4.0 < fin.z, s)   # mint instead, and
        a_[peach, 0] = 0.34                                                                  # feather_pool fades it
        c_[peach] = TINTRGB[TINTS.index("mint0")]
        lab[peach] = 1 + TINTS.index("mint0")
        col = np.maximum(lab - 1, 0) % 8
    if n in ("trees", "hill"):
        # the art picture lit a whole tree pixel one way; the fine spruces hold shelf and needle pixels side by side,
        # so the light splits by what it falls on: the snow shelves take the mint strongly, the needle pockets only a
        # breath of the deepest mint, so the lit trees keep their depth instead of washing out
        shelf = np.isin(fidx, TREE_SHELF) & T
        needle = np.isin(fidx, TREE_NEEDLE) & T
        mint = np.isin(col, MINT)
        a_[shelf & mint, 0] = np.minimum(a_[shelf & mint, 0] * LAMP_SHELF, 0.8)
        a_[needle & mint, 0] *= LAMP_NEEDLE
        c_[needle & mint] = TINTRGB[TINTS.index("mint0")]
    newa = _up(fin.a & ~mid_.a, s) & ~L.a & ~ring
    lit = L.rgb * (1 - a_) + c_ * a_
    base = np.where(newa[..., None], _up(fin.rgb, s), np.round(lit))
    L.rgb[T] = np.clip(base[T], 0, 255).astype(np.uint8)
    L.a |= newa
    if n == "hill":
        feather_pool(L, fidx, T & np.isin(col, MINT), s)
        lantern(L, hd, snap["car"], s)
    else:
        glint = _up(t & (fin.rgb == D.C["lamp"]).all(-1), s)
        L.rgb[glint] = D.C["lamp"]


# ---------------------------------------------------------------- the look
def pixelize_hd(work: Path, out: Path, seed: int = SEED) -> dict:
    """the art-size layers as paint3d.pixelize makes them (the runtime's depth, route and lookups), plus
    hd_<layer>.png at the render's own size"""
    work, out = Path(work), Path(out)
    scene, snap = pixelize(work, out, seed)
    rk = work / "raw" / "rake.npy"
    rake = np.load(rk).astype(np.float32) if rk.exists() else None
    hd, fidx = {}, {}
    for name in ("sky", "trees", "hill"):
        fidx[name], hd[name] = fine_world(work, name, rake)
    s = hd["sky"].s
    sky = D.sky_back(np.random.default_rng(seed + 1), s)
    m = hd["sky"].a
    sky.rgb[m] = hd["sky"].rgb[m]
    hd["sky"] = sky
    hd["ridges"] = up_smooth(snap["pre"]["ridges"], s, 2)
    trees_air(hd["trees"])
    for grp, al in HD_ROWS_AIR.items():
        m = np.isin(fidx["trees"], [KIDX[grp + i] for i in "u0123"]) & hd["trees"].a
        hd["trees"].rgb[m] = D.tint(hd["trees"].rgb[m], "mist", al)
    for n in LAYERS:
        pre, mid_, L = snap["pre"][n], snap["mid"][n], hd[n]
        # what was drawn over the render at art size (posts, wires, poles, the car, its pool and bank): those art
        # pixels, s x s each; the ropes and wires come back refitted (relay_lines), the nearest posts as clean slabs
        rep = (mid_.rgb != pre.rgb).any(-1) | (mid_.a != pre.a)
        if n == "hill":
            rep &= ~old_lines(snap)
        src, rep = slab_posts(mid_.rgb, rep & mid_.a) if n == "hill" else (mid_.rgb, rep & mid_.a)
        R = _up(rep, s)
        L.rgb[R] = _up(src, s)[R]
        L.a |= R
        L.z[R] = _up(mid_.z, s)[R]
        if n == "hill":
            relay_lines(L, snap, s)
            seat_car(L, snap, s)
        relight(L, n, snap, fidx.get(n), hd, s)
        L.save(out / f"hd_{n}.png", optimize=True)
    return scene
