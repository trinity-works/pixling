"""The arena's data renders -> the painted map (stepped ramps, zone by zone), its occluders, the level data.

    world.npy / back.npy / ids.npy (arena/blender/arena.py) -> art/map.png, art/zones.png, art/occ.png + occ.json,
    art/level.json

The look is the fp engine's painted view (fp/hd2d.py) on an orthographic map: every material's lit value picks a band
of its ramp (RAMPS, tune here, no re-render). What a pixel may show is set by its depth ZONE (arena/zones.py): the
ramp is merged down to the zone's step budget, the lit value is blurred inside the material by the zone's stroke size
before stepping, small clusters are absorbed up to the zone's minimum, and the palette colour is rendered through the
zone (the sun's colours kept or swapped, hazed toward the fog, saturation capped, value clamped). So the playfield
stays a calm two-tone field, the frame dark, the backdrop's forests and the vista's cumulus quieter with every step
back but still painted in dabs and puffs.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from . import place as P
from . import zones as Z
from . import palette as C
from .palette import rgb



def _bind():
    """read the active map's biome: its materials and ramps, the palette as indices and as every zone renders it"""
    global B, MAT, RAMPS, KEYS, KIDX, PALRGB, ZPAL, CLOUD_MATS
    from .maps import active
    B = active().biome
    MAT, RAMPS = B.MAT, B.RAMPS
    CLOUD_MATS = tuple(getattr(B, "CLOUD_MATS", ()))
    KEYS = list(C.PAL)
    KIDX = {k: i for i, k in enumerate(KEYS)}
    PALRGB = np.array([rgb(C.PAL[k]) for k in KEYS], np.uint8)
    ZPAL = Z.zone_palette(KEYS)


_bind()


