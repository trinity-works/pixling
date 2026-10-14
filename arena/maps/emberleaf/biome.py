"""Emberleaf Hollow's biome: an autumn-red forest at midday. Materials and their ramps, the zones' budgets for this
palette, and the painter's hooks (arena/paint.py calls them in order: frame_trees -> sky -> ground -> (step, clean)
-> after_clean -> (sky pixels) -> after_sky):

- ground: the ground's parts per pixel from where it is (u, v): the fighting ground's dirt (two tones in big soft
  patches), the grass (shade, body, lime patches, darker clumps with scalloped edges), a dark rim of grass along the
  dirt's edge, the forest floor in the trees' shade, the pond's wet bank;
- after_clean: the marks stamped after the cleanup, so they keep their size: flat cobbles on the dirt (a lit crescent
  toward the sun, a shadowed lower edge), painted tufts along the dirt's edge and the hollow's rim, flower sprinkles and
  mushrooms in the grass, fallen petals under the red crowns, the pond's water (darker under the bank, lighter in the
  middle, sky streaks), the sun's peach rim on the crowns that stand against the back;
- sky: a midday gradient by screen height, pale and warm over the hills.
"""
from __future__ import annotations

import math
import random

import numpy as np

from ... import zones as Z
from . import place as P

TITLE = "Emberleaf Hollow"
FOG = "fog"
# the shared table (arena/zones.py) moved to this palette: a saturated, lighter world than Hushfall's dusk. The steps,
# strokes and cleanups stay shared, except the frame and backdrop keep one more step (the crowns' plum, magenta, coral
# and peach need four; STYLE.md allows frame 3-4)
ZONE_OVERRIDES = {
    # (a map that paints its step boundaries with dabs may raise the playfield's cleanup share: STYLE.md)
    "playfield": dict(value=(0.36, 0.76), sat=0.38, sun=0.5, clean=(3, 0.45)),
    "frame":     dict(value=(0.10, 0.64), sat=0.50, sun=0.55, steps=4),
    "backdrop":  dict(haze=(0.34, 0.44, 0.50), far=(50.0, 75.0), value=(0.32, 0.53), sat=0.20, sun=0.30, steps=4,
                      rise=(0.0, 0.03, 0.04)),
    # the haze bank lies on the far hills (level 1); the cumulus stand over it, lighter (level 2)
    "vista":     dict(haze=(0.30, 0.40, 0.22), far=(150.0, 240.0), value=(0.62, 0.77), sat=0.14, sun=0.2),
    "sky":       dict(value=(0.58, 0.88), sat=0.3, sun=0.2),
}
# the embers' colours (coral and pink, palette.SUN_HUES) and the neutral each becomes where a zone has no sun
SUN_KEYS = {"cr_hi": "cl_hi", "cr_lit": "cl_lit", "cr": "cl_mid", "cr_sh": "rk_lit", "ce_hi": "cl_hi", "ce_lit": "cl_lit",
            "ce": "cl_mid", "ce_sh": "rk_lit", "fl_pink": "cl_hi", "mu_cap": "wd_lit", "rune": "cl_hi"}
# how much of each zone the embers may cover (saturated coral, chroma > 0.3): the crowns are the frame's colour
PF_LO_GAP = 0.25          # the playfield's darks (grass in a crown's shade) stand this far above a unit's outline
SUN_SHARE = {"playfield": 0.004, "frame": 0.45, "backdrop": 0.30, "vista": 0.02, "sky": 0.0}

MAT = dict(grass=1, dirt=2, cobble=3, grass_dk=4, grass_lt=5, grass_hi=6, floor=7, cliff=8, water=9, bank=10,
           dirt_lt=11, boulder=12, boulder_top=13, bark=14, wood=15, wood_end=16, ruin=17, moss=18,
           crown_coral=20, crown_ember=21, pine=22, pine_hi=23, bush_green=24, bush_red=25, reed=26,
           waystone=27, rune=28, lamp=29, metal=30,
           far_ground=33, far_coral=34, far_green=35, river=36, hills=37, cloud=38,
           tuft=42, sky=43, fern=44, floor_lt=45, cloth=46, clay=47, dirt_pk=48)
# (lit thresholds, palette keys): lit ~0.39 in full shade, ~1.2 on flat ground in the sun; cards (crowns, needles)
# run 0.28 .. 1.6 from their dark side to the sun's
RAMPS = {
    # the fighting ground: dirt in two tones, the cobbles' body
    "dirt": ([0.74], ["dt_sh", "dt"]),
    "dirt_lt": ([0.74], ["dt_sh", "dt_lit"]),
    "dirt_pk": ([0.74], ["dt_sh", "dt_pk"]),            # packed wear lines: a step darker, smoother
    "cobble": ([0.74], ["dt_sh", "cb"]),
    # grass: shade and body, the lime patches, the darker clumps
    "grass": ([0.74], ["gr_sh", "gr"]),
    "grass_lt": ([0.74], ["gr_sh", "gr_lit"]),
    "grass_hi": ([0.74], ["gr_sh", "gr_hi"]),
    "grass_dk": ([0.74], ["gr_teal", "gr_sh"]),       # the field's deep shade: teal, never grey
    "tuft": ([0.74], ["gr_deep", "gr_hi"]),
    # the forest floor under the frame's trees, the plateau's lip and cliffs
    "floor": ([0.6, 0.95], ["ff_dk", "ff", "ff_lit"]),
    # the floor's first metres past the hollow's rim: the step between the field's teal shade and the forest's
    "floor_lt": ([0.6, 0.95], ["ff", "ff_lit", "gr_teal"]),
    "cliff": ([0.5, 0.8, 1.05], ["cf_dk", "cf", "cf_lit", "rk_lit"]),
    "bank": ([0.7], ["shore", "ff"]),
    "water": ([0.7], ["wa_deep", "wa"]),
    "lily": ([0.74], ["lily", "lily_lit"]),
    # boulders: slate, warm-grey tops; the ruin, a step warmer, mossy
    "boulder": ([0.42, 0.78, 1.08], ["rk_sh", "rk", "rk_lit", "rk_hi"]),
    "boulder_top": ([0.7, 1.0], ["rk", "rk_lit", "rk_hi"]),
    "ruin": ([0.5, 0.8, 1.1], ["rs_sh", "rs", "rs_lit", "rk_hi"]),
    "moss": ([0.7, 1.0], ["gr_deep", "moss", "gr_lit"]),
    # wood: bark, logs, stumps, the cut ends
    "bark": ([0.45, 0.8], ["wd_dk", "wd", "wd_lit"]),
    "wood": ([0.5, 0.85], ["wd_dk", "wd", "wd_lit"]),
    "wood_end": ([0.75], ["wd_ring", "wd_end"]),
    # the crowns: plum undersides, magenta, coral, its light; the peach comes as the sun's rim (after_clean)
    "crown_coral": ([0.44, 0.7, 1.26], ["cr_under", "cr_mag", "cr", "cr_lit"]),
    "crown_ember": ([0.44, 0.7, 1.26], ["ce_under", "ce_mag", "ce", "ce_lit"]),
    # pines: deep teal needles, a lighter shelf on the upper boughs
    "pine": ([0.42, 0.62, 0.9], ["pn_deep", "pn_sh", "pn", "pn_lit"]),
    "pine_hi": ([0.7, 1.0], ["pn", "pn_lit", "pn_hi"]),
    "bush_green": ([0.5, 0.8, 1.1], ["ff_dk", "bu_sh", "bu", "bu_lit"]),
    "bush_red": ([0.5, 0.8, 1.1], ["ce_under", "cr_mag", "ce", "cr"]),
    # ferns and leafy plants: the reference's bright big-leaf plants by the path
    "fern": ([0.5, 0.85, 1.2], ["gr_deep", "bu", "bu_lit", "gr_lit"]),
    "reed": ([0.8], ["reed", "reed_lit"]),
    # the camps: bedrolls, banners (neutral linen), clay pots
    "cloth": ([0.6, 0.95], ["cloth_dk", "cloth", "cloth_lit"]),
    "clay": ([0.6, 0.95], ["wd", "wd_lit", "wd_end"]),
    # the spawns' waystones: grey stone, a glowing rune; the lanterns
    "waystone": ([0.5, 0.85, 1.15], ["rs_sh", "rs", "rs_lit", "rk_hi"]),
    "rune": ([], ["rune"]),
    "lamp": ([], ["lamp"]),
    "metal": ([0.6], ["ink2", "rk_sh"]),
    # the back: the valley's canopy (coral and green), its ground, the river; the hills
    "far_ground": ([0.8], ["ff", "vf"]),
    "far_coral": ([0.4, 0.62, 1.0], ["cr_under", "cr_sh", "cr", "cr_lit"]),
    "far_green": ([0.55, 0.85, 1.1], ["pn_sh", "pn", "bu", "bu_lit"]),
    "river": ([0.9], ["wa_lit", "rv"]),
    "hills": ([0.62, 0.9], ["hl_sh", "hl", "hl_lit"]),
    "cloud": ([0.45, 0.6, 0.72, 0.84], ["cl_base", "cl_shade", "cl_mid", "cl_lit", "cl_hi"]),
}
CLOUD_MATS = (MAT["cloud"],)
CROWN_MATS = (MAT["crown_coral"], MAT["crown_ember"], MAT["bush_red"])
TREE_MATS = (MAT["crown_coral"], MAT["crown_ember"], MAT["pine"], MAT["pine_hi"], MAT["bark"], MAT["far_coral"],
             MAT["far_green"])
