"""First Snow painted in 3D: the place built in Blender with the painted-cards technique, stepped back into pixel art.

    export    the place (place.py) in metres -> scene3d.json + terrain.npz + road.npz: the terrain on a screen-even
              grid, the road's strip, the flagstones, posts, pillows, spruces, poles and the car's box
    render    Blender (blender/first_snow.py) builds it: spruces as tiers of alpha dab cards with sphere normals and
              snow shelves, cumulus as puff cards lit as one mass, a snow terrain with real cast shadows, 3D
              flagstones, posts, pillows, the car. Each layer is rendered once from the composed camera at SS x the
              art size as DATA, not colour: R = the lit value, G = a material id, B = depth. So the ramps are tuned
              here in seconds instead of re-rendering for minutes. blender/walker.py renders the walker the same way.
    pixelize  every material's lit value picks a band of its Hushfall ramp (RAMPS); 2x2 blocks take their most common
              colour, clusters are cleaned (no orphans); the sky's back, the far hills, the props, the car and the
              headlamps' light are drawn over it on the art grid (draw2d.py) -> the art-size layers (the pixel look,
              and the runtime's lookups and depth)
    hd2d      the default look (hd2d.py): the same render stepped per render pixel at the screen's own size, the
              art-grid drawing laid back on top as crisp art pixels

The layers are committed (fp/art/first_snow/), so `fp build` needs no Blender; `python3 -m fp paint` re-renders when
a Blender is around (FP_BLENDER = a blender binary, or FP_BPY = a python with the bpy module).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np

from . import draw2d as D
from . import place as P

HERE = Path(__file__).resolve().parent
ART = HERE / "art" / P.NAME                 # the committed layers of the layout place.py paints
BL_SCRIPT = HERE / "blender" / f"{P.NAME}.py"
WALKER_SCRIPT = HERE / "blender" / "walker.py"
SS = 2                                      # render supersampling (Blender renders SS x the art size)
LIGHT = (-0.55, 0.75, 0.37)                 # toward the sun, fp axes (x right, y up, z into the picture): back-left, ~49 deg up
SEED = 7

# material ids (the G channel of the data render)
MAT = dict(snow=1, stone=2, wood=3, pillow=4, car=5, glass=6, tyre=7, tail=8, load=9, rack=10, lamp=11, trunk=12,
           cloud=30, pink=31, ridge=32, cloudfar=33, deck=34,
           needle_tn=20, needle_tm=21, needle_tb=22, needle_tf=23, snowc_tn=24, snowc_tm=25, snowc_tb=26, snowc_tf=27,
           loadsnow=13, stone_side=14, road=15, rut=16, shoulder=17)


# ---------------------------------------------------------------- export: the place in metres
def export(out: Path, seed: int = SEED, ss: int = SS) -> dict:
    """write the place for the Blender pass (scene3d.json, terrain.npz, road.npz); returns place.layout()"""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lay = P.layout(seed)
    # the terrain on a grid that is even on screen: columns every 3 px, rows every ~1.2 px of ground
    zs = [P.Z_STAIR0 - 2.6]
    while zs[-1] < 140:
        z = zs[-1]
        step = 1.2 / max(abs(float(P.ground_row(z + 0.05) - P.ground_row(z))) / 0.05, 1e-3)
        zs.append(z + float(np.clip(step, 0.03, 3.0)))
    zs = np.array(zs)
    sx = np.arange(-120, P.W + 121, 3.0)
    Zg = np.repeat(zs[:, None], len(sx), 1)
    Xg = (sx[None, :] - P.X0) / P.ppm(Zg)
    Yg = P.terrain(Xg, Zg)
    np.savez_compressed(out / "terrain.npz", x=Xg.astype(np.float32), y=Yg.astype(np.float32), z=Zg.astype(np.float32),
                        path=np.array([P.path_x(z) for z in zs], np.float32), pz=zs.astype(np.float32))
    stones = []
    for sb in lay["slabs"]:
        pts = P.slab_outline(sb, n=24)
        stones.append(dict(pts=[(float(x), float(z)) for x, z in pts],
                           top=[float(P.stone_top(sb, x, z)) for x, z in pts],
                           bot=[float(min(float(P.terrain(x, z)) - 0.25, P.stone_top(sb, x, z) - 0.3)) for x, z in pts],
                           cz=float(sb["cz"]), w=float(sb["w"])))
    g = lambda p: list(p) + [float(P.terrain(p[0], p[1]))]          # each thing's ground height goes along
    spec = dict(
        W=P.W, H=P.H, F=P.F, ZB=P.ZB, CAMH=P.CAMH, X0=P.X0, Y0=P.Y0, CORE_X=P.CORE_X, HILL_CUT=P.HILL_CUT,
        LENS=[P.LENS_ZS, P.LENS_ZB, P.LENS_A, P.LENS_B], SS=ss, LIGHT=LIGHT, MAT=MAT,
        stones=stones, posts=[g(p) for p in lay["posts"]], pillows=[g(p) for p in lay["pillows"]],
        trees=[g(t) for t in lay["trees"]], trees_core=lay["trees_core"], car=P.car3d(), poles=[g(p) for p in P.POLES],
        lamp=[P.LAMP_U, P.LAMP_V, P.LAMP_TILT],
        near_pillows=P.NEAR_PILLOWS, lips=P.LIPS, rakers=P.RAKERS,
    )
    rx, ry, rz, rlab = P.road_strip()
    np.savez_compressed(out / "road.npz", x=rx.astype(np.float32), y=ry.astype(np.float32), z=rz.astype(np.float32),
                        part=rlab)
    (out / "scene3d.json").write_text(json.dumps(spec))
    return lay


# ---------------------------------------------------------------- render: Blender
def blender_cmd():
    """how to run a bpy script here: FP_BLENDER (a blender binary) or FP_BPY (a python with the bpy module)"""
    if os.environ.get("FP_BLENDER"):
        return [os.environ["FP_BLENDER"], "-b", "--python-exit-code", "1", "-P"]
    if os.environ.get("FP_BPY"):
        return [os.environ["FP_BPY"]]
    b = shutil.which("blender")
    if b:
        return [b, "-b", "--python-exit-code", "1", "-P"]
    return None


def blender(script: Path, *args) -> None:
    """run a bpy script with its args (EEVEE wants a display: under xvfb-run when there is none)"""
    cmd = blender_cmd()
    if cmd is None:
        raise SystemExit("fp paint: no Blender. Set FP_BLENDER=/path/to/blender or FP_BPY=/path/to/python-with-bpy")
    full = cmd + [str(script), "--"] + [str(a) for a in args]
    if not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        full = ["xvfb-run", "-a", "-s", "-screen 0 1280x720x24"] + full
    subprocess.run(full, check=True)


def textures(out: Path) -> None:
    """the alpha atlases the cards use (2x2 tiles each): fat brush dabs for needles, rounded puffs for clouds and the
    snow on the boughs. Ideas from painted/textures.py, drawn here so fp stays its own engine."""
    from PIL import Image, ImageDraw, ImageFilter
    import random
    out.mkdir(parents=True, exist_ok=True)
    T = 256

    def dab(d, x, y, ang, L, Wd):
        ca, sa = math.cos(ang), math.sin(ang)
        pts = []
        for i in range(32):
            th = i / 32 * math.tau
            px = L / 2 * (math.cos(th) - 1)
            py = Wd * math.sin(th) * ((1 + math.cos(th)) / 2) ** .45
            pts.append((x + px * ca - py * sa, y + px * sa + py * ca))
        d.polygon(pts, fill=255)

    def dabs(rng):     # a few fat dabs fanned from the centre: one tile = one bough tip
        S = 2
        im = Image.new("L", (T * S, T * S), 0)
        d = ImageDraw.Draw(im)
        c = T * S / 2
        for _ in range(rng.randint(9, 12)):
            a = rng.random() * math.tau
            r = (rng.random() ** 0.6) * T * S * 0.26 + T * S * .05
            Wd = rng.uniform(.07, .09) * T * S
            dab(d, c + math.cos(a) * r, c + math.sin(a) * r, a + rng.uniform(-.5, .5), Wd * rng.uniform(2.6, 3.2), Wd)
        return im.resize((T, T), Image.LANCZOS)

    def puffs(rng):
        im = Image.new("L", (T, T), 0)
        d = ImageDraw.Draw(im)
        for _ in range(rng.randint(5, 8)):
            a, r = rng.random() * math.tau, rng.random() ** 0.6 * T * 0.22
            x, y, s = T / 2 + math.cos(a) * r, T / 2 + math.sin(a) * r * 0.8, rng.uniform(30, 56)
            d.ellipse([x - s, y - s, x + s, y + s], fill=255)
        return im

    for fn, name, seed in ((dabs, "dabs", 4), (puffs, "puffs", 5)):
        rng = random.Random(seed)
        a = Image.new("L", (T * 2, T * 2), 0)
        for i in range(4):
            a.paste(fn(rng), ((i % 2) * T, (i // 2) * T))
        a.filter(ImageFilter.GaussianBlur(1)).save(out / f"{name}.png")


# ---------------------------------------------------------------- pixelize: data render -> the layer format
# every material's stepped ramp: (lit thresholds, palette keys), the painted engine's constant colour ramp applied
# after the render. lit = the diffuse value (0 in full shade with no sky, ~1 facing the sun, + the sky fill ~0.28).
RAMPS = {
    "snow": ([0.36, 0.47, 0.555, 0.86, 0.96, 1.03, 1.1], ["sn_deep", "sn_shade", "sn_mid", "sn", "sn_hi", "sn_lit", "sn_warm", "sn_glow"]),
    "pillow": ([0.26, 0.42, 0.66, 0.9], ["sn_shade", "sn", "sn_hi", "sn_lit", "sn_cap"]),
    "loadsnow": ([0.36, 0.6, 0.9], ["sn_shade", "sn", "sn_lit", "sn_cap"]),
    "stone": ([0.84, 1.0], ["slab_lip", "slab", "slab_lit"]),
    "stone_side": ([0.3], ["riser_dk", "riser"]),
    # the road: its packed lane a step under the snow beside it, the ruts a step under that, the trodden shoulder a
    # step over it; its plough ridges are pillows
    "road": ([0.5, 1.02], ["sn_shade", "sn_mid", "sn"]),
    "rut": ([0.5, 1.02], ["sn_deep", "sn_shade", "sn_mid"]),
    "shoulder": ([0.5, 0.95], ["sn", "sn_hi", "sn_lit"]),
    "wood": ([0.32, 0.7], ["wood_dk", "wood", "wood_lit"]),
    "trunk": ([], ["trunk"]),
    "car": ([0.2, 0.33, 0.5, 0.8, 1.05], ["car_under", "car_dk", "car_lo", "car", "car_lit", "car_rim"]),
    "glass": ([0.35, 0.7], ["glass_dk", "glass", "glass_hi"]),
    "tyre": ([], ["tyre"]),
    "tail": ([], ["tail"]),
    "lamp": ([], ["lamp"]),
    "load": ([0.35, 0.75], ["load_dk", "load", "load_lit"]),
    "rack": ([], ["rack"]),
    # the cumulus, lit from the low sun behind-right: a flat slate-violet base and belly, the face toward us one clear
    # value step lighter than the sky, a lit upper band, a pale crown; on the crown clumps the top band is the hot pink
    "cloud": ([0.44, 0.58, 0.77, 0.88], ["cl_base", "cl_shade", "cl_lit", "cl_hi", "cl_crown"]),
    "pink": ([0.44, 0.58, 0.77, 0.85, 0.89], ["cl_base", "cl_shade", "cl_lit", "cl_hi", "hot2", "hot"]),
    "cloudfar": ([0.5, 0.8], ["clf_lo", "clf", "clf_hi"]),
    "deck": ([0.4, 0.58, 0.84], ["dk_base", "dk_lo", "dk", "dk_hi"]),
}
for k in ("tn", "tm", "tb", "tf"):
    RAMPS["needle_" + k] = ([0.30], [k + "u", k + "0"])
    # the snow on the boughs never falls to the body colour: a shelf, a sun-side shelf, and the lit snow on the tiers
    # facing the sun
    RAMPS["snowc_" + k] = ([0.56, 0.78], [k + "1", k + "2", k + "3"])
KEYS = list(D.PAL)                           # palette index <-> key (the label images hold indices)
KIDX = {k: i for i, k in enumerate(KEYS)}
PALRGB = np.array([D.rgb(D.PAL[k]) for k in KEYS], np.uint8)
RAKE_DARK = 0.30          # how far the rake shadows (trees off the frame's left edge) drop the snow's lit value
SNOWY = [MAT["snow"], MAT["pillow"]]


def blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """separable gaussian blur (edges clamp)"""
    r = max(1, int(math.ceil(sigma * 2.5)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    for ax in (0, 1):
        p = np.pad(a, [(r, r) if i == ax else (0, 0) for i in range(2)], mode="edge")
        n = a.shape[ax]
        a = sum(w * (p[i:i + n] if ax == 0 else p[:, i:i + n]) for i, w in enumerate(k))
    return a


def classify(raw: np.ndarray, shift: dict | None = None, rake: np.ndarray | None = None, soft: float = 0.0,
             soft_mats=()):
    """data render (h, w, 4 floats) -> palette index per pixel (-1 = empty), material id, depth (m) per pixel.
    shift = per-material offsets of the ramp thresholds.
    rake = the shadow-only pass (1 lit, 0 in the shadow of the trees off the frame); it darkens snow and pillows.
    soft = a blur (px) of the lit value inside each of soft_mats before it is stepped: the band and shadow edges run
    as smooth painted strokes instead of the shadow map's sample jitter (the hd2d look's snow field)."""
    a = raw[..., 3] > 0.5
    lit = (raw[..., 0].astype(np.float32) - 0.2) / 0.4
    mid = np.round(raw[..., 1].astype(np.float32) * 64).astype(int)
    dep = raw[..., 2].astype(np.float32) * 160.0
    if rake is not None:
        sh = np.where(rake[..., 3] > 0.5, 1.0 - np.clip(rake[..., 0], 0, 1), 0.0)
        sel = (mid == MAT["snow"]) | (mid == MAT["pillow"]) | (mid == MAT["stone"])
        lit = np.where(sel, lit - RAKE_DARK * sh, lit)
    for m in (soft_mats if soft > 0 else ()):
        sel = a & (mid == m)
        w = blur(sel.astype(np.float32), soft)
        v = blur(np.where(sel, lit, 0).astype(np.float32), soft)
        lit = np.where(sel, v / np.maximum(w, 1e-4), lit)
    idx = np.full(a.shape, -1, np.int16)
    for name, m in MAT.items():
        if name not in RAMPS:
            continue
        sel = a & (mid == m)
        if not sel.any():
            continue
        th, keys = RAMPS[name]
        th = np.array(th) + (shift or {}).get(name, 0.0)
        band = np.digitize(lit[sel], th)
        idx[sel] = np.array([KIDX[k] for k in keys], np.int16)[band]
    mid = np.where(idx >= 0, mid, 0)
    return idx, mid, np.where(idx >= 0, dep, np.inf)


def load_raw(work: Path, name: str) -> np.ndarray:
    return np.load(Path(work) / "raw" / f"{name}.npy").astype(np.float32)


def _blocks(a, s):
    h, w = a.shape[0] // s, a.shape[1] // s
    return a[:h * s, :w * s].reshape(h, s, w, s).transpose(0, 2, 1, 3).reshape(h, w, s * s)


def downsample(idx: np.ndarray, mid: np.ndarray, dep: np.ndarray, s: int):
    """s x s blocks -> one art pixel: the block's most common colour (empty if most of it is empty), its material,
    the nearest depth"""
    blk, bm = _blocks(idx, s), _blocks(mid, s)
    dz = _blocks(dep, s).min(-1)
    cnt = (blk[..., :, None] == blk[..., None, :]).sum(-1)          # how often each sample's colour occurs in its block
    filled = (blk >= 0).sum(-1)
    pick = np.where(filled * 2 >= s * s, np.argmax(np.where(blk >= 0, cnt * 2 + 1, 0), -1),
                    np.argmax(cnt * 2 + (blk >= 0), -1))
    out = np.take_along_axis(blk, pick[..., None], -1)[..., 0]
    om = np.take_along_axis(bm, pick[..., None], -1)[..., 0]
    out = np.where(filled * 2 >= s * s, out, -1)
    return out.astype(np.int16), np.where(out >= 0, om, 0), np.where(out >= 0, dz, np.inf)


def clean(idx: np.ndarray, mid: np.ndarray, n: int = 3, alpha: bool = True, need: int = 2):
    """orphans and 1 px whiskers take their most common neighbour (empty counts as a label, so silhouettes round off
    too unless alpha=False); the material follows the colour"""
    lab = idx.astype(np.int32) + 1
    out = D.mode_clean(lab, n, keep=None if alpha else (lab == 0), need=need)
    if not alpha:
        out[lab == 0] = 0
    moved = out != lab
    if moved.any():                      # a pixel that took a neighbour's colour takes that neighbour's material too
        m2 = mid.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nl = np.roll(lab, (dy, dx), (0, 1)); nm = np.roll(mid, (dy, dx), (0, 1))
            hit = moved & (nl == out)
            m2[hit] = nm[hit]
        mid = np.where(out > 0, m2, 0)
    return (out - 1).astype(np.int16), mid


def min_rows(idx: np.ndarray, mid: np.ndarray, mats, n: int = 2) -> np.ndarray:
    """shadow and band rows at least 2 px tall on the snow: a 1 px row whose pixels above and below agree takes their
    colour (the grazing-slope streaks)"""
    sel = np.isin(mid, mats)
    for _ in range(n):
        up, dn = np.roll(idx, 1, 0), np.roll(idx, -1, 0)
        bad = sel & (up == dn) & (up != idx) & (up >= 0) & np.isin(np.roll(mid, 1, 0), mats)
        idx = np.where(bad, up, idx)
    return idx


def components(mask: np.ndarray):
    """4-connected components of a mask: a list of (ys, xs) index arrays, in raster order of their first pixel"""
    lab, n = P.label4(mask)
    if not n:
        return []
    ys, xs = np.nonzero(mask)
    o = np.argsort(lab[ys, xs], kind="stable")
    cut = np.cumsum(np.bincount(lab[ys, xs], minlength=n))[:-1]
    return list(zip(np.split(ys[o], cut), np.split(xs[o], cut)))


STONE_CHIP = 10           # a stone patch smaller than this (art px) is a chip: it goes back to snow


def stair_craft(idx: np.ndarray, mid: np.ndarray) -> np.ndarray:
    """the flagstones sit IN the snow: stray stone chips go back to snow, every riser has a lit top and a dark foot,
    a dark contact row runs under each stone, a lit snow lip curls over each slab's back edge and the snow between
    two slabs sinks into a darker recess"""
    K = KIDX
    stone = (mid == MAT["stone"]) | (mid == MAT["stone_side"])
    snow = (mid == MAT["snow"])
    for ys, xs in components(stone):
        if len(ys) < STONE_CHIP:
            idx[ys, xs] = K["sn"]; mid[ys, xs] = MAT["snow"]
    stone = (mid == MAT["stone"]) | (mid == MAT["stone_side"])
    side = mid == MAT["stone_side"]
    top = mid == MAT["stone"]
    up = lambda m, k=1: np.roll(m, k, 0)
    dn = lambda m, k=1: np.roll(m, -k, 0)
    # the riser: its rows counted from the slab top down; the upper half lit blue, the lower half (the foot) dark
    run = np.zeros(idx.shape, np.int16)
    for y in range(1, idx.shape[0]):
        run[y] = np.where(side[y], run[y - 1] + 1, 0)
    below = np.zeros(idx.shape, np.int16)
    for y in range(idx.shape[0] - 2, -1, -1):
        below[y] = np.where(side[y], below[y + 1] + 1, 0)
    hgt = run + below - 1
    idx[side] = K["riser"]
    idx[side & (below <= np.maximum(1, hgt // 2))] = K["riser_dk"]
    # the contact row under every stone, and a second, softer one
    c1 = snow & up(stone)
    c2 = snow & up(stone, 2) & ~c1 & ~up(snow & ~up(stone))
    idx[c2] = K["sn_shade"]
    idx[c1] = K["sn_deep"]
    # the snow lip: the top row of a slab where snow lies behind it
    lip = top & up(snow) & up(snow, 2)
    idx[lip] = K["sn_lit"]
    # the recess: snow with a stone 1-3 px above and 1-3 px below it (between two slabs) goes a step darker
    near_up = up(stone) | up(stone, 2) | up(stone, 3)
    near_dn = dn(stone) | dn(stone, 2) | dn(stone, 3)
    rec = snow & near_up & near_dn & ~c1
    idx[rec] = K["sn_shade"]
    return idx


def contact(idx: np.ndarray, mid: np.ndarray, mats, key: str = "sn_deep") -> np.ndarray:
    """a dark contact row in the snow under the given materials (trunks, posts)"""
    m = np.isin(np.roll(mid, 1, 0), mats) & (mid == MAT["snow"])
    idx[m] = KIDX[key]
    return idx


def rim_lip(idx: np.ndarray, mid: np.ndarray) -> np.ndarray:
    """a lit lip along the hill's skyline (the plateau rim seen against what lies beyond)"""
    snow = mid == MAT["snow"]
    e1 = snow & (np.roll(idx, 1, 0) < 0)
    e2 = snow & np.roll(e1, 1, 0)
    idx[e2] = KIDX["sn_lit"]
    idx[e1] = KIDX["sn_warm"]
    return idx


