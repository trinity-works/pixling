"""The map as layers that move, for the viewer (web/arena.js), painted from the same data renders as art/map.png:

    sky.png        the dusk sky, painted wider and taller than the map (it pans least)
    far.png        the cumulus past the forest: a strip STRIP_W px wide that wraps seamlessly (drifts, pans little)
    main.png       the map without the clouds (alpha where the sky and the clouds show), the trees swaying on it
    corner.png     the two towers standing out of the sea at the front corners
    sea.png        the cloud sea under the lip: a wrapping strip (drifts, pans more than the sky)
    cap.png        the ledge's top along the front lip, drawn over the sea so it never laps onto the field
    sway.png/json  the swaying trees: SWAY_N held frames, as the TILE px tiles that differ from main.png

Draw order: sky < far < main < corner < sea < cap. With every layer at offset 0 the composite is art/map.png's picture
(the clouds repainted whole, so where trees hid them they now continue).

The sway: every tree pixel (the frame's spruces by their occluder id, the far ridges' by their id in the ids pass) is
moved sideways by whole pixels, round(A * w * s): w = (height over the tree's foot / its height)^1.5, so the foot
never moves; s = a slow sway of its own phase plus a gust crest that rolls across the map left to right (wavelength
GUST_PX, one loop of SWAY_N frames at SWAY_FPS). A is per tree: the ring's back trees most, its sides less, the far
ridges a little, the groves inside the field not at all. What a moved tree uncovers takes what lies beside it (or the
sky, transparent). Each frame is cut into tiles; only tiles that differ from main.png are kept, identical ones shared.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from . import paint
from . import place as P
from . import zones as Z

PAD_X, PAD_Y = 640, 320            # the sky's margin round the map, for the parallax
SWAY_N, SWAY_FPS = 12, 6
TILE = 32
GUST_PX = 960


def _bind():
    global B, TREE_MATS
    from .maps import active
    B = active().biome
    TREE_MATS = tuple(B.TREE_MATS)


_bind()


def _rgba(rgb, alpha):
    out = np.zeros(rgb.shape[:2] + (4,), np.uint8)
    out[..., :3] = rgb
    out[..., 3] = np.where(alpha, 255, 0)
    out[~alpha, :3] = 0
    return out


def paint_clouds(work: Path, name: str):
    """a cloud layer from its own render: the vista's ramps, haze and cleanup; RGBA"""
    lit, mid, dep, a = paint.decode(np.load(work / "raw" / f"{name}.npy"))
    zone = np.where(a, Z.CODE["vista"], 0).astype(np.int32)
    idx = paint.step_zoned(lit, mid, zone, 1.0)
    r, share = Z.ZONES["vista"]["clean"]
    idx = Z.clean(idx, a & (idx >= 0), r, share)
    level = Z.haze_level(zone, dep)
    rgb = paint.ZPAL[zone, level, np.maximum(idx, 0)]
    return _rgba(rgb, a & (idx >= 0))


def crop_rows(img):
    rows = np.nonzero(img[..., 3].any(1))[0]
    y0, y1 = int(rows.min()), int(rows.max()) + 1
    return img[y0:y1], y0


def sky_layer():
    H, W = P.H + 2 * PAD_Y, P.W + 2 * PAD_X
    idx, sea = B.sky(H, W, 1.0, -PAD_X, -PAD_Y)
    zone = np.where(sea, Z.CODE["vista"], Z.CODE["sky"])
    return paint.ZPAL[zone, 0, idx]


