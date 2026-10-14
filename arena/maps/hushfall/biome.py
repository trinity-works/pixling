"""Hushfall Crossing's biome: the winter dusk. Its materials and their ramps, the zones' budgets as they are (the
shared table in arena/zones.py was written for this map), the dusk sky, the low sun's rims on the tree line, the
ledge's cliffs sinking into the cloud sea, the moving layers (cumulus strip, cloud sea, corner towers, the ledge's
front) and the viewer's ambience (snowfall, camp fires, lamps, banners).

The painter (arena/paint.py) calls the hooks here in a fixed order: frame_trees -> sky -> ground -> (step, clean) ->
after_clean -> (sky pixels) -> after_sky.
"""
from __future__ import annotations

import numpy as np

from . import place as P
from ... import zones as Z

TITLE = "Hushfall Crossing"
FOG = "fog"
ZONE_OVERRIDES = {}                 # the shared table is Hushfall's own
# the sun's colours, and the neutral each becomes where the zone has no sun (sun = 0)
SUN_KEYS = {"hot": "cl_hi", "hot2": "cl_lit", "hot_deep": "cl_mid", "cl_crown": "cl_hi", "glow": "sky_lo",
            "rim": "tb2", "rim_hot": "tb3", "lamp": "cloth_lit", "lamp_core": "cloth_lit", "fire": "cl_lit"}

MAT = dict(snow_edge=40, snow=1, path=2, ice=3, cliff=4, pillow=5, rock=6, wood=7, wood_dk=8, canvas_west=9,
           canvas_east=10, bark=11, metal=12, lamp=13, rope=14, grass=15, trim=16, plank=17, hearth=18, rock_top=19,
           needle_a=20, needle_b=21, snowc_a=22, snowc_b=23, deck_snow=24, masonry=25, bank=26, shore=27,
           cap=28, cloud=30, pink=31, cloudfloor=32, far_snow=33, far_rock=34, far_floor=35, stone=36, coping=37, fog=41,
           sky=42)

# (lit thresholds, palette keys): lit = the diffuse value (0.28 in full shade, ~0.9 on flat sunlit snow, + the fill).
# Ramps are written full; each zone merges them down to its step budget.
RAMPS = {
    # the field where they fight: lit snow and violet shade, the trodden lanes a step down
    "snow": ([0.7], ["pf_shade", "pf_lit"]),
    "path": ([0.7], ["pf_lane_sh", "pf_lane"]),
    # snow outside the field (drifts at the lip, the frame's ground, the shelf under the forest ring)
    # (the frame darkens them: kept on the violet side, so a clamped one never turns olive)
    "snow_edge": ([0.5, 0.75, 0.95], ["sn_shade", "sn_mid", "sn", "sn_hi"]),
    # the far ridges' snow under their forests
    "far_snow": ([0.8, 1.05], ["sn_shade", "sn_mid", "sn_lit"]),
    "far_rock": ([0.5, 0.8], ["cl_rock", "cl_rock_lit", "st_hi"]),
    "far_floor": ([], ["fog"]),
    "bank": ([0.7], ["sn_mid", "sn"]),
    # snow lying on things (drifts, banks, roofs); cool keys only: darkened in the frame they stay violet-grey
    "pillow": ([0.36, 0.55, 0.84, 1.0], ["sn_shade", "sn_mid", "sn", "sn_hi", "sn_lit"]),
    # the snow on the bridge: the playfield's own two tones, a third for the sunlit drifts
    "deck_snow": ([0.6, 0.95], ["pf_shade", "pf_lane", "pf_lit"]),
    "cliff": ([0.5, 0.8], ["cl_rock_dk", "cl_rock", "cl_rock_lit"]),
    # the ruin's masonry: dressed blocks a step warmer and lighter than the cliff
    "masonry": ([0.42, 0.62, 0.88], ["ms_dk", "ms", "ms_lit", "ms_hi"]),
    "stone": ([0.5, 0.9], ["st", "st_lit", "st_hi"]),
    "coping": ([0.6], ["st_hi", "fl_lo"]),
    "rock": ([0.33, 0.44, 0.8, 1.0], ["st_dk", "st_lo", "st", "st_lit", "st_hi"]),
    "rock_top": ([0.5, 0.95], ["st", "st_lit", "st_hi"]),
    "wood": ([0.34, 0.6], ["wd_dk", "wd", "wd_lit"]),
    "wood_dk": ([0.34, 0.7], ["bark_dk", "wd_dk", "wd"]),
    # the bridge's planks: four steps, the sunlit face warm
    "plank": ([0.4, 0.62, 0.86], ["wd_dk", "wd", "wd_lit", "pl_hi"]),
    "bark": ([0.34, 0.7], ["bark_dk", "bark", "bark_lit"]),
    "metal": ([0.34, 0.7], ["metal_dk", "metal", "metal_lit"]),
    "rope": ([], ["rope"]),
    "trim": ([0.5], ["rope", "cloth_dk"]),
    "grass": ([0.6], ["grass", "st_hi"]),
    "hearth": ([], ["ash"]),
    "canvas_west": ([0.33, 0.45, 0.8], ["cw_lo", "cw", "cw_mid", "cw_lit"]),
    "canvas_east": ([0.33, 0.45, 0.8], ["ce_lo", "ce", "ce_mid", "ce_lit"]),
    "lamp": ([], ["lamp"]),
    "needle_a": ([0.30], ["tau", "ta0"]),
    "needle_b": ([0.30], ["tbu", "tb0"]),
    "snowc_a": ([0.56, 0.8], ["ta1", "ta2", "ta3"]),
    "snowc_b": ([0.56, 0.8], ["tb1", "tb2", "tb3"]),
    "cloud": ([0.32, 0.46, 0.6, 0.72, 0.82], ["cl_base", "cl_shade", "cl_mid", "cl_lit", "cl_hi", "cl_crown"]),
    # the clumps on the crowns that face the sun: peach, then its hot pink only where they catch it full
    "pink": ([0.32, 0.46, 0.6, 0.72, 0.84], ["cl_base", "cl_shade", "cl_mid", "cl_crown", "hot2", "hot"]),
    # the cloud sea under the ledge: in the dusk's shade, the salmon only on its tops
    "cloudfloor": ([0.45, 0.66], ["fl_base", "fl_lo", "fl"]),
    # snow lying on the ruin (built in the playfield's zone): the field's own two tones
    "cap": ([0.62], ["pf_shade", "pf_lit"]),
}
CLOUD_MATS = (MAT["cloud"], MAT["pink"], MAT["cloudfloor"])
TREE_MATS = (MAT["needle_a"], MAT["needle_b"], MAT["snowc_a"], MAT["snowc_b"], MAT["bark"])
GROUND_MATS = (MAT["snow"], MAT["path"])