def to_layer(idx: np.ndarray, dep: np.ndarray, s: int = 1) -> D.Layer:
    L = D.Layer(s)
    m = idx >= 0
    L.rgb[m] = PALRGB[idx[m]]
    L.a[:] = m
    L.z[:] = np.where(m, dep, np.inf).astype(np.float32)
    return L


def trees_air(trees: D.Layer) -> None:
    """aerial perspective on the tree band: the back rows paled toward the mist (one step for the middle rows, two
    for the last), the front row one step darker"""
    for grp, al in (("tb", 0.22), ("tf", 0.36)):
        for suf in "0123u":
            m = (trees.rgb == D.C[grp + suf]).all(-1) & trees.a
            trees.rgb[m] = D.tint(trees.rgb[m], "mist", al)
    for a_, b_ in (("tn0", "tnu"), ("tn1", "tn0")):
        m = (trees.rgb == D.C[a_]).all(-1) & trees.a
        trees.rgb[m] = D.C[b_]


# ---------------------------------------------------------------- the headlamps
LAMP_BANDS = [0.2, 0.45, 0.8]   # the lamp pass's lit value -> mint steps 1..3
SPRUCE_KEYS = [k + i for k in ("tn", "tm", "tb", "tf") for i in "u0123"]
LAMP_SNOW_KEYS = D.SNOW_KEYS + ("sn_deep",)