GROUND_MATS = (MAT["grass"], MAT["floor"])
# the shared step-edge pass (paint.dab_edges), opt-in: ramp-step boundaries become dabs, per material family
DAB_EDGES = ("playfield", "frame")
DAB_MATS = ("grass", "grass_lt", "grass_hi", "grass_dk", "floor", "floor_lt", "dirt", "dirt_lt", "dirt_pk")
DAB_FAMILIES = (("grass", "grass_lt", "grass_hi", "grass_dk", "floor", "floor_lt"), ("dirt", "dirt_lt", "dirt_pk"))
SWAY_KINDS = ("oak", "pine")
CLOUD_LAYERS = ("far",)
CAP = False
RENDER_PASSES = ("world", "back", "cfar", "ids")
LIGHT = dict(sun=1.0, fill=0.32, world=0.28)


def _k():
    from ... import paint
    return paint.KIDX


def _fbm(u, v, scale, seed, oct=3):
    return P.fbm(u, v, scale, seed, oct)


def textures(out):
    """the map's own alpha atlas for big-leaf plants (2 x 2 tiles like the kit's dabs and puffs): leaves.png"""
    from PIL import Image, ImageDraw
    T = 256
    img = Image.new("L", (2 * T, 2 * T), 0)
    d = ImageDraw.Draw(img)
    r_ = random.Random(3)
    for ty in range(2):
        for tx in range(2):
            ox, oy = tx * T, ty * T
            for j in range(3 if (tx + ty) % 2 else 1):            # one big leaf, or a spray of three
                ang = r_.uniform(-0.9, 0.9) + (j - 1) * 0.7
                L_ = T * (0.88 if j == 0 else 0.62)
                cx, cy = ox + T / 2, oy + T * 0.85
                pts = []
                for i in range(40):
                    t_ = i / 39
                    w = T * 0.2 * math.sin(math.pi * t_) ** 0.8 * (1.1 - 0.4 * t_)
                    pts.append((t_, w))
                poly = [(cx + math.sin(ang) * t_ * L_ + math.cos(ang) * w, cy - math.cos(ang) * t_ * L_ + math.sin(ang) * w)
                        for t_, w in pts]
                poly += [(cx + math.sin(ang) * t_ * L_ - math.cos(ang) * w, cy - math.cos(ang) * t_ * L_ - math.sin(ang) * w)
                         for t_, w in reversed(pts)]
                d.polygon(poly, fill=255)
    out.mkdir(parents=True, exist_ok=True)
    img.save(out / "leaves.png")


# ---------------------------------------------------------------- the sky
def sky(H, W, s=1.0, x0=0, y0=0):
    """midday: soft blue at the top, paler toward the hills, a warm pale band on the horizon; thin high streaks"""
    K = _k()
    yy, xx = np.mgrid[y0:y0 + H, x0:x0 + W].astype(np.float64)
    p0 = (P.Y0 - yy / s) / P.PPM
    ph = P.P_BACK + 7.0                                   # the horizon, behind the far hills
    # the visible strip is short at 68 degrees, so the gradient runs on screen height over the far hills (about 2.3 m
    # of the picture): blue at the top, the warm glow only just over the hills
    p = (p0 - ph) + 2.4 + 0.12 * P.fbm(xx / s / 70, yy / s / 25, 2.0, 5) + 0.15 * (xx / (P.W * s) - 0.5)
    idx = np.full((H, W), K["sk_top"], np.int32)
    idx[p < 2.2] = K["sk_hi"]
    idx[p < 1.5] = K["sk_mid"]
    idx[p < 0.9] = K["sk_lo"]
    idx[p < 0.45] = K["glow"]
    st = P.fbm(xx / s / 700, p0 * 1.4, 1.0, 61) + 0.5 * P.fbm(xx / s / 200, p0 * 3.0, 1.0, 62)
    band = (p > 1.7) & (p < 6.0)
    idx[band & (st > 0.45)] = K["sk_mid"]
    idx[band & (st < -0.5)] = K["sk_top"]
    sea = np.zeros((H, W), bool)
    return idx, sea


# ---------------------------------------------------------------- the ground painter
def frame_trees(lay):
    return [(t["u"], t["v"]) for t in lay["things"] if t["kind"] in ("oak", "pine")]


def pool(u, v):
    """the light pool on the fighting ground: 1 in its middle, 0 about 8 m out, negative toward the hollow's ends and
    rim (the frame's shade). Added to the lit value before stepping (scaled by POOL)"""
    cu, cv = P.GROUND[0], P.GROUND[1]
    r = np.hypot((np.asarray(u) - cu) / 18.5, (np.asarray(v) - cv) / 9.0)
    return (1 - P.smooth(0.35, 1.0, r)) - 1.4 * P.smooth(1.05, 1.75, r)


POOL = (0.22, 0.42)        # (lift in the pool's middle, darkening at its far edge) in lit units
SUN_UV = np.array([-0.62, 0.52]) / np.hypot(-0.62, 0.52)


def wear_dist(u, v):
    """metres from the nearest wear line: the routes across the fighting ground (centre and south lanes) and the dirt
    paths' middles, mirrored"""
    u = np.asarray(u, np.float64); v = np.asarray(v, np.float64)
    best = P.lane_dist(u, v)
    for name in ("centre",):
        pts = [p_ for p_ in P.LANES[name] if abs(p_[0]) < 14.0]
        for (a, b, _), (c_, d, _) in zip(pts, pts[1:]):
            du, dv = c_ - a, d - b
            t = np.clip(((u - a) * du + (v - b) * dv) / (du * du + dv * dv), 0, 1)
            best = np.minimum(best, np.hypot(u - a - t * du, v - b - t * dv))
    return best


def ground(c):
    aw, useb, mid, z, gu, gv, zone, lit = c["aw"], c["useb"], c["mid"], c["z"], c["gu"], c["gv"], c["zone"], c["lit"]
    g = aw & ~useb & np.isin(mid, GROUND_MATS) & (z > -2.5)
    u, v = gu[g], gv[g]
    pf = zone[g] == Z.CODE["playfield"]
    sd = P.sd_dirt(u, v)
    # the light: a pool on the fighting ground, the hollow's ends and rim in the frame's shade (lit is stepped later)
    pl = pool(u, v) + 0.2 * _fbm(u, v, 5.0, 171) + 0.04 * _fbm(u, v, 1.3, 172)    # a soft, slightly irregular glade
    sd0 = P.sd_dirt(u, v)
    # the pool lifts the middle; the frame's shade darkens the grass toward the ends, not the dirt (the spawns' glades
    # and paths stay calm, one tone)
    # (the glades' camps keep a little light: the ends' shade eases round each spawn)
    near_sp = np.exp(-(np.hypot(np.abs(u) - P.SPAWNS["east"][0], v - P.SPAWNS["east"][1]) / 5.5) ** 2)
    lit[g] = lit[g] + np.where(pl > 0, POOL[0] * pl, np.where(sd0 > 0, POOL[1] * pl * (1 - 0.65 * near_sp), 0.0))
    # grass: one lawn whose tone comes from the light (the pool's lime, the body, the frame's teal shade); the bands
    # are smooth (the pool's ellipses), their boundaries dabbed by the step-edge pass; no noise patches
    cls = np.full(u.shape, MAT["grass"], np.int32)
    cls[pl > 0.12] = MAT["grass_lt"]
    cls[pl > 0.6] = MAT["grass_hi"]
    cls[pl < -0.45] = MAT["grass_dk"]
    n = np.zeros(u.shape)
    # the dirt: one calm tone, a step lighter in the light pool (no stain blobs)
    dirt = sd <= 0
    gcu, gcv, gru, grv, gp = P.GROUND
    # granular dirt (ground_research.md): the fighting ground's base the light tone, the paths and glades one step
    # down; the wear lines where feet go (the routes and the paths' middles) packed a step darker and smoother
    oval = P.sd_ellipse(u, v, gcu, gcv, gru + 0.8, grv + 0.8, gp) + 0.3 * _fbm(u, v, 1.5, 112) < 0
    # the paths' trodden middles a step darker (broken), not in the glades; on the fighting ground the wear shows
    # only as smoother soil (less grain: granular())
    glade = np.hypot(np.abs(u) - P.SPAWNS["east"][0], v - P.SPAWNS["east"][1]) < P.GLADE_R - 0.3
    rgw = np.random.default_rng(113)                         # a continuous trodden line, its edge dissolving
    wear = (P.lane_dist(u, v) + 0.08 * _fbm(u, v, 1.2, 113) < 0.3 + 0.18 * rgw.random(len(u))) & ~glade
    cls[dirt] = np.where(oval[dirt], MAT["dirt_lt"], np.where(wear[dirt], MAT["dirt_pk"], MAT["dirt"]))
    # outside the hollow: the forest floor, but the shelf in the window over the knoll is long grass;
    # the pond's wet bank
    shelf = (~pf) & (v > 8.0) & (np.abs(u) < 12.0) & (z[g] > -1.0)
    # the forest floor darkens away from the rim in soft, broken bands (no contour where the field ends): the field's
    # teal shade first, then the floor's light step, then the floor
    tb = P.sd_play(u, v) + 0.7 * _fbm(u, v, 1.3, 115) + 0.3 * _fbm(u, v, 0.45, 116)
    cls[~pf & ~shelf] = np.where(tb[~pf & ~shelf] < 0.9, MAT["grass_dk"],
                                 np.where(tb[~pf & ~shelf] < 2.2, MAT["floor_lt"], MAT["floor"]))
    cls[shelf] = np.where(n[shelf] > 0.2, MAT["grass_dk"], MAT["floor"])
    bank = (P.sd_pond(u, v) < 0.12) & (z[g] < 0.05)
    cls[bank & ~dirt] = MAT["bank"]
    out = mid.copy()
    out[g] = cls
    return out