def blur(a: np.ndarray, sigma: float) -> np.ndarray:
    r = max(1, int(math.ceil(sigma * 2.5)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    for ax in (0, 1):
        p = np.pad(a, [(r, r) if i == ax else (0, 0) for i in range(2)], mode="edge")
        n = a.shape[ax]
        a = sum(w * (p[i:i + n] if ax == 0 else p[:, i:i + n]) for i, w in enumerate(k))
    return a


def decode(raw: np.ndarray):
    raw = raw.astype(np.float32)
    lit = (raw[..., 0] - 0.2) / 0.4
    mid = np.round(raw[..., 1] * 64).astype(np.int32)
    dep = raw[..., 2] * 800 - 200
    a = raw[..., 3] > 0.5
    mid[~a] = 0
    return lit, mid, dep, a


def step_zoned(lit, mid, zone, s=1.0):
    """palette index per pixel (-1 where nothing): each (material, zone) stepped through the material's ramp merged
    to the zone's budget, its lit value first blurred inside the pair by the zone's stroke size"""
    idx = np.full(lit.shape, -1, np.int32)
    for name, zb in Z.ZONES.items():
        zm = zone == zb["code"]
        if not zm.any():
            continue
        for n, mi in MAT.items():
            if n not in RAMPS:
                continue
            m = zm & (mid == mi)
            if not m.any():
                continue
            th, keys = Z.reduce_ramp(*RAMPS[n], zb["steps"])
            v = lit
            if zb["soft"] > 0:
                ys, xs = np.nonzero(m)
                r = int(zb["soft"] * s * 3) + 2
                y0, y1, x0, x1 = max(0, ys.min() - r), ys.max() + r + 1, max(0, xs.min() - r), xs.max() + r + 1
                mm, ll = m[y0:y1, x0:x1], lit[y0:y1, x0:x1]
                w = blur(mm.astype(np.float32), zb["soft"] * s)
                vv = np.where(mm, blur(np.where(mm, ll, 0), zb["soft"] * s) / np.maximum(w, 1e-3), ll)
                v = lit.copy(); v[y0:y1, x0:x1] = vv
            b = np.searchsorted(np.array(th), v[m], side="right") if th else np.zeros(int(m.sum()), int)
            idx[m] = np.array([KIDX[k] for k in keys])[b]
    return idx


def _dab_masks():
    """dab stamps: leaf-shaped ellipses, 8 turns x 3 lengths, as (dy, dx) offsets"""
    out = {}
    for L in (4, 6, 8):
        for k in range(8):
            a = k * math.pi / 8
            ca, sa = math.cos(a), math.sin(a)
            pts = []
            r = L
            for y in range(-r, r + 1):
                for x in range(-r, r + 1):
                    p, q = x * ca + y * sa, -x * sa + y * ca
                    t = p / (L / 2)
                    if abs(t) <= 1 and abs(q) <= (L * 0.24) * (1 - t * t) ** 0.6 * (1.15 - 0.3 * t):
                        pts.append((y, x))
            out[(L, k)] = np.array(pts, np.int64).reshape(-1, 2)
    return out


DAB = None


def dab_edges(idx, mid, zone, gu, gv, codes, s=1.0, mats=None, seed=11, spacing=4.0):
    """paint the boundaries between two ramp steps of one material with dabs instead of a bare contour: along every
    such boundary (in the given zones and materials), every `spacing` px or so, a leaf-shaped dab of one side's key
    reaches into the other (both ways, the lighter one more often), turned along a slow flow field. The step count
    and the palette stay the same; only the edges become brushwork. Opt-in per biome (biome.DAB_EDGES)."""
    global DAB
    DAB = DAB or _dab_masks()
    H, W = idx.shape
    sel = np.isin(zone, codes) & (idx >= 0)
    if mats is not None:
        sel &= np.isin(mid, mats)
    bnd = np.zeros((H, W), bool)
    for dy, dx in ((0, 1), (1, 0)):
        a = (slice(0, H - dy), slice(0, W - dx)); b = (slice(dy, H), slice(dx, W))
        e = sel[a] & sel[b] & (mid[a] == mid[b]) & (idx[a] != idx[b])
        bnd[a] |= e
    ys, xs = np.nonzero(bnd)
    if not len(ys):
        return idx
    rng = np.random.default_rng(seed)
    cell = max(2, int(round(spacing * s)))
    key = (ys // cell) * (W // cell + 1) + xs // cell
    order = rng.permutation(len(ys))
    _, first = np.unique(key[order], return_index=True)
    pick = order[first]
    lum = luma(PALRGB)
    out = idx.copy()
    flow = (0.55 * math.pi * P.fbm(gu[ys[pick], xs[pick]], gv[ys[pick], xs[pick]], 5.0, 77) + math.pi / 5) % math.pi
    for n, i in enumerate(pick):
        y, x = ys[i], xs[i]
        # the two keys meeting here
        k0 = idx[y, x]
        nb = [(y, x + 1), (y + 1, x), (y, x - 1), (y - 1, x)]
        k1 = next((idx[q] for q in nb if 0 <= q[0] < H and 0 <= q[1] < W and sel[q] and mid[q] == mid[y, x]
                   and idx[q] != k0), None)
        if k1 is None:
            continue
        light, dark = (k0, k1) if lum[k0] >= lum[k1] else (k1, k0)
        paint_, into = (light, dark) if rng.random() < 0.65 else (dark, light)
        L = (4, 6, 8)[min(2, int(rng.random() * 3 * s ** 0.5))]
        m = DAB[(L, int(flow[n] / (math.pi / 8)) % 8)]
        py, px = m[:, 0] + y, m[:, 1] + x
        ok = (py >= 0) & (py < H) & (px >= 0) & (px < W)
        py, px = py[ok], px[ok]
        hit = sel[py, px] & (mid[py, px] == mid[y, x]) & (idx[py, px] == into)
        out[py[hit], px[hit]] = paint_
    return out


def luma(c):
    c = np.asarray(c, np.float64)
    return (c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114) / 255.0


def fbm2(h, w, scale, seed, s=1.0):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    return P.fbm(xx / s / P.PPM, yy / s / P.PPM, scale, seed)


# ---------------------------------------------------------------- the map
def composite(work: Path, drop_clouds: bool = False) -> dict:
    """the painted picture from the data renders: world and back composited by depth, zoned, stepped, cleaned, the
    rims, the sky, the sunk cliffs. drop_clouds leaves the cumulus and the cloud sea out of the back (the drifting
    layers carry them: arena/layers.py)"""
    work = Path(work)
    lw, mw, dw, aw = decode(np.load(work / "raw" / "world.npy"))
    lb, mb, db, ab = decode(np.load(work / "raw" / "back.npy"))
    if drop_clouds:
        ab = ab & ~np.isin(mb, CLOUD_MATS)
    useb = ab & (~aw | (db < dw))
    lit, mid, dep = np.where(useb, lb, lw), np.where(useb, mb, mw), np.where(useb, db, dw)
    a = aw | ab
    H, W = lit.shape
    s = W / P.W                                   # render scale (0.5 for a quick look)
    sp = s * P.PPM / 32.0                         # stroke scale: strokes and cleanups are set at 32 px/m (STYLE.md)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64) / s
    A = (P.Y0 - yy) / P.PPM
    z = A * P.CE - dep * P.SE                     # where every pixel's surface is
    gu = (xx - P.X0) / P.PPM
    gv = A * P.SE + dep * P.CE

    # zones: what Blender tagged each object with; the terrain by where it is; no coverage = sky (the cloud sea's gaps
    # under the ledge are vista)
    ids = np.load(work / "raw" / "ids.npy")
    zone = np.round(ids[..., 2] * 8).astype(np.int32)
    zone[ids[..., 3] < 0.5] = -1
    trees = B.frame_trees(P.layout())
    terr = a & (zone <= 0) & ~useb
    zt = P.zone_at(gu[terr], gv[terr], z[terr], trees)
    zone[terr] = np.array([Z.CODE[n] for n in zt], np.int32)
    zone[a & (zone <= 0) & useb] = Z.CODE["backdrop"]
    skyidx, sea = B.sky(H, W, s)
    zone[~a] = Z.CODE["sky"]
    zone[~a & sea] = Z.CODE["vista"]
    c = dict(lit=lit, mid=mid, dep=dep, a=a, aw=aw, ab=ab, useb=useb, ids=ids, zone=zone, z=z, gu=gu, gv=gv, s=s, sp=sp,
             W=W, H=H, work=work)

    # the ground's parts per pixel (the biome's ground painter: lanes, paths, patches), then each (material, zone)
    # stepped through its ramp, the zone's cleanup, the biome's touches (rims), the sky, the biome's last touches
    mid = c["mid"] = B.ground(c)
    idx = step_zoned(lit, mid, zone, sp)
    for name, zb in Z.ZONES.items():
        r, share = zb["clean"]
        if r:
            idx = Z.clean(idx, (zone == zb["code"]) & (idx >= 0), max(1, int(round(r * sp))), share)
    if getattr(B, "DAB_EDGES", None):              # opt-in: ramp-step boundaries painted with dabs
        fam = mid.copy()                          # material families: grass patches count as one surface
        for f in getattr(B, "DAB_FAMILIES", ()):
            fam[np.isin(mid, [MAT[m] for m in f])] = MAT[f[0]]
        idx = dab_edges(idx, fam, zone, gu, gv, [Z.CODE[n] for n in B.DAB_EDGES], sp,
                        mats=[MAT[m] for m in getattr(B, "DAB_MATS", MAT)])
    idx = B.after_clean(c, idx)
    idx[~a] = skyidx[~a]
    idx = B.after_sky(c, idx)

    level = Z.haze_level(zone, dep)
    level[~a] = 0
    rgbimg = ZPAL[np.clip(zone, 0, Z.NZ - 1), level, idx]
    return dict(rgb=rgbimg, zone=zone, idx=idx, a=a, aw=aw, ab=ab, useb=useb, ids=ids, mid=mid, dep=dep, W=W, H=H,
                s=s, gu=gu, gv=gv, z=z)


def paint_map(work: Path, art: Path, seed: int = 3, c: dict = None) -> dict:
    work, art = Path(work), Path(art)
    art.mkdir(parents=True, exist_ok=True)
    c = c or composite(work)
    rgbimg, zone, ids, aw, useb, W = c["rgb"], c["zone"], c["ids"], c["aw"], c["useb"], c["W"]
    Image.fromarray(rgbimg).save(art / "map.png", optimize=True)
    Image.fromarray(np.clip(zone, 0, 255).astype(np.uint8)).save(art / "zones.png", optimize=True)

    # occluders: each tree / rock / stake / tent / the bridge cut out of the final picture, packed in an atlas
    meta = json.loads((work / "raw" / "meta.json").read_text())
    occ_info = {}
    oid = (np.round(ids[..., 0] * 255).astype(np.int32) + 256 * np.round(ids[..., 1] * 255).astype(np.int32))
    oid[ids[..., 3] < 0.5] = 0
    oid[~aw | useb] = 0
    foot = {m[0]: m[1:] for m in meta["occ"]}
    order = np.argsort(oid.ravel(), kind="stable")
    flat = oid.ravel()[order]
    starts = np.searchsorted(flat, np.arange(1, meta["occluders"] + 2))
    pieces = []
    for k in range(1, meta["occluders"] + 1):
        pix = order[starts[k - 1]:starts[k]]
        if len(pix) < 3:
            continue
        ys, xs = np.divmod(pix, W)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        tile = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
        tile[ys - y0, xs - x0, :3] = rgbimg[ys, xs]
        tile[ys - y0, xs - x0, 3] = 255
        u, v, zf, deck = (list(foot[k]) + [0])[:4]
        pc = dict(k=k, x=int(x0), y=int(y0), w=int(x1 - x0), h=int(y1 - y0), tile=tile,
                  d=round(float(P.depth(u, v, zf or 0.0)), 3))
        if deck:
            pc["deck"] = 1
        pieces.append(pc)
    pieces.sort(key=lambda p: -p["h"])               # shelf pack, tallest first
    AW = 2048
    x = y = rowh = 0
    for p in pieces:
        if x + p["w"] > AW:
            x, y, rowh = 0, y + rowh + 1, 0
        p["ax"], p["ay"] = x, y
        x += p["w"] + 1
        rowh = max(rowh, p["h"])
    atlas = np.zeros((y + rowh + 1, AW, 4), np.uint8)
    for p in pieces:
        atlas[p["ay"]:p["ay"] + p["h"], p["ax"]:p["ax"] + p["w"]] = p.pop("tile")
    Image.fromarray(atlas).save(art / "occ.png", optimize=True)
    occ_info = [dict(p) for p in sorted(pieces, key=lambda p: p["k"])]
    (art / "occ.json").write_text(json.dumps(occ_info, separators=(",", ":")))
    return dict(map=str(art / "map.png"), occluders=len(occ_info))


def _occ_ids(work: Path):
    return json.loads((Path(work) / "raw" / "meta.json").read_text())


def level_json(art: Path) -> dict:
    """the level as data for the units the user adds (art/level.json; the runtime reads it too): collision shapes,
    the nav with clearance, LOS data, gameplay zones, and the v3 keys kept (arena/level.py)"""
    from . import level
    w, _ = level.export()
    (Path(art) / "level.json").write_text(json.dumps(w, separators=(",", ":")))
    return w