def lamp_light(work: Path, car: dict, lay: dict) -> None:
    """the headlamps, from the Blender lamp pass (a spot light in the scene, real shadows): its light on the snow and
    the spruces in three stepped mint bands with a warm edge where the pool fades on the snow; a beam cone in the air
    in two faint steps; a hot core at the lamp. Baked: nothing of it moves."""
    f = Path(work) / "raw" / "lamp.npy"
    if not f.exists():
        return
    raw = np.load(f).astype(np.float32)
    s = raw.shape[1] // P.W
    a = raw[..., 3] > 0.5
    v = np.where(a, (raw[..., 0] - 0.2) / 0.4, 0.0)
    d = np.where(a, raw[..., 2] * 160.0, np.inf)
    vb, db = _blocks(v, s).mean(-1), _blocks(d, s).min(-1)
    K = D.C
    # the plateau ahead of the nose hides behind the crest from this camera, so the pool is the drawn low dome of
    # light rising off the crest snow at the nose and round her at the hold (draw2d.lamp_field), stepped the same way
    # and merged with the spot's light on the spruces
    dome = D.lamp_field(car).astype(np.int32)
    for L in (lay["sky"], lay["ridges"]):
        for i, (col, al) in enumerate((("mint0", 0.12), ("mint1", 0.22), ("mint2", 0.32))):
            m = L.a & (dome == i + 1)
            L.rgb[m] = D.tint(L.rgb[m], col, al)
    for name in ("trees", "hill"):
        L = lay[name]
        with np.errstate(invalid="ignore"):
            same = L.a & (np.abs(db - L.z) < np.maximum(1.0, 0.04 * L.z))
        lab = np.where(same, np.digitize(vb, LAMP_BANDS), 0).astype(np.int32)
        snow = np.zeros(lab.shape, bool)
        for k in LAMP_SNOW_KEYS:
            snow |= (L.rgb == K[k]).all(-1)
        plab = np.where(L.z > car["z"] - 4.0, dome, 0)
        lab = np.maximum(lab, plab)
        lab = D.mode_clean(lab, 2)
        lab = np.where(L.a, lab, 0)
        # a cone: the mint on the spruces ends at the right pole, in two steps; on the hill layer too (its near
        # spruce row right of the pole took the dome's mint and read as sickly olive trees)
        px_ = D.pole_x()
        cap = np.select([D.XS < px_ - 40, D.XS < px_ - 16, D.XS < px_ + 2], [3, 2, 1], 0)
        spruce = np.ones(lab.shape, bool) if name == "trees" else np.zeros(lab.shape, bool)
        if name == "hill":
            for k in SPRUCE_KEYS:
                spruce |= (L.rgb == K[k]).all(-1)
        lab = np.where(spruce, np.minimum(lab, cap), lab).astype(np.int32)
        for i, (col, al) in enumerate((("mint0", 0.3), ("mint1", 0.45), ("mint2", 0.62))):
            m = lab == i + 1
            L.rgb[m] = D.tint(L.rgb[m], col, np.where(snow[m], al, al * 0.85)[:, None])
        # the warm edge: the pool's outer band where it meets the unlit snow
        edge = snow & (lab == 1) & (np.roll(lab, -1, 0) == 0) | snow & (lab == 1) & (np.roll(lab, -1, 1) == 0)
        L.rgb[edge] = D.tint(L.rgb[edge], "peach", 0.55)
    # the beam in the air: a cone from the lamp along the nose, two faint flat steps, over what stands at the car or
    # beyond (never over the nearer snow)
    lx, ly = car["lamp"]
    p1 = P.proj(*P.lamp_ahead(9.0))                         # the aim, 9 m on (place.lamp3d: the spot Blender lights)
    ux, uy = p1[0] - lx, p1[1] - ly
    n = math.hypot(ux, uy); ux, uy = ux / n, uy / n
    dx, dy = D.XS + 0.5 - lx, D.YS + 0.5 - ly
    along = dx * ux + dy * uy
    perp = np.abs(-dx * uy + dy * ux)
    cone = np.zeros((P.H, P.W), np.int8)
    cone[(along > 2) & (along < 150) & (perp < 3 + along * 0.36)] = 1
    cone[(along > 2) & (along < 80) & (perp < 2 + along * 0.2)] = 2
    cone = D.mode_clean(cone, 2, redblack=False)
    for L in (lay["sky"], lay["ridges"], lay["trees"], lay["hill"]):
        m = L.a & (cone > 0)
        if L is lay["hill"]:
            m &= L.z > car["z"] - 1.0
        for i, (col, al) in enumerate((("mint1", 0.16), ("mint2", 0.26))):
            mm = m & (cone == i + 1)
            L.rgb[mm] = D.tint(L.rgb[mm], col, al)
    # the hot core at the lamp, a mint ring round it (hd2d.lantern repaints it at the fine size)
    H_ = lay["hill"]
    ring, core = lantern_ring(car), D.ellipse_mask(lx + 0.5, ly + 0.5, 1.8, 1.3)
    H_.rgb[ring & ~core] = D.tint(H_.rgb[ring & ~core], "mint2", 0.6)
    H_.rgb[core] = K["lamp"]
    H_.a[ring] = True
    H_.z[ring] = np.minimum(H_.z[ring], car["z"] - 0.2)


