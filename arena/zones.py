"""Depth zones and their budgets: the information hierarchy of a battle map, in one table.

Loudest to quietest: the units (added later) and effects > FOCUS (what is fought for: the Stones, hearts, towers,
banners, the bridge) > PLAYFIELD (where units walk: calm, light, two tones) and FRAME (the forest ring, the ruin's
faces, the palisades: "the edge is here") > BACKDROP (the forests past the drop) > VISTA (the cumulus, the cloud sea)
> SKY.

Every pixel of the map has a zone (arena/paint.py writes them to art/zones.png). The painter enforces the zone's
budget when it steps the render's data passes into colours, and Blender builds each zone at its detail level:

    haze      (near, mid, far) mix toward the fog colour; `far` = the depths (metres) where mid and far begin
    steps     the most ramp bands a material may show in this zone (a material's ramp is merged down to it)
    value     (lo, hi) luma clamp of every colour in the zone; `rise` lifts the floor per haze level (far ridges
              step back into the haze instead of sharing one dark floor)
    sat       saturation (chroma) cap; colours above it are pulled toward grey
    sun       the chroma cap of the sun's colours (SUN_KEYS: its pinks on the cloud crowns, the glow, the rims);
              0 = they are swapped for neutrals here
    soft      blur (px) on the lit value inside each material before stepping: stroke size
    clean     (radius px, share): a pixel whose colour holds less than `share` of its (2r+1)^2 neighbourhood takes the
              neighbourhood's commonest colour; the minimum cluster size
    detail    Blender's card density (dabs per spruce, puffs per cloud) and geometry level, 1 = full

The back is quiet by value and haze, not by flattening: the backdrop keeps three steps and a small cleanup, so the
spruces' dabs survive at low contrast; the vista keeps the cumulus's puffs and its pink crowns. So lint asks contrast
and texture energy (contrast x the share of neighbouring pixels that differ) to fall with depth, not detail alone.

The accent rule: the brightest, most saturated colours are the sun's (sky, cloud crowns, rims) and the lights'
(lamps, the camps' hearts, fires) and the objectives'. Each map keeps its own hue bands free for the units the user adds
(its palette.UNIT_HUES; Hushfall: gold, green, azure; Emberleaf: gold, violet): no pixel shows them above chroma 0.2.
The table below is shared by every map (arena/STYLE.md); a biome overrides value windows, caps and haze only.

`python3 -m arena lint` measures the painted map against this table and fails when the hierarchy breaks.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import palette as C
from .palette import rgb

# The shared table (arena/STYLE.md): every map keeps these steps, strokes, cleanups and detail levels and the order of
# the zones. A biome (arena/maps/<name>/biome.py ZONE_OVERRIDES) may move a zone's value window, saturation and sun caps
# and its haze to suit its palette; lint then measures the hierarchy (contrast and texture energy falling with depth,
# the playfield calmer and lighter than the frame) the same way on every map.
BASE = {
    "playfield": dict(code=1, haze=(0.0, 0.0, 0.0), far=(1e9, 1e9), steps=2, value=(0.44, 0.66), sat=0.12, sun=0.0,
                      soft=3.0, clean=(3, 0.30), detail=1.0),
    "focus":     dict(code=2, haze=(0.0, 0.0, 0.0), far=(1e9, 1e9), steps=9, value=(0.0, 1.0), sat=1.0, sun=1.0,
                      soft=0.0, clean=(0, 0.0), detail=1.0),
    "frame":     dict(code=3, haze=(0.0, 0.0, 0.0), far=(14.0, 1e9), steps=3, value=(0.16, 0.44), sat=0.17, sun=0.2,
                      soft=0.6, clean=(1, 0.2), detail=0.9),
    "backdrop":  dict(code=4, haze=(0.24, 0.38, 0.50), far=(50.0, 75.0), steps=3, value=(0.36, 0.52), sat=0.12,
                      sun=0.16, soft=0.8, clean=(2, 0.3), detail=0.55, rise=(0.0, 0.03, 0.07)),
    "vista":     dict(code=5, haze=(0.10, 0.20, 0.30), far=(40.0, 120.0), steps=5, value=(0.51, 0.66), sat=0.13,
                      sun=0.7, soft=0.5, clean=(1, 0.2), detail=0.55),
    "sky":       dict(code=6, haze=(0.0, 0.0, 0.0), far=(1e9, 1e9), steps=5, value=(0.50, 0.68), sat=0.2, sun=0.22,
                      soft=0.0, clean=(0, 0.0), detail=0.0),
}
NL = 3                                  # haze levels
SUN_SHARE = {"focus": 1.0, "vista": 0.05, "sky": 0.02}
OUTLINE = 0.10            # the luma of a unit's dark outline (ink): it must stand >= 0.3 off the playfield


def _bind():
    """read the active map's biome: its zone overrides, fog key, the sun's keys and the shares the lint allows"""
    global ZONES, FOG, CODE, BY_CODE, NZ, SUN_KEYS, SUN_SHARE_B, UNIT_ZONES, PF_LO_GAP
    from .maps import active
    B = active().biome
    ovr = getattr(B, "ZONE_OVERRIDES", {})
    ZONES = {k: dict(v, **ovr.get(k, {})) for k, v in BASE.items()}
    FOG = getattr(B, "FOG", "fog")
    CODE = {k: v["code"] for k, v in ZONES.items()}
    BY_CODE = {v["code"]: k for k, v in ZONES.items()}
    NZ = max(CODE.values()) + 1
    # the sun's colours, and the neutral each becomes where the zone has no sun (sun = 0)
    SUN_KEYS = dict(B.SUN_KEYS)
    SUN_SHARE_B = dict(SUN_SHARE, **getattr(B, "SUN_SHARE", {}))
    # where the units' reserved hues must stay free (every zone unless the biome narrows it, e.g. to keep a flower
    # accent in the frame's hue band), and how far the playfield's darks must stand off a unit's outline
    UNIT_ZONES = getattr(B, "UNIT_ZONES", None)
    PF_LO_GAP = getattr(B, "PF_LO_GAP", 0.3)


_bind()


def luma(c):
    c = np.asarray(c, np.float64)
    return (c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114) / 255.0


def chroma(c):
    c = np.asarray(c, np.float64)
    return (c.max(-1) - c.min(-1)) / 255.0


def zone_rgb(key: str, zone: str, level: int = 0):
    """the colour a palette key takes in a zone: the sun's colours swapped where the zone has no sun, hazed toward
    the fog, saturation capped (the sun's colours by their own cap), value clamped"""
    z = ZONES[zone]
    cap = z["sat"]
    if key in SUN_KEYS:
        if z["sun"] <= 0:
            key = SUN_KEYS[key]
        else:
            cap = z["sun"]
    c = np.array(rgb(C.PAL[key]), np.float64)
    h = z["haze"][level]
    c = c * (1 - h) + np.array(rgb(C.PAL[FOG]), np.float64) * h
    y = luma(c) * 255
    ch = chroma(c)
    if ch > cap:
        c = y + (c - y) * (cap / ch)
    lo, hi = z["value"]
    lo = min(hi - 0.06, lo + z.get("rise", (0.0, 0.0, 0.0))[level])
    yy = luma(c)
    if yy < lo:
        c = c + (lo - yy) * 255
    elif yy > hi:
        c = c - (yy - hi) * 255
    return tuple(int(x) for x in np.clip(np.round(c), 0, 255))


def zone_palette(keys) -> np.ndarray:
    """(NZ, NL, len(keys), 3) uint8: every key as every zone renders it at every haze level (code 0 = raw palette)"""
    out = np.zeros((NZ, NL, len(keys), 3), np.uint8)
    for i, k in enumerate(keys):
        out[0, :, i] = rgb(C.PAL[k])
    for name, z in ZONES.items():
        for lv in range(NL):
            for i, k in enumerate(keys):
                out[z["code"], lv, i] = zone_rgb(k, name, lv)
    return out


def haze_level(zone_code: np.ndarray, dep: np.ndarray) -> np.ndarray:
    """the haze level (0 near .. NL-1 far) of every pixel from its zone and depth"""
    lv = np.zeros(zone_code.shape, np.int32)
    for name, z in ZONES.items():
        m = zone_code == z["code"]
        for far in z["far"]:
            lv[m & (dep > far)] += 1
    return lv


def reduce_ramp(th, keys, steps):
    """merge a ramp down to `steps` bands: keep evenly spread keys (both ends), each boundary at the original one
    halfway between them"""
    n = len(keys)
    if n <= steps:
        return list(th), list(keys)
    sel = [int(round(x)) for x in np.linspace(0, n - 1, steps)]
    return [th[(a + b) // 2] for a, b in zip(sel, sel[1:])], [keys[i] for i in sel]


def _boxsum(m, r):
    c = np.pad(m, ((r + 1, r), (r + 1, r))).cumsum(0).cumsum(1)
    return c[2 * r + 1:, 2 * r + 1:] - c[:-2 * r - 1, 2 * r + 1:] - c[2 * r + 1:, :-2 * r - 1] + c[:-2 * r - 1, :-2 * r - 1]


def clean(idx, sel, radius, share, rounds=2):
    """the zone's minimum cluster: a pixel of sel whose colour holds < share of its window takes the window's mode"""
    if radius <= 0 or not sel.any():
        return idx
    ys, xs = np.nonzero(sel)
    y0, y1, x0, x1 = max(0, ys.min() - radius), ys.max() + radius + 1, max(0, xs.min() - radius), xs.max() + radius + 1
    sub, ssel = idx[y0:y1, x0:x1].copy(), sel[y0:y1, x0:x1]
    area = (2 * radius + 1) ** 2
    for _ in range(rounds):
        labs = np.unique(sub[ssel])
        best = np.zeros(sub.shape, np.float32); arg = sub.copy(); own = np.zeros(sub.shape, np.float32)
        for lb in labs:
            cnt = _boxsum(((sub == lb) & ssel).astype(np.float32), radius)
            better = cnt > best
            best[better] = cnt[better]; arg[better] = lb
            own[sub == lb] = cnt[sub == lb]
        bad = ssel & (own < share * area)
        if not bad.any():
            break
        sub[bad] = arg[bad]
    idx[y0:y1, x0:x1] = sub
    return idx


# ---------------------------------------------------------------- the guard
def _hue(c):
    c = np.asarray(c, np.float64) / 255
    mx, mn = c.max(-1), c.min(-1)
    d = np.maximum(mx - mn, 1e-6)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4))
    return h * 60


def sun_hue(img):
    h = _hue(img)
    lo, hi = C.SUN_HUES
    return (h > lo) | (h < hi) if lo > hi else (h > lo) & (h < hi)


def sun_mask(img):
    """pixels in the sun's saturated pinks and salmons"""
    return sun_hue(img) & (chroma(img) > 0.3)


def unit_mask(img):
    """pixels in the hue bands kept free for the units (palette.UNIT_HUES), saturated enough to read as theirs"""
    h, ch = _hue(img), chroma(img)
    m = np.zeros(h.shape, bool)
    for lo, hi in C.UNIT_HUES.values():
        m |= (h >= lo) & (h <= hi)
    return m & (ch > 0.2)




def measure(img, zmap):
    """per zone: share of the picture, luma p5..p50..p95 (contrast), saturation p95 outside the sun's hues,
    detail (neighbour pairs that differ), the sun's pixels, the units' hues"""
    img = np.asarray(img)[..., :3]
    Y, C, S, Uh, SH = luma(img), chroma(img), sun_mask(img), unit_mask(img), sun_hue(img)
    diff_x = np.any(img[:, 1:] != img[:, :-1], -1); diff_y = np.any(img[1:] != img[:-1], -1)
    out = {}
    for name, z in ZONES.items():
        m = zmap == z["code"]
        if m.sum() < 50:
            continue
        mx = m[:, 1:] & m[:, :-1]; my = m[1:] & m[:-1]
        det = (diff_x[mx].sum() + diff_y[my].sum()) / max(1, mx.sum() + my.sum())
        y = Y[m]
        cs = C[m & ~SH]                                  # the sun's family has its own cap and share
        out[name] = dict(share=float(m.mean()), lo=float(np.percentile(y, 5)), mid=float(np.percentile(y, 50)),
                         hi=float(np.percentile(y, 95)), contrast=float(np.percentile(y, 95) - np.percentile(y, 5)),
                         p90=float(np.percentile(y, 90)),
                         sat=float(np.percentile(cs, 95)) if cs.size else 0.0, detail=float(det),
                         sun=float(S[m].mean()), units=int(Uh[m].sum()))
    return out


def brightest_region(img, zmap, blur=40, top=0.05):
    """squint at the land (playfield, focus, frame, backdrop: not the sky and vista): the top `top` of a box blur of the
    luma. Returns (share of that region on the playfield, its centroid x)"""
    from PIL import Image, ImageFilter
    Y = luma(np.asarray(img)[..., :3])
    G = np.asarray(Image.fromarray((Y * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(blur))) / 255.0
    land = np.isin(zmap, [CODE["playfield"], CODE["focus"], CODE["frame"], CODE["backdrop"]])
    reg = land & (G >= np.percentile(G[land], 100 * (1 - top)))
    ys, xs = np.nonzero(reg)
    return float((zmap[reg] == CODE["playfield"]).mean()), float(xs.mean())


def lint(art: Path, quiet: bool = False) -> int:
    """measure art/map.png against the budgets; 0 when the hierarchy holds"""
    from PIL import Image
    art = Path(art)
    img = np.asarray(Image.open(art / "map.png").convert("RGB"))
    zmap = np.asarray(Image.open(art / "zones.png"))
    M = measure(img, zmap)
    bad = []
    rows = ["zone        share  luma p5-p50-p95  contrast  sat p95  detail  energy   sun   unit-hue px   budget (value / sat)"]
    for name, m in M.items():
        z = ZONES[name]
        rows.append(f"{name:10s} {m['share']:6.1%}  {m['lo']:.2f}-{m['mid']:.2f}-{m['hi']:.2f}    {m['contrast']:.3f}    "
                    f"{m['sat']:.3f}   {m['detail']:.3f}  {m['contrast'] * m['detail']:.4f}  {m['sun']:5.1%}  {m['units']:6d}        "
                    f"{z['value'][0]:.2f}-{z['value'][1]:.2f} / {z['sat']:.2f}")
        if (UNIT_ZONES is None or name in UNIT_ZONES) and m["units"] > 0.0002 * m["share"] * img.shape[0] * img.shape[1]:
            bad.append(f"{name}: {m['units']} pixels in the units' hue bands (kept free for them)")
        if name == "focus":
            continue
        if m["lo"] < z["value"][0] - 0.03 or m["hi"] > z["value"][1] + 0.03:
            bad.append(f"{name}: values {m['lo']:.2f}-{m['hi']:.2f} outside {z['value']}")
        if m["sat"] > z["sat"] + 0.03:
            bad.append(f"{name}: saturation {m['sat']:.3f} over its cap {z['sat']}")
        if m["sun"] > SUN_SHARE_B.get(name, 0.002):
            bad.append(f"{name}: {m['sun']:.1%} of it in the sun's hues (allowed {SUN_SHARE_B.get(name, 0.002):.1%})")
    # quieter with every step back: less contrast, and less texture energy (contrast x detail). Detail alone may stay
    # up: the back keeps its dabs and puffs, it just says them softly
    order = [n for n in ("frame", "backdrop", "vista") if n in M]
    for a, b in zip(order, order[1:]):
        if M[a]["contrast"] <= M[b]["contrast"]:
            bad.append(f"contrast must fall with depth: {a} {M[a]['contrast']:.3f} <= {b} {M[b]['contrast']:.3f}")
        ea, eb = M[a]["contrast"] * M[a]["detail"], M[b]["contrast"] * M[b]["detail"]
        if ea <= eb:
            bad.append(f"texture energy must fall with depth: {a} {ea:.4f} <= {b} {eb:.4f}")
    if "playfield" in M and "frame" in M:
        pf, fr = M["playfield"], M["frame"]
        if pf["detail"] >= fr["detail"]:
            bad.append("the playfield is busier than the frame")
        if pf["mid"] - fr["mid"] < 0.15:
            bad.append(f"the frame ({fr['mid']:.2f}) is not clearly darker than the playfield ({pf['mid']:.2f})")
        if pf["contrast"] >= fr["contrast"]:
            bad.append("the playfield has more contrast than the frame: units would not pop")
        # bright crown tops or snow shelves must not flood the frame: its 90th percentile stays under the field's median
        if fr["p90"] > pf["mid"] + 0.05:
            bad.append(f"the frame's 90th percentile ({fr['p90']:.2f}) is over the playfield's median + 0.05 "
                       f"({pf['mid']:.2f}): the frame is louder than the field")
        # the brightest large region (the top 5% of a squint over the land) is the playfield's centre
        share, cx = brightest_region(img, zmap)
        if share < 0.6 or not (img.shape[1] / 3 <= cx <= 2 * img.shape[1] / 3):
            bad.append(f"the brightest large region is not the playfield's centre ({share:.0%} of it on the playfield, "
                       f"centred at x {cx:.0f})")
        # the units added later: their dark outline must stand off the field
        if pf["lo"] - OUTLINE < PF_LO_GAP:
            bad.append(f"the playfield's darks ({pf['lo']:.2f}) are too close to a unit's outline ({OUTLINE})")
    if not quiet:
        print("\n".join(rows))
        print("\n".join("FAIL " + b for b in bad) if bad else "arena lint: the hierarchy holds")
    return 1 if bad else 0


def tint(img, zmap, alpha=0.55):
    """a zone map for looking: each zone tinted its own colour over the greyscale picture"""
    cols = {0: (0, 0, 0), 1: (90, 200, 120), 2: (250, 70, 140), 3: (240, 170, 60), 4: (90, 140, 230), 5: (170, 110, 230),
            6: (200, 200, 210)}
    g = luma(np.asarray(img)[..., :3])[..., None] * 255
    out = np.repeat(g, 3, -1)
    for c, col in cols.items():
        m = zmap == c
        out[m] = out[m] * (1 - alpha) + np.array(col) * alpha
    return out.astype(np.uint8)