# ---------------------------------------------------------------- the sway
def trees(work: Path, c1: dict):
    """per pixel of main: the tree it belongs to (-1 none), and per tree: foot y, height px, x, amplitude, phase"""
    meta = json.loads((work / "raw" / "meta.json").read_text())
    S = json.loads((work / "scene3d.json").read_text())
    ids = c1["ids"]
    oid = (np.round(ids[..., 0] * 255).astype(np.int64) + 256 * np.round(ids[..., 1] * 255).astype(np.int64))
    oid[ids[..., 3] < 0.5] = 0
    kinds = getattr(B, "SWAY_KINDS", ("spruce",))
    spr = {(round(t["u"], 6), round(t["v"], 6)): t for t in S["things"] if t["kind"] in kinds}
    recs = {}
    for k, u, v, z, *_ in meta["occ"]:
        t = spr.get((round(u, 6), round(v, 6)))
        if t is None:
            continue
        recs[k] = (u, v, z, t["h"], B.sway_amp(t, u, v))
    for k, t in enumerate(S["trees"]):
        recs[10000 + k] = (t["u"], t["v"], t["z"], t["h"], B.back_sway_amp(t))
    tid = np.full(oid.shape, -1, np.int64)
    mat_ok = np.isin(c1["mid"], TREE_MATS) & c1["a"]
    keys = np.array(sorted(recs))
    pos = np.searchsorted(keys, oid)
    pos = np.clip(pos, 0, len(keys) - 1)
    hit = (keys[pos] == oid) & mat_ok & (oid > 0)
    tid[hit] = keys[pos[hit]]
    info = {}
    rng = np.random.default_rng(5)
    for k in np.unique(tid[tid >= 0]):
        u, v, z, h, amp = recs[int(k)]
        x, y = P.proj(u, v, z)
        info[int(k)] = dict(x=x, y=y, hpx=h * P.CE * P.PPM, amp=amp, phase=float(rng.uniform(0, math.tau)))
        if hasattr(B, "sway_exp"):                    # opt-in: a crown sways as one clump (a low exponent)
            info[int(k)]["wexp"] = B.sway_exp(int(k), u, v)
    return tid, info


def wind(x, t, phase):
    """the wind at map x and loop time t in [0, 1): a slow sway of the tree's own plus a gust crest rolling +x"""
    f = (x / GUST_PX - t) % 1.0
    gust = (0.5 - 0.5 * np.cos(2 * np.pi * f)) ** 2
    return 0.3 * np.sin(2 * np.pi * t + phase) + 0.7 * gust


def sway_frames(main, tid, info, dep):
    """the SWAY_N frames of main with the trees moved"""
    H, W = tid.shape
    ys, xs = np.nonzero(tid >= 0)
    t_of = tid[ys, xs]
    keys = np.array(sorted(info))
    ix = np.searchsorted(keys, t_of)
    F = lambda f: np.array([info[int(k)][f] for k in keys])[ix]
    fx, fy, hpx, amp, ph = F("x"), F("y"), F("hpx"), F("amp"), F("phase")
    w = np.clip((fy - ys) / hpx, 0, 1) ** (F("wexp") if "wexp" in info[int(keys[0])] else 1.5)
    d = dep[ys, xs]
    frames = []
    for n in range(SWAY_N):
        t = n / SWAY_N
        dx = np.round(amp * w * wind(fx, t, ph)).astype(np.int64)
        out = main.copy()
        mv = dx != 0
        if mv.any():
            my, mx, mdx, mt, md = ys[mv], xs[mv], dx[mv], t_of[mv], d[mv]
            vac = np.zeros((H, W), bool)
            vac[my, mx] = True
            # what the vacated spots show: the pixel beside the tree, away from its motion (or the sky)
            fill = main.copy()
            done = np.zeros(len(my), bool)
            for k in range(1, 4):
                qx = np.clip(mx - np.sign(mdx) * k, 0, W - 1)
                ok = ~done & (tid[my, qx] != mt)
                fill[my[ok], mx[ok]] = main[my[ok], qx[ok]]
                done |= ok
            out[my, mx] = fill[my, mx]
            # the moved pixels land, nearest last; never over something nearer that stays
            tx = mx + mdx
            inb = (tx >= 0) & (tx < W)
            my, tx, src_x, md = my[inb], tx[inb], mx[inb], md[inb]
            order = np.argsort(-md, kind="stable")
            my, tx, src_x, md = my[order], tx[order], src_x[order], md[order]
            free = vac[my, tx] | (main[my, tx, 3] == 0) | (md < dep[my, tx])
            my, tx, src_x = my[free], tx[free], src_x[free]
            out[my, tx] = main[my, src_x]
        frames.append(out)
    return frames