def lantern_ring(car: dict) -> np.ndarray:
    lx, ly = car["lamp"]
    return D.ellipse_mask(lx + 0.5, ly + 0.5, 3.6, 2.6)


# ---------------------------------------------------------------- pixelize
LAYERS = ("sky", "ridges", "trees", "hill")
TAIL_BLOOM = (((-2, 9, 13, 3.6), 0.16), ((-1, 8, 7, 2.1), 0.3))   # the tail lights' pink on the snow behind the car:
                                                                   # (dx, dy, rx, ry) from each light, hot alpha
TAIL_BLOOM_BELOW = 4      # it lies only this far below the lights and lower (art px)


def pixelize(work: Path, out: Path, seed: int = SEED):
    """the data render -> the art-size layers in `out` (the pixel look; the runtime's depth and colour lookups), the
    walker sheet and scene.json. Returns (scene, snap): snap holds the layers at each stage, which the hd2d look
    needs to replay what was drawn over the render (before the props, after the props, after the car, final)."""
    work, out = Path(work), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lay_ = P.layout(seed)
    rk = work / "raw" / "rake.npy"
    rake = np.load(rk).astype(np.float32) if rk.exists() else None
    lay = {}
    for name in ("sky", "trees", "hill"):
        raw = load_raw(work, name)
        s = raw.shape[1] // P.W
        idx, mid, dep = classify(raw, None, rake if name == "hill" else None)
        idx, mid, dep = downsample(idx, mid, dep, s)
        if name == "sky":
            idx, mid = clean(idx, mid, 2, alpha=False)
        else:
            idx, mid = clean(idx, mid, 3, alpha=False)        # inside the masses: checkers and orphans
            idx, mid = clean(idx, mid, 1, alpha=True)         # the silhouettes: whiskers
            idx = min_rows(idx, mid, SNOWY)
            idx = contact(idx, mid, [MAT["trunk"], MAT["wood"]])
        if name == "hill":
            idx = stair_craft(idx, mid)
            idx = rim_lip(idx, mid)
        lay[name] = to_layer(idx, dep)
    sky = D.sky_back(np.random.default_rng(seed + 1))          # the clouds over a painted back
    m = lay["sky"].a
    sky.rgb[m] = lay["sky"].rgb[m]
    ridges = D.far(np.random.default_rng(seed + 2), P.raster_terrain())
    trees, hill = lay["trees"], lay["hill"]
    trees_air(trees)
    layers = dict(sky=sky, ridges=ridges, trees=trees, hill=hill)
    snap = dict(pre={n: L.copy() for n, L in layers.items()})
    # posts, ropes and wires, poles: pixel sprites over the painted hill
    lines, rec = D.lines(lay_), {}
    D.props(hill, lay_, lines, rec)
    snap.update(props=hill.copy(), lines=(lines, rec))
    # the car: the hand-drawn hero sprite, painted straight onto the painted hill so its contact pool, bank and bloom
    # lie on the painted snow; Blender's copy of it only casts its shadow
    car = D.paint_car(hill, D.car_sprite())
    snap.update(car=car, mid={n: L.copy() for n, L in layers.items()})
    lamp_light(work, car, layers)
    snow = D.near_snow(hill)
    for (tx, ty) in car["tails"]:
        for (dx, dy, rx, ry), al in TAIL_BLOOM:
            m = D.ellipse_mask(tx + dx, ty + dy, rx, ry) & (D.YS >= ty + TAIL_BLOOM_BELOW) & snow
            hill.rgb[m] = D.tint(hill.rgb[m], "hot", al)
    snap["final"] = {n: L.copy() for n, L in layers.items()}
    for n, L in layers.items():
        L.save(out / f"{n}.png")
    zq = np.where(np.isfinite(hill.z) & hill.a, np.clip(hill.z * 100, 0, 65000), 65535).astype("<u2")
    (out / "hill_depth.bin").write_bytes(zq.tobytes())
    grid = P.walk_grid(lay_)
    (out / "walk.bin").write_bytes(walk_bin(grid))
    if (work / "raw" / "walker.npy").exists():
        walker_sheet(work, out, walker_heights(grid))
    scene = scene_json(lay_, car, grid, lit_shade(snap["mid"]["hill"], hill))
    (out / "scene.json").write_text(json.dumps(scene, separators=(",", ":")))
    return scene, snap