def _kidx():
    from ... import paint
    return paint.KIDX


# ---------------------------------------------------------------- the painted extras
FOG_Z = -5.5        # the ledge's cliffs sink into the cloud sea below this height (m), on a wavering line


def sky(H, W, s=1.0, x0=0, y0=0):
    """the dusk sky by screen height (First Snow's): the glow on the horizon behind the cumulus, warmest on the sun's
    side (left), rose and then cool grey-teal toward the zenith, long thin stratus in the glow's light. Under the
    ledge (below the horizon) the gaps of the cloud sea. x0, y0: the window's offset on the map (the parallax layer
    is painted wider than the map)"""
    K = _kidx()
    yy, xx = np.mgrid[y0:y0 + H, x0:x0 + W].astype(np.float64)
    p0 = (P.Y0 - yy / s) / P.PPM
    ph = P.P_BACK + 2.5                                   # the horizon, just behind the far forests
    p = p0 - ph + 0.35 * P.fbm(xx / s / 60, yy / s / 25, 2.0, 5) - 1.2 * (1 - xx / (P.W * s))
    idx = np.full((H, W), K["sky_top"], np.int32)
    idx[p < 10.0] = K["sky_hi"]
    idx[p < 7.6] = K["sky_mid"]
    idx[p < 5.4] = K["sky_lo"]
    idx[p < 3.2] = K["glow"]
    st = P.fbm(xx / s / 900, p0 * 1.6, 1.0, 61) + 0.5 * P.fbm(xx / s / 240, p0 * 3.0, 1.0, 62)
    band = (p > 2.0) & (p < 11.0)
    idx[band & (st > 0.42)] = K["sky_lo"]
    idx[band & (st > 0.42) & (p < 5.4)] = K["glow"]
    idx[band & (st < -0.48) & (p > 6.0)] = K["sky_hi"]
    sea = p0 < ph - 3.0
    k = P.fbm(xx / s / 70, yy / s / 30, 1.0, 64)
    idx[sea] = np.where(k[sea] > 0.1, K["fl_lo"], K["fl_base"])
    return idx, sea