def tiles(main, frames, atlas_w=2048):
    """per frame, the runs of TILE px tiles (along a row) that differ from main, each run stored as one strip in the
    atlas, so the viewer draws a run with one call: atlas (RGBA), index {frames: [[tx0, ty, n, ax, ay], ...]}"""
    H, W = main.shape[:2]
    nty, ntx = H // TILE + (H % TILE > 0), W // TILE + (W % TILE > 0)
    pad = lambda a: np.pad(a, ((0, nty * TILE - H), (0, ntx * TILE - W), (0, 0)))
    m = pad(main).reshape(nty, TILE, ntx, TILE, 4).swapaxes(1, 2)
    strips, per = [], []
    for f in frames:
        pf = pad(f)
        t = pf.reshape(nty, TILE, ntx, TILE, 4).swapaxes(1, 2)
        diff = np.any(t != m, axis=(2, 3, 4))
        lst = []
        for ty in range(nty):
            tx = 0
            while tx < ntx:
                if not diff[ty, tx]:
                    tx += 1
                    continue
                t0 = tx
                while tx < ntx and diff[ty, tx]:
                    tx += 1
                strips.append(pf[ty * TILE:(ty + 1) * TILE, t0 * TILE:tx * TILE])
                lst.append([t0, ty, tx - t0, len(strips) - 1])
        per.append(lst)
    # shelf-pack the strips (all TILE high) into rows atlas_w wide
    x = y = 0
    place = []
    for st in strips:
        w = st.shape[1]
        if x + w > atlas_w:
            x, y = 0, y + TILE
        place.append((x, y))
        x += w
    atlas = np.zeros((y + TILE, atlas_w, 4), np.uint8)
    for st, (px, py) in zip(strips, place):
        atlas[py:py + TILE, px:px + st.shape[1]] = st
    per = [[[t0, ty, n, place[i][0], place[i][1]] for t0, ty, n, i in lst] for lst in per]
    return atlas, dict(tile=TILE, n=SWAY_N, fps=SWAY_FPS, runs=sum(len(x) for x in per),
                       tiles=int(sum(n for lst in per for _, _, n, _, _ in lst)), frames=per,
                       about="frame f shows main.png with, for each run [tx0, ty, n, ax, ay] of frames[f], the atlas "
                             "strip at (ax, ay), n tiles wide, drawn at (tx0, ty) * tile (cleared first where the "
                             "sky shows through: tiles carry alpha); everything else is main.png")


# ---------------------------------------------------------------- build
def build(work: Path, art: Path, c0: dict = None) -> dict:
    work, art = Path(work), Path(art)
    c0 = c0 or paint.composite(work)
    c1 = paint.composite(work, drop_clouds=True)
    H, W = c1["a"].shape
    # main: the map's own pixels wherever it showed them, the repainted world where the clouds hid it
    cloud0 = c0["useb"] & np.isin(c0["mid"], paint.CLOUD_MATS)
    keep = c0["a"] & ~cloud0
    rgb = np.where(keep[..., None], c0["rgb"], c1["rgb"])
    main = _rgba(rgb, c1["a"])
    Image.fromarray(main).save(art / "main.png", optimize=True)
    cl = getattr(B, "CLOUD_LAYERS", ())
    if getattr(B, "CAP", False):
        # the cap: the ledge's top in the lower picture, over the sea
        capm = c1["aw"] & ~c1["useb"] & (c1["z"] > -1.6) & ~np.isin(c1["mid"], TREE_MATS)
        capm[: int(H * 0.72)] = False
        cap, cy = crop_rows(_rgba(rgb, capm))
        Image.fromarray(cap).save(art / "cap.png", optimize=True)
    Image.fromarray(sky_layer()).save(art / "sky.png", optimize=True)
    at = {}
    for name in ("far", "sea", "corner"):
        if name not in cl:
            continue
        img, y = crop_rows(paint_clouds(work, "c" + name))
        at[name] = y
        Image.fromarray(img).save(art / f"{name}.png", optimize=True)
    # the sway
    tid, info = trees(work, c1)
    frames = sway_frames(main, tid, info, c1["dep"])
    atlas, idx = tiles(main, frames)
    Image.fromarray(atlas).save(art / "sway.png", optimize=True)
    sw = P.STRIP_W
    lm = B.layer_meta(W, sw, at, cy if getattr(B, "CAP", False) else 0)
    layers = dict(about=lm.pop("about"), sky=dict(x=-PAD_X, y=-PAD_Y, parallax=lm.pop("sky_parallax", [0.15, 0.6])))
    for name in ("far", "main", "corner", "sea", "cap"):
        if name == "main":
            layers["main"] = dict(x=0, y=0, parallax=[1, 1])
        elif name in lm:
            layers[name] = lm[name]
    layers["sway"] = dict(idx, trees=len(info))
    if "ambience" in lm:
        layers["ambience"] = lm["ambience"]
    (art / "layers.json").write_text(json.dumps(layers, separators=(",", ":")))
    return dict(trees=len(info), tiles=idx["tiles"], per_frame=[len(f) for f in idx["frames"]])