# the runtime's footprints and contact shadows: every colour they may land on -> the next darker tone
SHADE = {"sn_cap": "sn_lit", "sn_lit": "sn", "sn": "sn_shade", "sn_shade": "sn_deep", "sn_deep": "riser",
         "sn_hi": "sn", "sn_mid": "sn_shade", "riser_dk": "slab_lip", "slab": "slab_lip", "slab_lit": "slab",
         "riser": "slab_lip", "mint2": "mint1", "mint1": "mint0", "mint0": "sn_shade", "peach": "sn",
         "sn_warm": "sn_lit", "sn_glow": "sn_warm", "tail": "hot_deep"}


# each layer's share of a sideways camera move (the hill moves with the actors; what is further moves less). The tree
# band moves with the hill: the poles and wires drawn on the hill stand on its far snow.
PARALLAX = {"sky": 0.72, "ridges": 0.86, "trees": 1.0, "hill": 1.0}


def lit_shade(before: D.Layer, after: D.Layer) -> dict:
    """the shade lookup for the light's colours: where the headlamps or the tail lights tinted the hill's snow and
    stone off the palette, a print or her shadow there is the same tint over the next darker tone (the palette step's
    change carried over); hex -> hex, for each lit colour the step most of its pixels came from"""
    keys = {tuple(D.C[k]): k for k in SHADE}
    moved = (after.rgb != before.rgb).any(-1) & after.a
    votes = {}
    for b, f in zip(before.rgb[moved].tolist(), after.rgb[moved].tolist()):
        k = keys.get(tuple(b))
        if k is None:
            continue
        sh = np.clip(np.array(f) + D.C[SHADE[k]].astype(int) - np.array(b), 0, 255)
        v = votes.setdefault("#%02x%02x%02x" % tuple(f), {})
        h = "#%02x%02x%02x" % tuple(int(c) for c in sh)
        v[h] = v.get(h, 0) + 1
    pal = set(D.PAL.values())
    return {f: max(v, key=lambda h: (v[h], h)) for f, v in sorted(votes.items()) if f not in pal}