def rims(idx, mid, dep, a, zone, s=1.0):
    """the low sun's rim on the up-left silhouette of the tree line where it stands against something far behind
    it (the back, the sky): First Snow's salmon edge on the spruces"""
    K = _kidx()
    H, W = idx.shape
    tree = (mid >= 20) & (mid <= 23) & np.isin(zone, [Z.CODE["frame"], Z.CODE["backdrop"]])
    rim = np.zeros_like(tree)
    k = max(1, int(round(2 * s)))
    for (dy, dx) in ((-k, -k), (-1, -k), (-k, -1)):
        nb_a = np.zeros_like(a); nb_d = np.full(dep.shape, 1e9, np.float32)
        sy0, sy1 = max(0, -dy), H - max(0, dy)
        sx0, sx1 = max(0, -dx), W - max(0, dx)
        nb_a[sy0:sy1, sx0:sx1] = a[sy0 + dy:sy1 + dy, sx0 + dx:sx1 + dx]
        nb_d[sy0:sy1, sx0:sx1] = dep[sy0 + dy:sy1 + dy, sx0 + dx:sx1 + dx]
        rim |= tree & (~nb_a | (nb_d > dep + 12.0))
    snowy = (mid == MAT["snowc_a"]) | (mid == MAT["snowc_b"])
    idx[rim & snowy] = K["rim_hot"]
    idx[rim & ~snowy] = K["rim"]
    return idx




# ---------------------------------------------------------------- the painter's hooks
def frame_trees(lay):
    """the trees whose feet are the frame's ground (zone_at)"""
    return [(t["u"], t["v"]) for t in lay["things"] if t["kind"] == "spruce"]


def ground(c):
    """the ground's parts per pixel from where it is (u, v), not per render face: smooth, a little wobbly edges"""
    aw, useb, mid, z, gu, gv, zone = c["aw"], c["useb"], c["mid"], c["z"], c["gu"], c["gv"], c["zone"]
    ground = aw & ~useb & np.isin(mid, [MAT["snow"], MAT["path"]]) & (z > -1.2)
    lane = P.lane_dist(gu, gv) + 0.35 * P.fbm(gu, gv, 1.1, 42)
    pf = zone == Z.CODE["playfield"]
    cls = np.where(pf, MAT["snow"], MAT["snow_edge"])
    cls[pf & (lane < 1.15)] = MAT["path"]
    mid = np.where(ground, cls, mid)
    mid[(mid == MAT["cliff"]) & (zone == Z.CODE["playfield"])] = MAT["snow"]
    return mid


def after_clean(c, idx):
    return rims(idx, c["mid"], c["dep"], c["a"], c["zone"], c["s"])


def after_sky(c, idx):
    """the ledge sinks into the cloud sea: below FOG_Z (wavering) its cliffs take the sea's shadowed tone"""
    K = _kidx()
    aw, useb, z, gu, zone = c["aw"], c["useb"], c["z"], c["gu"], c["zone"]
    sunk = aw & ~useb & (z < FOG_Z + 1.1 * P.fbm(gu, 0 * gu, 3.5, 63, oct=2))
    idx[sunk] = np.where(z[sunk] < FOG_Z - 3.0, K["fl_lo"], K["fl_base"])
    zone[sunk] = Z.CODE["vista"]
    return idx


# ---------------------------------------------------------------- the moving layers (arena/layers.py)
SWAY_KINDS = ("spruce",)
CLOUD_LAYERS = ("far", "sea", "corner")       # rendered alone as cfar / csea / ccorner
CAP = True                                    # the ledge's front, drawn over the sea
RENDER_PASSES = ("world", "back", "cfar", "csea", "ccorner", "ids")


def sway_amp(t, u, v):
    """the frame's spruces: the ring's back trees most, its sides less; the groves in the field stand still"""
    inside = float(P.sd_play(np.array(u), np.array(v))) < 0
    return 0.0 if inside else (0.9 + 1.1 * float(P.smooth(-4.0, 12.0, v))) * (0.7 if v < -5 else 1.0)


def back_sway_amp(t):
    return (1.2, 1.0, 0.8)[t["band"]]