# ---------------------------------------------------------------- the marks after the cleanup
def _stamp(idx, x, y, key_px):
    H, W = idx.shape
    for dx, dy, k in key_px:
        xx, yy = x + dx, y + dy
        if 0 <= xx < W and 0 <= yy < H:
            idx[yy, xx] = k


def _ring(H, W, x, y, rx, ry, w=1.5):
    """pixels of an elliptic ring (the projected foot of a round prop)"""
    x0, x1 = max(0, int(x - rx - 3)), min(W, int(x + rx + 4))
    y0, y1 = max(0, int(y - ry - 3)), min(H, int(y + ry + 4))
    if x1 <= x0 or y1 <= y0:
        return np.zeros((0,), int), np.zeros((0,), int), np.zeros((0,))
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.hypot((xx - x) / max(rx, 1), (yy - y) / max(ry, 1))
    m = d < 1.0 + w / max(rx, 1)
    return yy[m], xx[m], d[m]


def _proj_s(u, v, s):
    x, y = P.proj(u, v, float(P.terrain(np.array(u), np.array(v))))
    return x * s, y * s


def after_clean(c, idx):
    K = _k()
    s = c["s"]
    ps = c.get("sp", s)                    # pixel sizes of the marks scale with px per metre (set at 32 px/m)
    mid, zone, gu, gv, lit, a, z = c["mid"], c["zone"], c["gu"], c["gv"], c["lit"], c["a"], c["z"]
    H, W = idx.shape
    pf = zone == Z.CODE["playfield"]
    sun = lit > 0.74
    rng = random.Random(5)
    lay = P.layout()
    grassm = np.isin(mid, [MAT["grass"], MAT["grass_lt"], MAT["grass_hi"], MAT["grass_dk"]]) & pf
    dm = np.isin(mid, [MAT["dirt"], MAT["dirt_lt"]]) & pf
    fl = mid == MAT["floor"]

    # --- the grass stands a little proud of the dirt: a lit lip on the grass where its edge faces the sun, a shadow
    # band on the dirt where the grass stands between it and the sun; the edge itself scalloped in lobes
    near = (grassm | dm)
    sdg = np.full(gu.shape, 9.0)
    sdg[near] = P.sd_dirt(gu[near], gv[near])
    e = 0.05
    gx = (P.sd_dirt(gu[near] + e, gv[near]) - P.sd_dirt(gu[near] - e, gv[near])) / (2 * e)
    gy = (P.sd_dirt(gu[near], gv[near] + e) - P.sd_dirt(gu[near], gv[near] - e)) / (2 * e)
    nl = np.hypot(gx, gy) + 1e-6
    facing = np.zeros(gu.shape)
    facing[near] = (gx * SUN_UV[0] + gy * SUN_UV[1]) / nl          # > 0: the grass lies toward the sun
    lobes = np.zeros(gu.shape)
    lobes[near] = 0.07 * np.abs(P.fbm(gu[near], gv[near], 0.55, 141, 2)) + 0.03 * np.abs(P.fbm(gu[near], gv[near], 0.25, 142, 2))
    # a lighter lip all round the grass's edge (wider where it faces the sun), a thin cast shadow on the dirt where
    # the grass stands between it and the sun
    lipw = 0.05 + 0.6 * lobes + 0.06 * (facing < -0.15)
    lip = grassm & (sdg > 0) & (sdg < lipw)
    idx[lip & sun] = K["gr_hi"]
    upk_ = {K["gr_teal"]: K["gr_sh"], K["gr_sh"]: K["gr"], K["gr"]: K["gr_lit"]}
    for a_, b_ in upk_.items():
        idx[lip & ~sun & (idx == a_)] = b_
    band = dm & (sdg > -0.05 - 0.3 * lobes) & (facing > 0.25)       # a thin cast shadow, not an outline
    idx[band] = K["dt_sh"]

    # --- the water: deeper toward the middle, a shallow lighter rim, the far bank's sky reflection, soft highlights;
    # shade from the stones and trees keeps it deep; lily pads and floating red leaves
    wm = mid == MAT["water"]
    if wm.any():
        cu, cv, hu, hv = P.POND
        u, v = gu[wm], gv[wm]
        dp = P.sd_pond(u, v)
        main = np.hypot((u - cu) / hu, (v - cv) / hv) < 1.6
        refl = np.where(main, (v - cv) / hv, 0.0) + 0.3 * P.fbm(u, v, 1.6, 132)
        # depth in four soft bands that follow the shore (distance in from the bank), their edges broken by a fine
        # checker so they blend; one band lighter on the far side (the sky in it), a light line on the far bank
        bodies = [P.POND] + [(sg * pu, pv, phu, phv) for pu, pv, phu, phv in P.POOLS for sg in (-1, 1)]
        refl = np.full(u.shape, -9.0)
        for (bu_, bv_, bhu, bhv) in bodies:
            inb = np.hypot((u - bu_) / bhu, (v - bv_) / bhv) < 1.7
            refl = np.where(inb, np.maximum(refl, (v - bv_) / bhv), refl)
        dj = dp + 0.12 * P.fbm(u, v, 0.8, 133) + 0.05 * P.fbm(u, v, 0.25, 136)
        ys_, xs_ = np.nonzero(wm)
        chk = ((ys_ + xs_) % 2 == 0)
        band = np.zeros(u.shape, np.int32)                    # 0 shallows .. 3 deep
        for k_, th in enumerate((-0.28, -0.7, -1.2)):
            band += (dj < th - 0.05) | ((dj < th + 0.05) & chk)
        band -= ((refl > 0.25 + 0.2 * P.fbm(u, v, 1.0, 137)) & (band > 0)).astype(np.int32)   # the sky on the far side
        band[~sun[wm]] = np.minimum(3, band[~sun[wm]] + 1)
        cols = np.array([K["wa_lit"], K["wa"], K["wa_mid"], K["wa_deep"]])
        wsub = cols[band]
        top = np.zeros_like(wm)
        top[1:, :] = wm[1:, :] & ~wm[:-1, :]
        for _ in range(max(1, int(round(1 * ps)))):
            top[1:, :] |= top[:-1, :] & wm[1:, :]
        wsub[top[wm] & sun[wm]] = K["wa_sh"]
        streak = (np.sin(v * 7.0 + 1.6 * np.sin(u * 0.7)) > 0.95) & (dp < -0.5) & (P.fbm(u, v, 1.2, 131) > 0.1)
        wsub[streak & (refl > -0.2) & sun[wm]] = K["wa_hi"]
        idx[wm] = wsub
        r_ = random.Random(17)
        pads = 0
        for _ in range(60):
            if pads >= 12:
                break
            if r_.random() < 0.75:
                a_ = r_.uniform(0, math.tau); rr = r_.uniform(0.55, 0.92)
                pu_, pv_ = cu + math.cos(a_) * hu * rr, cv + math.sin(a_) * hv * rr
            else:
                pu0, pv0, phu, phv = P.POOLS[0]
                sgn = r_.choice((-1, 1)); a_ = r_.uniform(0, math.tau); rr = r_.uniform(0.2, 0.6)
                pu_, pv_ = sgn * pu0 + math.cos(a_) * phu * rr, pv0 + math.sin(a_) * phv * rr
            x, y = P.proj(pu_, pv_, P.WATER_Z)
            x, y = int(x * s), int(y * s)
            if not (0 <= y < H and 0 <= x < W and wm[y, x]):
                continue
            pads += 1
            R = max(2, int(round(r_.uniform(2.0, 3.4) * ps)))
            px_ = []
            for yy in range(-R, R + 1):
                for xx in range(-R - 1, R + 2):
                    if (xx / (R + 0.8)) ** 2 + (yy / (R * 0.7)) ** 2 <= 1 and not (xx > 0 and abs(yy) <= max(0, xx // 3)):
                        px_.append((xx, yy, K["lily_lit"] if (xx + yy) < 0 else K["lily"]))
            if r_.random() < 0.35:
                px_.append((0, -1, K["fl_pink"])); px_.append((0, 0, K["fl_white"]))
            _stamp(idx, x, y, px_)
        for _ in range(6):                                       # floating red leaves
            a_ = r_.uniform(0, math.tau); rr = r_.uniform(0.15, 0.7)
            x, y = P.proj(cu + math.cos(a_) * hu * rr, cv + math.sin(a_) * hv * rr, P.WATER_Z)
            x, y = int(x * s), int(y * s)
            if 0 <= y < H and 0 <= x < W and wm[y, x]:
                c1, c2 = (K["cr_lit"], K["cr_mag"]) if r_.random() < 0.6 else (K["ce_lit"], K["ce_mag"])
                _stamp(idx, x, y, [(1, -1, c1), (0, 0, c1), (1, 0, c1), (2, 0, c1), (0, 1, c2), (1, 1, c2), (2, 1, c1),
                                   (1, 2, c2), (3, 1, c2)])

    # --- props sit in the ground: a dark contact ring and a few tufts round the boulders; rings on the cut stumps;
    # the ruin's courses; the lanterns' light on the ground
    for t in lay["things"]:
        k = t["kind"]
        if k == "boulder" and t["r"] >= 0.5 and t.get("zone") == "frame":
            x, y = _proj_s(t["u"], t["v"], s)
            rx, ry = t["r"] * 1.05 * P.PPM * s, t["r"] * 1.05 * P.PPM * P.SE * s
            yy, xx, d = _ring(H, W, x, y, rx, ry, 2.0 * ps)
            # the contact shadow: the lower half of the foot, heavier on the side away from the sun
            awayx = (xx - x) / max(rx, 1) * 0.6 + (yy - y) / max(ry, 1)
            m = (d >= 0.9) & (awayx > 0.55) & (grassm[yy, xx] | dm[yy, xx] | fl[yy, xx])
            idx[yy[m], xx[m]] = K["gr_deep"]
        if k == "lantern":
            x, y = _proj_s(t["u"], t["v"], s)
            yy, xx, d = _ring(H, W, x, y, 1.0 * P.PPM * s, 1.0 * P.PPM * P.SE * s, 0)
            m = (d < 1.0) & grassm[yy, xx] & (idx[yy, xx] == K["gr"])
            idx[yy[m], xx[m]] = K["gr_lit"]
    we = mid == MAT["wood_end"]
    if we.any():
        cents = [(t["u"], t["v"]) for t in lay["things"] if t["kind"] == "stump"]
        u, v = gu[we], gv[we]
        dmin = np.full(u.shape, 9.0)
        for (cu, cv) in cents:
            dmin = np.minimum(dmin, np.hypot(u - cu, v - cv))
        ring = (dmin < 1.0) & ((dmin / 0.075) % 1 < 0.35)
        sub = idx[we]
        sub[ring] = K["wd_ring"]
        idx[we] = sub
    rm = mid == MAT["ruin"]
    if rm.any():
        zz = z[rm]
        line = ((zz + 0.25) / 0.48) % 1 < 0.13
        sub = idx[rm]
        sub[line] = K["rs_sh"]
        idx[rm] = sub

    # --- the lawn's brush texture: short strokes along a slow flow, one step lighter in the light (two in the pool's
    # middle), one darker in the shade; sparse, so the field stays calm
    rs = np.random.default_rng(41)
    ys, xs = np.nonzero(grassm | fl)
    pick = rs.random(len(ys)) < 0.009
    ys, xs = ys[pick], xs[pick]
    up = {K["gr_sh"]: K["gr"], K["gr"]: K["gr_lit"], K["gr_lit"]: K["gr_hi"], K["gr_hi"]: K["gr_lit"],
          K["gr_deep"]: K["gr_sh"], K["gr_teal"]: K["gr_sh"], K["ff"]: K["ff_lit"], K["ff_dk"]: K["ff"], K["ff_lit"]: K["gr_sh"]}
    down = {K["gr"]: K["gr_sh"], K["gr_lit"]: K["gr"], K["gr_hi"]: K["gr_lit"], K["gr_sh"]: K["gr_teal"],
            K["ff_lit"]: K["ff"], K["ff"]: K["ff_dk"]}
    ang = (0.5 * math.pi * P.fbm(gu[ys, xs], gv[ys, xs], 4.0, 151) + 0.35 * math.pi)
    L_ = max(2, int(round(3 * ps)))
    for y, x, an in zip(ys, xs, ang):
        k0 = int(idx[y, x])
        col = (up if sun[y, x] else down).get(k0)
        if col is None:
            continue
        ca, sa = math.cos(an), math.sin(an)
        for t_ in range(L_):
            py, px = int(round(y - sa * t_)), int(round(x + ca * t_))
            if 0 <= py < H and 0 <= px < W and idx[py, px] == k0:
                idx[py, px] = col

    # --- dappled light: round sun-spots (0.15-0.4 m, flattened by the view) in the trees' shade near the canopy, on
    # the grass, the forest floor and the dirt; each one step lighter, its rim checkered so it is soft
    shade = (grassm | fl | dm | (mid == MAT["floor_lt"])) & ~sun
    if shade.any():
        nk = max(K.values()) + 1
        lut = np.arange(nk)
        for a_, b_ in (("gr_sh", "gr"), ("gr_teal", "gr_sh"), ("gr_deep", "gr_sh"), ("ff_dk", "ff"), ("ff", "ff_lit"),
                       ("ff_lit", "gr_teal"), ("dt_sh", "dt"), ("dt", "dt_lit"), ("cb_sh", "cb"), ("gr", "gr_lit")):
            lut[K[a_]] = K[b_]
        trees_ = np.array([(t["u"], t["v"]) for t in lay["things"] if t["kind"] in ("oak", "pine")])
        rd = random.Random(61)
        fy, fx = np.nonzero(shade)
        n_sp = int(len(fy) / (1.5 * P.PPM * s) ** 2)
        for i_ in rd.sample(range(len(fy)), min(len(fy), n_sp)):
            y, x = int(fy[i_]), int(fx[i_])
            u0, v0 = gu[y, x], gv[y, x]
            dmin = np.min(np.hypot(trees_[:, 0] - u0, trees_[:, 1] - v0))
            if dmin > 6.5 or rd.random() < dmin / 9.0:         # thicker near the trunks, none far out
                continue
            rx = rd.uniform(0.15, 0.4) * P.PPM * s
            ry = rx * rd.uniform(0.5, 0.75)
            x0, x1 = max(0, int(x - rx - 1)), min(W, int(x + rx + 2)); y0, y1 = max(0, int(y - ry - 1)), min(H, int(y + ry + 2))
            yy, xx = np.mgrid[y0:y1, x0:x1]
            d = np.hypot((xx - x) / rx, (yy - y) / ry)
            m = (d < 1.0) & shade[y0:y1, x0:x1] & ((d < 0.75) | ((xx + yy) % 2 == 0))
            sub = idx[y0:y1, x0:x1]
            sub[m] = lut[sub[m]]

    # --- tufts in clusters along the edges (gaps between), pebbles near them
    edge = np.zeros_like(grassm)
    edge[1:-1, 1:-1] = grassm[1:-1, 1:-1] & (dm[:-2, 1:-1] | dm[2:, 1:-1] | dm[1:-1, :-2] | dm[1:-1, 2:])
    rimh = np.zeros_like(grassm)
    rimh[1:-1, 1:-1] = grassm[1:-1, 1:-1] & (fl[:-2, 1:-1] | fl[2:, 1:-1])
    cand = [(int(y), int(x)) for y, x in zip(*np.nonzero(edge | rimh))]
    rng.shuffle(cand)
    taken = set()
    cellpx = max(8, int(round(40 * ps)))
    nt = 0
    for (y, x) in cand:
        key = (y // cellpx, x // cellpx)
        if key in taken or rng.random() > 0.6:
            continue
        taken.add(key)
        for _ in range(rng.randint(3, 5)):                      # a cluster of tufts
            ty, tx = y + rng.randint(-2, 2), x + rng.randint(-int(7 * ps), int(7 * ps))
            if not (0 <= ty < H and 0 <= tx < W) or not (grassm[ty, tx] or dm[ty, tx]):
                continue
            nt += 1
            sunny = bool(sun[ty, tx])
            hi, lo = (K["gr_hi"], K["gr_sh"]) if sunny else (K["gr_sh"], K["gr_teal"])
            px = []
            nb = rng.randint(3, 5)
            for b in range(nb):
                bx = (b - nb // 2) * max(1, int(round(1.4 * ps))) + rng.randint(-1, 1)
                ln = int(round(rng.uniform(3, 8) * ps * (1.0 - 0.4 * abs(b - nb // 2) / nb)))
                lean = rng.choice((-1, 0, 0, 1))
                for kk in range(ln):
                    px.append((bx + (lean if kk > ln // 2 else 0), -kk, hi if kk > 0 else lo))
            _stamp(idx, tx, ty, px)

    # --- the campfires' warm light on the ground round them (one step up, a checkered rim)
    nk = max(K.values()) + 1
    lut2 = np.arange(nk)
    for a_, b_ in (("gr_sh", "gr"), ("gr_teal", "gr_sh"), ("gr", "gr_lit"), ("gr_lit", "gr_hi"), ("ff", "ff_lit"),
                   ("ff_dk", "ff"), ("ff_lit", "gr_teal"), ("dt_sh", "dt"), ("dt", "dt_lit")):
        lut2[K[a_]] = K[b_]
    for t in lay["things"]:
        if t["kind"] != "fire":
            continue
        x, y = _proj_s(t["u"], t["v"], s)
        rx = 1.5 * P.PPM * s; ry = rx * P.SE
        x0, x1 = max(0, int(x - rx)), min(W, int(x + rx + 1)); y0, y1 = max(0, int(y - ry)), min(H, int(y + ry + 1))
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.hypot((xx - x) / rx, (yy - y) / ry)
        m = (grassm | dm | fl | (mid == MAT["floor_lt"]))[y0:y1, x0:x1] & ((d < 0.7) | ((d < 1.0) & ((xx + yy) % 2 == 0)))
        sub = idx[y0:y1, x0:x1]
        sub[m] = lut2[sub[m]]
        m2 = m & ((d < 0.4) | ((d < 0.55) & ((xx + yy) % 2 == 1)))     # brighter close to the flames
        sub[m2] = lut2[sub[m2]]

    # --- the grass overhangs the dirt's far edges: soft scallops hanging onto the dirt, their shadow under them; small
    # pebbles along the edges
    top_e = np.zeros_like(grassm)
    top_e[:-1, :] = grassm[:-1, :] & dm[1:, :]
    ro_ = random.Random(71)
    ys, xs = np.nonzero(top_e)
    for i_ in range(len(ys)):
        if ro_.random() > 0.5 / max(1.0, 3.0 * ps):
            continue
        y, x = int(ys[i_]), int(xs[i_])
        r = max(2, int(round(ro_.uniform(1.6, 3.2) * ps)))
        col = int(idx[y, x])
        for dy in range(1, r + 2):
            w_ = int(round(math.sqrt(max(0.0, 1 - (dy / (r + 0.5)) ** 2)) * r))
            for dx in range(-w_, w_ + 1):
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and dm[yy, xx]:
                    idx[yy, xx] = col
        for dx in range(-r + 1, r):                                 # the shadow it casts on the dirt
            yy, xx = y + r + 2, x + dx + 1
            if 0 <= yy < H and 0 <= xx < W and dm[yy, xx] and sun[yy, xx]:
                idx[yy, xx] = K["dt_sh"]

    idx = granular(c, idx, dm, grassm, fl, sdg, sun, ps, lay)

    # --- flowers in drifts where nobody fights: along the dirt's edges and round the props, never in a lane's middle
    edge_d = np.full(gu.shape, 9.0)
    edge_d[grassm] = np.abs(sdg[grassm])
    props = [(t["u"], t["v"]) for t in lay["things"] if t["kind"] in ("boulder", "stump", "ruinwall", "fern", "lantern")
             and float(P.sd_play(np.array(t["u"]), np.array(t["v"]))) < 0.5]
    rf = random.Random(23)
    cols = [K["fl_pink"], K["fl_white"], K["fl_orange"], K["fl_lilac"]]
    for (y, x) in rf.sample(cand, min(len(cand), 900)):
        if rf.random() > 0.3:
            continue
        col = cols[rf.randrange(4)]
        for _ in range(rf.randint(5, 12)):                        # a drift
            ty, tx = y + rf.randint(-int(8 * ps), int(8 * ps)), x + rf.randint(-int(18 * ps), int(18 * ps))
            if not (0 <= ty < H and 0 <= tx < W) or not grassm[ty, tx] or edge_d[ty, tx] > 1.2:
                continue
            _bloom(idx, tx, ty, col, K, rf)
    for (pu, pv) in props:
        x, y = _proj_s(pu, pv, s)
        col = cols[rf.randrange(4)]
        for _ in range(rf.randint(3, 7)):
            a_ = rf.uniform(0, math.tau); rr = rf.uniform(0.8, 1.7) * P.PPM * s
            tx, ty = int(x + math.cos(a_) * rr), int(y + math.sin(a_) * rr * P.SE)
            if 0 <= ty < H and 0 <= tx < W and grassm[ty, tx]:
                _bloom(idx, tx, ty, col, K, rf)
    # the layout's flower clumps (pink, orange, white, lilac): a dense patch of blooms with leaves under them
    fcol = {"pink": K["fl_pink"], "orange": K["fl_orange"], "white": K["fl_white"], "lilac": K["fl_lilac"]}
    for t in lay["things"]:
        if t["kind"] != "flowers":
            continue
        r_ = random.Random(t["seed"])
        x0, y0 = _proj_s(t["u"], t["v"], s)
        col = fcol.get(t.get("cls"), K["fl_pink"])
        R_ = r_.uniform(0.25, 0.45) * P.PPM * s
        for _ in range(r_.randint(10, 18)):
            a_ = r_.uniform(0, math.tau); rr = R_ * math.sqrt(r_.random())
            x, y = int(x0 + math.cos(a_) * rr), int(y0 + math.sin(a_) * rr * 0.7)
            if 0 <= y < H and 0 <= x < W and (grassm[y, x] or fl[y, x]):
                _stamp(idx, x, y + 1, [(0, 0, K["gr_sh"]), (1, 0, K["gr_sh"])])
                _bloom(idx, x, y, col, K, r_)
    # mushrooms from the layout's patches: red caps with pale spots, a pale stem, a shadow; sized in metres
    for t in lay["things"]:
        if t["kind"] != "mushrooms":
            continue
        r_ = random.Random(t["seed"])
        x0, y0 = _proj_s(t["u"], t["v"], s)
        for _ in range(r_.randint(2, 5)):
            x = int(x0 + r_.uniform(-0.45, 0.45) * P.PPM * s); y = int(y0 + r_.uniform(-0.3, 0.3) * P.PPM * s * P.SE)
            if 0 <= y < H and 0 <= x < W and (grassm[y, x] or fl[y, x]):
                _mushroom(idx, x, y, max(2, int(round(r_.uniform(1.6, 2.6) * ps))), K)

    # --- fungi on the stumps and the log, on their sides that face the camera
    rfu = random.Random(83)
    for t in lay["things"]:
        if t["kind"] == "stump":
            g0 = float(P.terrain(np.array(t["u"]), np.array(t["v"])))
            for a_ in (rfu.uniform(-2.2, -1.4), rfu.uniform(-1.0, -0.4)):
                x, y = P.proj(t["u"] + math.cos(a_) * t["r"] * 0.95, t["v"] + math.sin(a_) * t["r"] * 0.95,
                              g0 + rfu.uniform(0.12, 0.3))
                _fungi(idx, int(x * s), int(y * s), rfu.randint(1, 3), ps, K, rfu)
        elif t["kind"] == "log":
            g0 = float(P.terrain(np.array(t["u"]), np.array(t["v"])))
            for k_ in range(3):
                vv = t["v"] - t["len"] * 0.35 + k_ * t["len"] * 0.3 + rfu.uniform(-0.2, 0.2)
                x, y = P.proj(t["u"] + t["r"] * 0.9, vv, g0 + t["r"] * 0.9)
                _fungi(idx, int(x * s), int(y * s), rfu.randint(1, 2), ps, K, rfu)

    # --- fallen red leaves: everywhere at a low density (more under the red crowns), the crowns' colour carried down
    # onto the floor; 2-3 px, two tones
    rl = random.Random(31)
    oaks = [(t["u"], t["v"], t.get("crown", 2.8)) for t in lay["things"] if t["kind"] == "oak"]
    floorish = grassm | dm | fl
    ys, xs = np.nonzero(floorish)
    n_leaf = int(len(ys) / (P.PPM * s) ** 2 / P.SE / 4.0)
    for i in rl.sample(range(len(ys)), min(len(ys), n_leaf)):
        y, x = int(ys[i]), int(xs[i])
        if dm[y, x] and rl.random() < 0.5:
            continue
        _leaf(idx, x, y, K, rl)
    for (ou, ov, R) in oaks:
        for _ in range(int(R * R * 1.4)):
            a_ = rl.uniform(0, math.tau); rr = rl.uniform(0.6, R + 1.2)
            x, y = _proj_s(ou + math.cos(a_) * rr, ov + math.sin(a_) * rr, s)
            x, y = int(x), int(y)
            if 0 <= y < H and 0 <= x < W and floorish[y, x]:
                _leaf(idx, x, y, K, rl)

    # --- the crowns' lobes: a few big round lobes per crown that overlap like scales (the lower one, nearer the
    # camera, in front); inside each lobe a soft gradient made of the ramp's steps and a 4x4 ordered dither: a glow at
    # the top centre toward the sun (peach in its core), the body, the shadow side down to the plum. Pines and bushes
    # get smaller lobes
    crm = np.isin(mid, CROWN_MATS + (MAT["pine"], MAT["pine_hi"], MAT["bush_green"]))
    if crm.any():
        from ...geo import _hash
        cy_, cx_ = np.nonzero(crm)
        isc = np.isin(mid[cy_, cx_], CROWN_MATS)
        R = np.where(isc, 36.0, 20.0) * ps
        fx = cx_ / R + 0.1 * np.sin(cy_ / R * 2.3 + 1.7 * np.sin(cx_ / R * 0.9))
        fy = cy_ / R + 0.1 * np.sin(cx_ / R * 2.1 + 1.3 * np.sin(cy_ / R * 1.1))
        iu, iv = np.floor(fx).astype(np.int64), np.floor(fy).astype(np.int64)
        best = np.full(fx.shape, -9.0); ox = np.zeros(fx.shape); oy = np.zeros(fx.shape)
        for du in (-1, 0, 1):
            for dv in (-1, 0, 1):
                a_, b_ = iu + du, iv + dv
                sx = a_ + 0.15 + 0.7 * _hash(a_, b_, 171); sy = b_ + 0.15 + 0.7 * _hash(a_, b_, 172)
                rad = 0.66 + 0.22 * _hash(a_, b_, 174)
                dd = np.hypot(fx - sx, fy - sy)
                front = (dd < rad) & (sy > best)                  # the lowest covering lobe is in front
                best = np.where(front, sy, best)
                ox = np.where(front, (fx - sx) / rad, ox); oy = np.where(front, (fy - sy) / rad, oy)
        has = best > -9.0
        L_ = (ox * 0.7 + oy * 0.7)                              # > 0: away from the sun (lower right)
        r_ = np.hypot(ox, oy)
        glow_ = np.clip(1.0 - np.hypot(ox + 0.25, oy + 0.32) / 0.7, 0, 1)
        shad_ = np.clip((L_ - 0.15) * 1.6, 0, 1) * np.clip(r_ * 1.4, 0, 1)
        f = np.where(has, 1.35 * glow_ - 1.25 * shad_, 0.0)
        B4 = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16.0 - 0.5
        sh = np.floor(f + B4[cy_ % 4, cx_ % 4] * 0.9 + 0.5).astype(np.int64)
        sh = np.clip(sh, -1, 2)
        cur = idx[cy_, cx_]
        nk = max(K.values()) + 1
        seq_i = np.full(nk, -1); seq_p = np.zeros(nk, np.int64)
        SEQS = [["cr_under", "cr_mag", "cr", "cr_lit", "cr_hi"], ["ce_under", "ce_mag", "ce", "ce_lit", "ce_hi"],
                ["pn_deep", "pn_sh", "pn", "pn_lit", "pn_hi"], ["ff_dk", "bu_sh", "bu", "bu_lit"]]
        for si, seq in enumerate(SEQS):
            for pi, k_ in enumerate(seq):
                if seq_i[K[k_]] < 0:
                    seq_i[K[k_]] = si; seq_p[K[k_]] = pi
        ok = seq_i[cur] >= 0
        si = seq_i[cur]; pi = seq_p[cur]
        top_ = np.array([len(q) - 1 for q in SEQS])[np.maximum(si, 0)]
        # the peach top step only in a lobe's glowing core; the plum floor stays (undersides keep their weight)
        np_ = np.clip(pi + sh, np.where(pi == 0, 0, 1), np.where(f > 0.75, top_, top_ - 1))
        np_ = np.where(pi >= top_, pi, np_)                     # rims and peach already painted stay
        seqk = [np.array([K[k_] for k_ in q]) for q in SEQS]
        new = cur.copy()
        for q_, arr in enumerate(seqk):
            m_ = ok & (si == q_)
            new[m_] = arr[np.minimum(np_[m_], len(arr) - 1)]
        idx[cy_, cx_] = new

    # --- the front row of crowns (in front of the pond) one step down: the frame stays quieter than the field
    crowns_all = np.isin(mid, CROWN_MATS) & (zone == Z.CODE["frame"]) & (gv < -10.6)
    for a_, b_ in (("cr_mag", "cr_under"), ("cr", "cr_mag"), ("cr_lit", "cr"), ("ce_mag", "ce_under"), ("ce", "ce_mag"),
                   ("ce_lit", "ce")):
        idx[crowns_all & (idx == K[a_])] = K[b_]

    # the sun's peach rim on the crowns' upper-left silhouettes where they stand against something far behind
    idx = rims(idx, mid, c["dep"], a, zone, ps)
    c["tufts"] = nt
    return idx


# pebble shapes (ground_research.md): body pixels; the lit pixel(s) on the upper left are derived, the shadow is the body
# shifted one pixel down-right, drawn on the ground only
PEBBLES = {
    1: [[(0, 0)], [(0, 0), (1, 0)], [(0, 0), (0, 1)]],
    2: [[(0, 0), (1, 0), (0, 1), (1, 1)], [(0, 0), (1, 0), (2, 0), (1, 1)], [(0, 0), (1, 0), (1, 1), (2, 1)]],
    3: [[(1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, 2)], [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (3, 1)],
        [(1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (3, 1), (1, 2), (2, 2)]],
    4: [[(1, 0), (2, 0), (3, 0), (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (1, 2), (2, 2), (3, 2)],
        [(1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (3, 1), (0, 2), (1, 2), (2, 2), (3, 2), (1, 3), (2, 3)]],
}


def granular(c, idx, dm, grassm, fl, sdg, sun, ps, lay):
    """granular soil on the dirt (ground_research.md): dusty lighter patches away from the wear, fine grain in clusters
    (darker and lighter by one step, no orphan pixels, denser in the loose soil at the edges and round objects, almost
    none on the packed wear lines) and pebbles (2-12 cm: 1-6 px bodies lit on the upper left, a 1-px shadow
    down-right) placed by blue-noise rejection with a density mask x clumping noise; a few along the pond's banks"""
    K = _k()
    s = c["s"]
    gu, gv, mid = c["gu"], c["gv"], c["mid"]
    H, W = idx.shape
    nk = max(K.values()) + 1
    up = np.arange(nk); dn = np.arange(nk)
    for a_, b_ in (("dt_sh", "dt_pk"), ("dt_pk", "dt"), ("dt", "dt_lit"), ("dt_lit", "dt_du")):
        up[K[a_]] = K[b_]; dn[K[b_]] = K[a_]
    ys, xs = np.nonzero(dm)
    if not len(ys):
        return idx
    u, v = gu[ys, xs], gv[ys, xs]
    wd = wear_dist(u, v)
    edge = P.smooth(-0.15, -1.1, sdg[ys, xs])                 # 0 at the grass's edge -> 1 a metre in
    objs = np.array([(t["u"], t["v"], (t.get("r") or 0.3)) for t in lay["things"]
                     if t["kind"] in ("log", "stump", "crates", "fire", "waystone", "lantern", "bush", "oak")
                     and float(P.sd_dirt(np.array(t["u"]), np.array(t["v"]))) < 2.0])
    cav = np.zeros(u.shape)
    for (ou, ov, orr) in objs:                                 # loose soil collects round things
        cav = np.maximum(cav, np.exp(-((np.hypot(u - ou, v - ov) - orr) / 0.7) ** 2))
    packed = np.exp(-(wd / 0.6) ** 2)                          # 1 on a wear line
    clump = 0.5 + 0.5 * P.fbm(u, v, 0.9, 191, 2)               # clumping noise
    loose = np.clip((1 - edge) * 0.9 + 0.8 * cav + 0.25, 0, 1.6) * (1 - 0.85 * packed)

    # dusty lighter patches: big and soft, away from the wear, checkered rims
    # (their rims dissolve grain by grain, a random threshold over a soft ramp: no checker, no contour)
    fd = P.fbm(u, v, 3.0, 193) + 0.25 * P.fbm(u, v, 0.9, 194)
    rgd = np.random.default_rng(95)
    dmask = (fd > 0.34 + 0.14 * rgd.random(len(ys))) & (packed < 0.3) & sun[ys, xs] & (mid[ys, xs] == MAT["dirt_lt"])
    idx[ys[dmask], xs[dmask]] = up[idx[ys[dmask], xs[dmask]]]

    rg = np.random.default_rng(97)
    # grain: clusters of 2-4 px (1x2, 2x1, 2x2, an L), darker twice as dense as lighter
    shapes = [((0, 0), (1, 0)), ((0, 0), (0, 1)), ((0, 0), (1, 0), (0, 1), (1, 1)), ((0, 0), (1, 0), (1, 1))]
    area = (P.PPM * s) ** 2
    for lut_, dens in ((dn, 120.0), (up, 50.0)):               # grain clusters per square metre at full looseness
        p = dens * (loose * (0.55 + 0.45 * clump)) / area
        pick = rg.random(len(ys)) < p
        py, px = ys[pick], xs[pick]
        sh = rg.integers(0, len(shapes), len(py))
        for si, shp in enumerate(shapes):
            m = sh == si
            for (dx, dy) in shp:
                yy, xx = py[m] + dy, px[m] + dx
                ok = (yy < H) & (xx < W)
                yy, xx = yy[ok], xx[ok]
                ok2 = dm[yy, xx]
                idx[yy[ok2], xx[ok2]] = lut_[idx[yy[ok2], xx[ok2]]]

    # pebbles: candidates by the density mask, accepted on a blue-noise occupancy grid (no two closer than their
    # sizes), size biased up at the edges and round objects
    pdens = 22.0 * loose * clump ** 1.2                         # pebbles per square metre
    cand = np.nonzero(rg.random(len(ys)) < pdens / area * 3.0)[0]
    rg.shuffle(cand)
    occ = {}
    cellpx = 3
    rp = random.Random(101)
    variants = [("cb_top", "cl_lit", 0.4), ("rk_hi", "cb_top", 0.4), ("dt_pk", "dt", 0.2)]
    for i_ in cand:
        y, x = int(ys[i_]), int(xs[i_])
        big = (1 - edge[i_]) * 0.6 + cav[i_] * 0.7
        rr = rp.random()
        size = 1 if rr > 0.6 + 0.2 * big else (2 if rr > 0.25 + 0.2 * big else (3 if rr > 0.07 + 0.12 * big else 4))
        size = max(1, min(4, int(round(size * min(1.0, ps / 1.6)))))
        key = (y // cellpx, x // cellpx)
        span = size // 2 + 1
        if any(occ.get((key[0] + a, key[1] + b)) for a in range(-span, span + 1) for b in range(-span, span + 1)):
            continue
        occ[key] = True
        body = rp.choice(PEBBLES[size])
        q = rp.random()
        vb, vh = variants[0][:2]
        acc = 0.0
        for b_, h_, w_ in variants:
            acc += w_
            if q < acc:
                vb, vh = b_, h_
                break
        lit_ = bool(sun[y, x])
        cb_, ch_ = (K[vb], K[vh]) if lit_ else ((dn[K[vb]], K[vb]) if vb.startswith("dt") else (K["rk_lit"], K["rk_hi"]))
        bset = set(body)
        for (dx, dy) in body:                                   # the shadow first, on the dirt only
            sx_, sy_ = x + dx + 1, y + dy + 1
            if (dx + 1, dy + 1) not in bset and 0 <= sy_ < H and 0 <= sx_ < W and dm[sy_, sx_]:
                idx[sy_, sx_] = dn[idx[sy_, sx_]]
        top_l = min(body, key=lambda p_: p_[0] + p_[1])
        for (dx, dy) in body:
            yy, xx = y + dy, x + dx
            if 0 <= yy < H and 0 <= xx < W:
                hl = (dx, dy) == top_l or (size >= 3 and (dx - 1, dy) not in bset and (dx, dy - 1) not in bset)
                idx[yy, xx] = ch_ if hl and size > 1 else cb_

    # a few pebbles where the grass meets the pond's banks
    bank = np.isin(mid, [MAT["bank"]]) | (grassm & (P.sd_pond(gu, gv) < 0.6))
    by, bx = np.nonzero(bank)
    for i_ in rp.sample(range(len(by)), min(len(by), int(len(by) / (900 * ps * ps)))):
        y, x = int(by[i_]), int(bx[i_])
        body = rp.choice(PEBBLES[rp.choice((1, 2, 2, 3))])
        for (dx, dy) in body:
            if 0 <= y + dy + 1 < H and 0 <= x + dx + 1 < W:
                idx[y + dy + 1, x + dx + 1] = K["gr_deep"]
        for (dx, dy) in body:
            if 0 <= y + dy < H and 0 <= x + dx < W:
                idx[y + dy, x + dx] = K["rk_lit"] if (dx + dy) else K["rk_hi"]
    return idx


def _mushroom(idx, x, y, r, K):
    """a red cap (r px half-width) on a pale stem, lit on its upper left, two pale spots, a shadow at its foot"""
    px = [(dx, 1, K["gr_deep"]) for dx in range(-r + 1, r + 1)]
    for k in range(r):
        px.append((0, -k, K["mu_dot"])); px.append((1, -k, K["mu_dot"]))
    for dy in range(0, r + 1):                                  # rows of the dome, from its rim up
        w_ = int(round(r * math.sqrt(max(0.0, 1 - (dy / (r + 0.3)) ** 2))))
        for dx in range(-w_, w_ + 2):
            px.append((dx, -r - dy, K["fl_pink"] if (dx < 0 and dy >= r // 2) else K["mu_cap"]))
    px.append((-(r // 2), -r - r // 2, K["mu_dot"])); px.append((r // 2 + 1, -r - r // 3, K["mu_dot"]))
    _stamp(idx, x, y, px)


def _fungi(idx, x, y, n, ps, K, r_):
    """shelf fungi on a stump's or log's side: n small orange-cream brackets stacked"""
    for j in range(n):
        w_ = max(2, int(round(r_.uniform(2.2, 3.4) * ps)))
        oy = -j * max(2, int(round(1.6 * ps))); ox = r_.randint(-1, 1)
        px = [(dx + ox, oy, K["fl_orange"]) for dx in range(-w_, w_ + 1)]
        px += [(dx + ox, oy + 1, K["mu_dot"]) for dx in range(-w_ + 1, w_)]
        px += [(dx + ox, oy - 1, K["lamp"]) for dx in range(-w_ + 1, 0)]
        _stamp(idx, x, y, px)


def _bloom(idx, x, y, col, K, r_):
    if r_.random() < 0.6:                                        # four petals round a pale eye
        _stamp(idx, x, y, [(0, -1, col), (-1, 0, col), (1, 0, col), (0, 1, col), (0, 0, K["fl_white"] if col != K["fl_white"] else K["lamp"])])
    else:
        _stamp(idx, x, y, [(0, 0, col), (1, 0, col)])


def _leaf(idx, x, y, K, r_):
    a, b = (K["cr_lit"], K["cr_mag"]) if r_.random() < 0.65 else (K["ce_lit"], K["ce_mag"])
    shape = r_.choice(([(0, 0, a), (1, 0, a), (1, 1, b)], [(0, 0, a), (0, 1, b)], [(0, 0, a), (1, 0, b), (2, 0, b)]))
    _stamp(idx, x, y, shape)


def rims(idx, mid, dep, a, zone, s=1.0):
    K = _k()
    H, W = idx.shape
    crown = np.isin(mid, CROWN_MATS) & np.isin(zone, [Z.CODE["frame"], Z.CODE["backdrop"]])
    rim = np.zeros_like(crown)
    k = max(1, int(round(2 * s)))
    for (dy, dx) in ((-k, -k), (-1, -k), (-k, -1)):
        nb_a = np.zeros_like(a); nb_d = np.full(dep.shape, 1e9, np.float32)
        sy0, sy1 = max(0, -dy), H - max(0, dy)
        sx0, sx1 = max(0, -dx), W - max(0, dx)
        nb_a[sy0:sy1, sx0:sx1] = a[sy0 + dy:sy1 + dy, sx0 + dx:sx1 + dx]
        nb_d[sy0:sy1, sx0:sx1] = dep[sy0 + dy:sy1 + dy, sx0 + dx:sx1 + dx]
        rim |= crown & (~nb_a | (nb_d > dep + 4.0))
    ember = mid == MAT["crown_ember"]
    idx[rim & ember] = K["ce_hi"]
    idx[rim & ~ember] = K["cr_hi"]
    return idx


def after_sky(c, idx):
    return idx


# ---------------------------------------------------------------- the moving layers (arena/layers.py)
def sway_amp(t, u, v):
    """the frame's trees sway (the oaks' crowns breathe as clumps, about 1.5 px); the screen trees by the spawns and
    anything inside the hollow stand still (units read under them)"""
    if float(P.sd_play(np.array(u), np.array(v))) < 1.0:
        return 0.0
    return 1.5 if t["kind"] == "oak" else 0.8 + 0.6 * float(P.smooth(-6.0, 14.0, v))


_KIND_AT = {}


def sway_exp(k, u, v):
    """how the sway grows up a tree: a crown moves as one clump (a low exponent), a pine bends from its foot"""
    if not _KIND_AT:
        _KIND_AT.update({(round(t["u"], 4), round(t["v"], 4)): t["kind"] for t in P.layout()["things"]})
    return 0.3 if _KIND_AT.get((round(u, 4), round(v, 4))) == "oak" else 1.5


def back_sway_amp(t):
    return (0.3, 0.0, 0.0)[t["band"]]              # the vista stays quiet


def layer_meta(W, sw, at, cy):
    return dict(
        about="draw order sky < far (the cumulus strip over the hills) < main; x, y = where the layer's top-left sits "
              "on the map at offset 0; strips wrap every `wrap` px; drift in px/s; parallax: the share of the camera's "
              "pan a layer follows (1 = the map)",
        sky_parallax=[0.15, 0.5],
        far=dict(x=-(sw - W) // 2, y=at["far"], wrap=sw, drift=2.0, parallax=[0.3, 0.6]),
        ambience=ambience(),
    )


def ambience():
    """what the viewer animates over the map: the pond's shimmer (its water pixels' box and the surface's screen
    rows), leaves falling from the red crowns, light motes over the grass"""
    cu, cv, hu, hv = P.POND
    x0, y0 = P.proj(cu - hu, cv + hv, P.WATER_Z)
    x1, y1 = P.proj(cu + hu, cv - hv, P.WATER_Z)
    crowns = [[round(P.proj(t["u"], t["v"], float(P.terrain(np.array(t["u"]), np.array(t["v"]))) + t["h"] * 0.8)[0], 1),
               round(P.proj(t["u"], t["v"], float(P.terrain(np.array(t["u"]), np.array(t["v"]))) + t["h"] * 0.8)[1], 1)]
              for t in P.layout()["things"] if t["kind"] == "oak"]
    cols = [list(Z.zone_rgb(k, "frame", 0)) for k in ("wa_deep", "wa_mid", "wa", "wa_lit", "wa_hi")]
    # soft light the viewer lays over the picture (added at a low alpha, breathing slowly): a warm glow on the fighting
    # ground, a peach bloom on the sunlit tops of the big red crowns
    glows = []
    gcu, gcv, gru, grv, _ = P.GROUND
    gx, gy = P.proj(gcu, gcv, 0.0)
    glows.append([round(gx), round(gy), round(gru * 1.25 * P.PPM), round(grv * 1.5 * P.PPM * P.SE), "lamp", 0.09])
    for t in P.layout()["things"]:
        if t["kind"] != "oak" or t.get("crown", 0) < 2.0:
            continue
        g0 = float(P.terrain(np.array(t["u"]), np.array(t["v"])))
        x, y = P.proj(t["u"] - 0.35 * t["crown"], t["v"], g0 + t["h"] * 0.92)
        r = t["crown"] * P.PPM * 0.75
        glows.append([round(x), round(y), round(r), round(r * 0.8), "cr_hi", 0.13])
    return dict(pond=dict(x0=round(x0), y0=round(y0), x1=round(x1), y1=round(y1), u=cu, v=cv, hu=hu, hv=hv,
                          z=P.WATER_Z, colours=cols), crowns=crowns, glows=glows)


# ---------------------------------------------------------------- looking aids (arena/sheets.py)
GROUPS = [
    ("sky (midday)", ["sk_top", "sk_hi", "sk_mid", "sk_lo", "glow"]),
    ("cumulus, far hills, haze", ["cl_base", "cl_shade", "cl_mid", "cl_lit", "cl_hi", "hl_sh", "hl", "hl_lit", "fog"]),
    ("playfield: dirt and pebbles", ["dt_sh", "dt_pk", "dt", "dt_lit", "dt_du", "cb", "cb_top"]),
    ("playfield: grass", ["gr_deep", "gr_teal", "gr_sh", "gr", "gr_lit", "gr_hi"]),
    ("coral crowns (frame)", ["cr_deep", "cr_under", "cr_sh", "cr", "cr_lit", "cr_hi", "ce_under", "ce_sh", "ce",
                              "ce_lit", "ce_hi"]),
    ("pines, bushes, forest floor", ["pn_deep", "pn_sh", "pn", "pn_lit", "pn_hi", "bu_sh", "bu", "bu_lit", "ff_dk",
                                      "ff", "ff_lit"]),
    ("boulders, ruin, cliffs", ["rk_deep", "rk_sh", "rk", "rk_lit", "rk_hi", "rs_sh", "rs", "rs_lit", "moss", "cf_dk",
                                "cf", "cf_lit"]),
    ("wood", ["wd_dk", "wd", "wd_lit", "wd_ring", "wd_end"]),
    ("water, river", ["wa_deep", "wa_mid", "wa", "wa_lit", "wa_hi", "shore", "rv", "rv_hi"]),
    ("accents (flowers, mushrooms, reeds, lights)", ["fl_pink", "fl_orange", "fl_white", "fl_lilac", "mu_cap", "mu_dot", "reed",
                                                     "reed_lit", "lamp", "lamp_core", "rune"]),
]


def scale_marks(d, person, dim_line, hp, zof):
    spots = [(-21.4, 0.5), (-12.0, -1.0), (-5.0, 1.0), (0.0, 7.4), (6.0, -4.6), (9.0, 6.6), (16.0, -5.2), (21.4, 0.5)]
    for (u, v) in spots:
        x, y = P.proj(u, v, zof(u, v))
        person(d, x, y, hp)
    W_, E_ = P.SPAWNS["west"], P.SPAWNS["east"]
    dim_line(P.proj(W_[0], W_[1] - 6.0, 0), P.proj(E_[0], E_[1] - 6.0, 0), f"spawn to spawn {E_[0] - W_[0]:.0f} m")
    cu, cv, ru, rv, _ = P.GROUND
    dim_line(P.proj(cu - ru, cv + rv + 0.4, 0.1), P.proj(cu + ru, cv + rv + 0.4, 0.1),
             f"fighting ground {2 * ru:.0f} m", (0, -12))
    dim_line(P.proj(0.6, -0.8, 0.1), P.proj(0.6, 2.8, 0.1), "log 3.6 m", (46, 0))
    ku, kv, kr, kh = P.KNOLL
    x, y = P.proj(ku + kr * 0.2, kv, zof(ku, kv))
    dim_line((x + 40, y + kh * P.CE * P.PPM), (x + 40, y), f"knoll {kh:.1f} m", (44, 0))
    return ""


# ---------------------------------------------------------------- the viewer (web/arena.js, built by build.py)
VIEWER = dict(
    subtitle="a kill map for your units · 68 degrees · 1 m = 51.2 px · level.json v4",
    particles="leaves", particles_label="Leaves",
    people=[[-12.0, -1.0, 0], [0.0, 7.4, 0], [6.0, -4.6, 0], [-9.0, 6.6, 0]],
    levels=["ground"],
    surfaces=["", "grass", "dirt"],
    smoke=["smoke", "smoke_lo"],
)
SHOTS = [
    # the picture is 3072 x 1728 (51.2 px/m): the overview at 1x is a full-size window; crops at 2x; overlays at 1x
    ("overview", "pause=1&t=6&zoom=1&at=1536,864&hud=0", (3072, 1728)),
    ("overview_ui", "pause=1&t=6&zoom=fit", (1920, 1080)),
    ("overlay_grid", "pause=1&t=6&zoom=fit&overlay=grid&snow=0", (1920, 1080)),
    ("overlay_zones", "pause=1&t=6&zoom=fit&overlay=zones&snow=0", (1920, 1080)),
    ("overlay_scale", "pause=1&t=6&zoom=1&at=1536,980&overlay=scale&snow=0", (1920, 1080)),
    ("crop_fighting_ground", "pause=1&t=6&zoom=2&at=1536,960&hud=0&snow=0", (1200, 760)),
    ("crop_trees", "pause=1&t=6&zoom=2&at=640,420&hud=0&snow=0", (1200, 760)),
    ("crop_grass_edge", "pause=1&t=6&zoom=2&at=1060,1080&hud=0&snow=0", (1200, 760)),
    ("crop_pond", "pause=1&t=6&zoom=2&at=1536,1340&hud=0&snow=0", (1200, 760)),
    ("crop_background", "pause=1&t=6&zoom=2&at=1536,250&hud=0&snow=0", (1600, 600)),
    ("crop_spawn", "pause=1&t=6&zoom=2&at=420,980&hud=0&snow=0", (1200, 760)),
    ("colliders", "pause=1&t=6&zoom=fit&overlay=colliders&snow=0", (1920, 1080)),
    ("nav", "pause=1&t=6&zoom=fit&overlay=nav&snow=0", (1920, 1080)),
    ("los_ground", "pause=1&t=6&zoom=fit&overlay=los&los=-12,-1,0&losstep=1&snow=0", (1920, 1080)),
    ("los_knoll", "pause=1&t=6&zoom=fit&overlay=los&los=0,7.6,0&losstep=1&snow=0", (1920, 1080)),
    ("paths", "pause=1&t=6&zoom=fit&overlay=paths&cursor=0,7.4,0&snow=0", (1920, 1080)),
    ("agent", "pause=1&t=6&zoom=1&at=1536,900&overlay=agent&target=8,6.6,0&walk=150&snow=0", (1200, 760)),
    ("ambience_t0", "pause=1&t=0&zoom=1&at=1536,1100&hud=0", (1920, 1080)),
    ("ambience_t40", "pause=1&t=40&zoom=1&at=1536,1100&hud=0", (1920, 1080)),
    ("toggles", "pause=1&t=6&zoom=fit", (1920, 1080),
     ["#b-grid", "#b-zones", "#b-scale", "#b-zones", "#b-colliders", "#b-nav", "#b-los", "#b-paths", "#b-agent",
      "#b-nav", "#b-r", "#b-lv", "#b-snow"],
     "window.__arena.show.grid && !window.__arena.show.zones && window.__arena.show.scale && "
     "window.__arena.show.colliders && !window.__arena.show.nav && window.__arena.show.los && "
     "window.__arena.show.paths && window.__arena.show.agent && !window.__arena.show.snow"),
]