def scene_json(lay: dict, car: dict, grid: dict, shade_lit: dict = None) -> dict:
    """what web/layers.js reads: the canvas and the composed frame, the camera (place.proj's terms, which the runtime
    mirrors), the layers (vertical tilt share f, sideways share fx), the auto-walk's route, the walk (the grid in
    walk.bin, where she starts and stops, what she walks round), the car's anchors and the shade lookup"""
    route = P.walk_route(lay["curve"])
    return {
        "layout": P.NAME, "title": P.TITLE, "w": P.W, "h": P.H, "view_h": P.VIEW_H, "crane": list(P.CRANE), "pad": [P.SKY_PAD, P.GROUND_PAD], "xc": P.XC,
        "camera": {"f": P.F, "zb": P.ZB, "camh": P.CAMH, "x0": P.X0, "y0": P.Y0,
                   "lens": [P.LENS_ZS, P.LENS_ZB, P.LENS_A, P.LENS_B], "hero": list(P.HERO)},
        "layers": [{"src": f"{n}.png", "f": 1.0, "fx": PARALLAX[n]} for n in LAYERS[:-1]]
                  + [{"src": "hill.png", "f": 1.0, "fx": PARALLAX["hill"], "depth": "hill_depth.bin"}],
        "route": route,
        "walk": {"src": "walk.bin", **{k: grid[k] for k in ("x0", "z0", "d", "nx", "nz")},
                 "start": [route[0]["x"], route[0]["z"]], "end": list(P.END), "hold_r": P.HOLD_R, "fig_h": P.FIG_H,
                 "on": {"snow": P.ON_SNOW, "path": P.ON_PATH, "stone": P.ON_STONE, "road": P.ON_ROAD,
                        "bank": P.ON_BANK},
                 "pace": [P.PACE[k] for k in sorted(P.PACE)], **P.walk_blocks(lay)},
        "car": {**car, "at": list(P.CAR_AT)},
        "shade": {**(shade_lit or {}), **{D.PAL[k]: D.PAL[v] for k, v in SHADE.items()}},
    }