def layer_meta(W, sw, at, cy):
    return dict(
        about="draw order sky < far < main < corner < sea < cap; x, y = where the layer's top-left sits on the map at "
              "offset 0; strips wrap every `wrap` px; drift in px/s; parallax: the share of the camera's pan a layer "
              "follows (1 = the map)",
        sky_parallax=[0.15, 0.6],
        far=dict(x=-(sw - W) // 2, y=at["far"], wrap=sw, drift=3.0, parallax=[0.35, 0.75]),
        corner=dict(x=0, y=at["corner"], drift_amp=10.0, drift_period=240.0, parallax=[0.8, 1]),
        sea=dict(x=-(sw - W) // 2, y=at["sea"], wrap=sw, drift=6.0, parallax=[0.7, 1]),
        cap=dict(x=0, y=cy, parallax=[1, 1]),
    )


# ---------------------------------------------------------------- looking aids (arena/sheets.py)
GROUPS = [
    ("sky (warm dusk)", ["sky_top", "sky_hi", "sky_mid", "sky_lo", "glow"]),
    ("cumulus + the sun's pinks", ["cl_base", "cl_shade", "cl_mid", "cl_lit", "cl_hi", "cl_crown", "hot_deep", "hot2", "hot"]),
    ("cloud sea", ["fl_base", "fl_lo", "fl", "fl_hi"]),
    ("haze (backdrop pushed toward it)", ["fog"]),
    ("playfield: lit snow, lane, shade", ["pf_lit", "pf_lane", "pf_lane_sh", "pf_shade"]),
    ("snow (drifts, roofs, caps)", ["sn_deep", "sn_shade", "sn_mid", "sn", "sn_hi", "sn_lit", "sn_warm", "sn_glow", "sn_cap"]),
    ("spruce (frame)", ["tau", "ta0", "ta1", "ta2", "ta3", "tbu", "tb0", "tb1", "tb2", "tb3", "rim", "rim_hot"]),
    ("ruin masonry, cliff", ["ms_dk", "ms", "ms_lit", "ms_hi", "cl_rock_dk", "cl_rock", "cl_rock_lit"]),
    ("timber, bridge planks", ["wd_dk", "wd", "wd_lit", "pl_hi", "bark_dk", "bark", "bark_lit"]),
    ("camps: west / east canvas, banner cloth", ["cw_lo", "cw", "cw_mid", "cw_lit", "ce_lo", "ce", "ce_mid", "ce_lit",
                                                "cloth_dk", "cloth", "cloth_lit"]),
    ("lights (lamps, hearts, fire)", ["lamp", "lamp_core", "fire"]),
]




def scale_marks(d, person, dim_line, hp, zof):
    """people on every level and the key dimensions on the scale sheet; returns the legend's note"""
    import math
    spots = [(-21.0, -2.6), (-15.5, -1.0), (-11.5, P.RAMP_V), (-2.2, -0.2), (3.2, 7.8), (0.0, 13.6), (-1.0, -9.8),
             (18.4, 4.0)]
    for (u, v) in spots:
        x, y = P.proj(u, v, zof(u, v))
        person(d, x, y, hp)
    # on the bridge deck (level 1)
    vd = (P.DECK["v0"] + P.DECK["v1"]) / 2
    zd = P.DECK["z0"] + (P.DECK["z1"] - P.DECK["z0"]) * 0.5
    x, y = P.proj(0.4, vd, zd + 0.05)
    person(d, x, y, hp, col=(250, 220, 160))
    W_, E_ = P.CAMPS["west"], P.CAMPS["east"]
    dim_line(P.proj(W_[0], W_[1] - 7.5, 0), P.proj(E_[0], E_[1] - 7.5, 0), f"camp to camp {E_[0] - W_[0]:.0f} m", (0, 0))
    dim_line(P.proj(W_[0], W_[1] + 1.2, 0.3), P.proj(P.STONES[0] - 3.6, P.STONES[1] + 1.2, P.ZD),
             f"heart to the Stones {math.hypot(P.STONES[0] - W_[0], P.STONES[1] - W_[1]):.0f} m", (0, -14))
    ru = P.DAIS[2] + P.RAMP_LEN * 0.55
    dim_line(P.proj(ru, P.RAMP_V - P.RAMP_HW, 1.4), P.proj(ru, P.RAMP_V + P.RAMP_HW, 1.4), f"ramp {2 * P.RAMP_HW:.0f} m", (52, 0))
    dim_line(P.proj(P.DECK["u0"], P.DECK["v0"] + 2.0, P.ZD + 1.5), P.proj(P.DECK["u1"], P.DECK["v0"] + 2.0, P.ZD + 1.5),
             f"bridge {P.DECK['u1'] - P.DECK['u0']:.1f} m", (0, -16))
    xx, yy = P.proj(-P.DAIS[2] + 0.4, P.DAIS[1] - P.DAIS[3], 0.0)
    dim_line((xx - 14, yy), (xx - 14, yy - P.ZD * P.CE * P.PPM), f"terrace {P.ZD:.0f} m", (-52, 0))
    hx, hy = P.proj(3.0, 7.8, zof(3.0, 7.8))
    dim_line((hx, hy), (hx, hy - (P.ZD - 0.5 + P.CORR_DIP) * P.CE * P.PPM), f"headroom {P.ZD - 0.5 + P.CORR_DIP:.1f} m", (64, 10))
    return "; one stands on the bridge deck (level 1)"


# ---------------------------------------------------------------- the viewer (web/arena.js, built by build.py)
VIEWER = dict(
    subtitle="a map for your units \u00b7 1 m = 32 px \u00b7 level.json v4",
    particles="snow", particles_label="Snow",
    # the scale people the viewer stands by default: (u, v, layer); the spawns' first points are added in front
    people=[[-11.5, -1.6, 0], [3.0, 7.8, 0], [0, 13.6, 0], [-1.2, -9.8, 0], [0.3, 6.9, 1]],
    levels=["ground", "terrace", "deck"],
    surfaces=["", "snow", "trodden lane", "drift", "deck"],
)