def walk_bin(grid: dict) -> bytes:
    """the walk grid for the runtime, row-major from the near left: the height in cm (int16), then one byte each per
    cell for the surface, the room (0..255) and the lamp's light (0..255)"""
    q = lambda a: np.round(np.clip(a, 0, 1) * 255).astype(np.uint8).tobytes()
    return (np.round(grid["height"] * 100).astype("<i2").tobytes() + grid["surface"].astype(np.uint8).tobytes()
            + q(grid["room"]) + q(grid["lamp"]))


# ---------------------------------------------------------------- the command
def _render_cached(work: Path, force: bool, seed: int, ss: int = SS) -> None:
    """export -> Blender data render, skipped when its inputs are unchanged"""
    work.mkdir(parents=True, exist_ok=True)
    export(work, seed, ss)
    textures(work / "tex")
    h = hashlib.sha1()
    for f in (work / "scene3d.json", work / "terrain.npz", work / "road.npz", BL_SCRIPT, work / "tex" / "dabs.png",
              work / "tex" / "puffs.png"):
        h.update(Path(f).read_bytes())
    key = h.hexdigest()[:16]
    stamp = work / "raw" / "render.key"
    if force or not (stamp.exists() and stamp.read_text() == key):
        blender(BL_SCRIPT, work, 1)
        stamp.write_text(key)


def paint(work: Path, force: bool = False, seed: int = SEED) -> Path:
    """export -> Blender render (skipped when its inputs are unchanged) -> the layers in fp/art/first_snow: the
    art-size ones and hd_*.png from the 2x render; then hd3_*.png from a 3x render (work + '_3x', ~1.5 min, cached),
    for the hd2d look at 1080p"""
    from . import hd2d
    work = Path(work)
    _render_cached(work, force, seed)
    h = hashlib.sha1((work / "scene3d.json").read_bytes() + WALKER_SCRIPT.read_bytes())
    wstamp = work / "raw" / "walker.key"
    if force or not (wstamp.exists() and wstamp.read_text() == h.hexdigest()[:16]):
        blender(WALKER_SCRIPT, work, 4)
        wstamp.write_text(h.hexdigest()[:16])
    hd2d.pixelize_hd(work, ART, seed)
    w3 = work.parent / (work.name + "_3x")
    _render_cached(w3, force, seed, ss=3)
    tmp = w3 / "hd"
    hd2d.pixelize_hd(w3, tmp, seed)
    for n in LAYERS:
        shutil.copy(tmp / f"hd_{n}.png", ART / f"hd3_{n}.png")
    return ART


# ---------------------------------------------------------------- the walker: a Blender-lit sprite sheet
WALKER_MID = dict(coat=1, hood=2, scarf=3, pack=4, leg=5, boot=6, case=7, face=8)
# her colours as stepped ramps over the lit value; the top step of the coat, hood and scarf is the sun's salmon rim
# (she is backlit by the low sun behind-left, like the spruces). Her face stays light even in shade, so it reads.
WALKER_RAMPS = {
    "coat": ([0.5, 0.86, 1.1], ["#4c2850", "#6a3460", "#86466e", "#e6a6a6"]),
    "hood": ([0.62, 0.95, 1.12], ["#221c36", "#2e2846", "#3e3a5e", "#e6a6a6"]),
    "scarf": ([0.45, 0.85, 1.08], ["#a04468", "#d0607e", "#ec8ca0", "#f0b4c0"]),
    "pack": ([0.7], ["#2a2a48", "#3c3e60"]),
    "leg": ([], ["#24203c"]),
    "boot": ([], ["#1a1630"]),
    "case": ([0.5, 0.95], ["#3e2636", "#5e3a4a", "#80566a"]),
    "face": ([0.5, 0.9], ["#a87478", "#c48e86", "#dcae9c"]),
}
WALKER_MINT = {"coat": ["#6f9a90", "#a8c8a0"], "hood": ["#6f9a90", "#a8c8a0"], "scarf": ["#e6a6a6", "#f0b4c0"],
               "case": ["#80566a", "#a8c8a0"], "pack": ["#3c3e60", "#6f9a90"], "face": ["#b8847e", "#d8a898"]}
WALKER_CELL = (1.0, 1.42)    # a sprite cell's width and height in her heights (m): room for a stride and the case


def walker_heights(grid: dict) -> tuple:
    """the heights (px) she is drawn at anywhere she can walk (her height times the depth's scale and the hero
    scale), with a pixel to spare either way"""
    zs = grid["z0"] + np.arange(grid["nz"]) * grid["d"]
    z = zs[(grid["room"] > 0).any(1)]
    h = P.FIG_H * P.ppm(z) * P.hero(z)
    return int(math.floor(h.min())) - 1, int(math.ceil(h.max())) + 1


def walker_rims(g, lamp, hgt, ax, ay, L_):
    """the light's edge, placed the way a pixel artist places it: the sun's salmon rim on the silhouette pixels of the
    hood, shoulders and scarf that face up-left (the low sun behind-left); in the lamp variant three short broken
    mint highlights on her left side (the headlamps beside her)"""
    rim_mats = {L_(c) for k in ("coat", "hood", "scarf") for c in WALKER_RAMPS[k][1]}
    scarf = {L_(c) for c in WALKER_RAMPS["scarf"][1]}
    p = np.pad(g, 1)
    up_e, left_e, ul_e = p[:-2, 1:-1] == 0, p[1:-1, :-2] == 0, p[:-2, :-2] == 0
    R, Cc = np.mgrid[0:g.shape[0], 0:g.shape[1]]
    body = np.isin(g, list(rim_mats))
    hood = np.isin(g, [L_(c) for c in WALKER_RAMPS["hood"][1]])
    sun = body & (Cc <= ax) & (R < ay - 0.55 * hgt) & ((hood & (up_e | left_e | ul_e)) | (~hood & left_e))
    out = g.copy()
    out[sun & np.isin(g, list(scarf))] = L_("#f0b4c0")
    out[sun & ~np.isin(g, list(scarf))] = L_("#e6a6a6")
    if lamp:
        # the lamp's light as three short broken highlights on the side toward it (hood, shoulder, coat hem), each
        # 2+ px long; never a continuous outline
        for lo, hi in ((0.97, 0.84), (0.72, 0.62), (0.34, 0.25)):
            y0, y1 = ay - lo * hgt, ay - hi * hgt
            if y1 - y0 < 2:
                y1 = y0 + 2
            seg = (g > 0) & left_e & (R >= y0) & (R < y1)
            out[seg] = L_("#a8c8a0")
    return out


def walker_sheet(work: Path, out: Path, heights: tuple) -> dict:
    """the walker's data render -> one sprite per height, heading and pose: every render pixel picks its material's
    band (and the mint band where the lamps' light reaches, for the lamp variant), then each output pixel takes the
    most common label of the render pixels inside it (more than half empty = empty) and 1 px orphans are cleaned away.
    A row of cells per height (each row's cells sized to it, rows listed in walker.json); across a row, heading by
    heading, each pose plain then lamp-lit. The feet sit on the anchor pixel's bottom edge."""
    work, out = Path(work), Path(out)
    raw = load_raw(work, "walker")
    lamp = load_raw(work, "walker_lamp")
    meta = json.loads((work / "raw" / "walker.json").read_text())
    pxm = meta["pxm"]
    a = raw[..., 3] > 0.5
    lit = (raw[..., 0] - 0.2) / 0.4
    ll = (lamp[..., 0] - 0.2) / 0.4
    mid = np.round(raw[..., 1] * 64).astype(int)
    cols = []                                    # label -> hex
    lab = {}

    def L_(h):
        if h not in lab:
            lab[h] = len(cols) + 1
            cols.append(h)
        return lab[h]
    base = np.zeros(a.shape, np.int32)
    lit_l = np.zeros(a.shape, np.int32)
    for name, m in WALKER_MID.items():
        sel = a & (mid == m)
        th, keys = WALKER_RAMPS[name]
        ids = np.array([L_(k) for k in keys])
        base[sel] = lit_l[sel] = ids[np.digitize(lit[sel], th)]
        if name in WALKER_MINT:
            mk = WALKER_MINT[name]
            v, cur = ll[sel], lit_l[sel]
            cur = np.where(v > 0.55, L_(mk[0]), cur)
            lit_l[sel] = np.where(v > 0.85, L_(mk[1]), cur)
    hmin, hmax = heights
    sizes = [(hgt, int(math.ceil(WALKER_CELL[0] * hgt / P.FIG_H)) + 2, int(math.ceil(WALKER_CELL[1] * hgt / P.FIG_H)) + 1)
             for hgt in range(hmin, hmax + 1)]
    n_cells = len(meta["feet"]) * 2
    sheet = np.zeros((sum(ch for _, _, ch in sizes), n_cells * max(cw for _, cw, _ in sizes), 4), np.uint8)
    rgbs = np.array([[0, 0, 0]] + [D.rgb(c) for c in cols], np.uint8)
    nl = len(cols) + 1
    cell_w, cell_h = meta["cell"]
    rows, y_off = [], 0
    for hgt, cw, ch in sizes:
        ax, ay = cw // 2, ch - 1                  # the anchor pixel: her feet stand on its bottom edge
        s = hgt / P.FIG_H / pxm                   # output px per render px
        for fi, (fx, fy) in enumerate(meta["feet"]):
            y0, x0 = max(int(fy - 0.92 * cell_h), 0), max(int(fx - cell_w / 2), 0)
            YY, XX = np.mgrid[y0:int(fy + 0.08 * cell_h), x0:int(fx + cell_w / 2)]
            c = np.floor((XX + 0.5 - fx) * s + ax + 0.5).astype(int)
            r = ay - np.floor((fy - YY - 0.5) * s).astype(int)
            ok = (c >= 0) & (c < cw) & (r >= 0) & (r < ch)
            for vi, labs in enumerate((base, lit_l)):
                lb = labs[YY[ok], XX[ok]]
                cnt = np.bincount((r[ok] * cw + c[ok]) * nl + lb, minlength=ch * cw * nl).reshape(ch * cw, nl)
                tot, fill = cnt.sum(1), cnt[:, 1:].sum(1)
                g = np.where((fill * 2 >= tot) & (tot > 0), np.argmax(cnt[:, 1:], 1) + 1, 0).reshape(ch, cw)
                g2 = D.mode_clean(g, 2, keep=(g == 0))              # inside her only: the silhouette never erodes
                g = walker_rims(np.where((g > 0) & (g2 == 0), g, g2), vi, hgt, ax, ay, L_)
                X_ = (fi * 2 + vi) * cw
                sheet[y_off:y_off + ch, X_:X_ + cw, :3] = rgbs[g]
                sheet[y_off:y_off + ch, X_:X_ + cw, 3] = np.where(g > 0, 255, 0)
        rows.append([y_off, cw, ch, ax, ay])
        y_off += ch
    from PIL import Image
    Image.fromarray(sheet, "RGBA").save(out / "walker.png", optimize=True)
    info = dict(src="walker.png", hmin=hmin, hmax=hmax, poses=meta["poses"], headings=meta["headings"],
                variants=["plain", "lamp"], rows=rows, knot=meta["knot"], mouth=meta["mouth"])
    (out / "walker.json").write_text(json.dumps(info))
    return info
