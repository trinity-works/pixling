"""Detail materials: surface patterns + silhouette breakup, painted in each part's own space.

Why: at 25-35 px, hand-made pixel art gets its detail from placed accent pixels (a fold line, a
fur tuft breaking the outline, a rivet glint), not from shape. These passes add that, keyed to
the bone-local surface position (buf.local), so a pattern sticks to its part like a texture and
stays pixel-stable while the part moves.

Material option:  "detail": {"kind": "fur", "scale": 1.0, "amount": 1.0}
                  "edge":   {"kind": "fur", "amount": 0.35}      (silhouette tufts / notches)
kinds: fur, feather, cloth, plate, scale, leaf, bark, stone, hide
Every pattern returns a level delta per pixel: -1 = one shade darker, +1 = one lighter.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

N4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def _hash(ix: np.ndarray, iy: np.ndarray, iz: np.ndarray, seed: float = 0.0) -> np.ndarray:
    v = np.sin(ix * 127.1 + iy * 311.7 + iz * 74.7 + seed * 19.19) * 43758.5453
    return v - np.floor(v)


def noise(p: np.ndarray, seed: float = 0.0) -> np.ndarray:
    """Trilinear value noise, p (..., 3) -> (...) in [0, 1)."""
    f = np.floor(p)
    t = p - f
    t = t * t * (3 - 2 * t)
    ix, iy, iz = f[..., 0], f[..., 1], f[..., 2]
    tx, ty, tz = t[..., 0], t[..., 1], t[..., 2]
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (tx if dx else 1 - tx) * (ty if dy else 1 - ty) * (tz if dz else 1 - tz)
                out = out + w * _hash(ix + dx, iy + dy, iz + dz, seed)
    return out


def _cell(p: np.ndarray, size, seed=0.0) -> np.ndarray:
    q = np.floor(p / np.asarray(size, float))
    return _hash(q[..., 0], q[..., 1], q[..., 2], seed)


# ------------------------------------------------------------------ patterns (local pos, normal) -> delta

def pat_fur(p, n, lit, s):
    # short vertical strands: noise stretched along z, dark in the shadow side, lit tips on top
    q = p * np.array([1.1, 1.1, 0.33]) / s
    v = noise(q, 1.0)
    d = np.where(v > 0.72, -1, 0)
    d = np.where((v < 0.16) & lit, 1, d)
    return d


def pat_feather(p, n, lit, s):
    # overlapping scallop rows (bottom edge of each row darker), rows staggered
    row_h = 3.0 * s
    col_w = 3.4 * s
    ang = np.arctan2(p[..., 1], p[..., 0])
    u = ang * 6.0 * s                      # around the body
    row = np.floor(p[..., 2] / row_h)
    uu = u / col_w * 3.4 + row * 0.5
    scallop = (1 - np.cos(2 * np.pi * (uu - np.floor(uu)))) * 0.5
    fz = (p[..., 2] / row_h + scallop * 0.55) % 1.0
    d = np.where(fz < 0.2, -1, 0)
    d = np.where((fz > 0.82) & lit, 1, d)
    return d


def pat_cloth(p, n, lit, s):
    # folds: a few vertical dark lines that wander, hem line near the bottom of the part
    ang = np.arctan2(p[..., 1], p[..., 0])
    w = ang * 3.0 / s + noise(p * np.array([0.25, 0.25, 0.12]) / s, 3.0) * 2.2
    fold = np.abs((w % 1.0) - 0.5) < 0.07
    d = np.where(fold & ~lit, -1, 0)
    d = np.where(fold & lit, -1, d) if s < 0.9 else d
    return d


def pat_plate(p, n, lit, s):
    # horizontal plate seams every few px + rivets / glints along them
    band = 3.2 * s
    fz = (p[..., 2] / band) % 1.0
    seam = fz < 0.32
    d = np.where(seam, -1, 0)
    rivet = (np.abs(fz - 0.5) < 0.18) & (_cell(p, (2.2 * s, 2.2 * s, band), 5.0) > 0.86)
    d = np.where(rivet & lit, 1, d)
    return d


def pat_scale(p, n, lit, s):
    return pat_feather(p, n, lit, s * 0.6)


def pat_leaf(p, n, lit, s):
    # 2-px leaf clusters: dark pockets in shadow, lit clusters on top
    v = noise(p / (1.6 * s), 7.0)
    d = np.where(v > 0.66, -1, 0)
    d = np.where((v < 0.26) & lit, 1, d)
    return d


def pat_bark(p, n, lit, s):
    q = p * np.array([1.4, 1.4, 0.22]) / s
    v = noise(q, 9.0)
    return np.where(np.abs(v - 0.5) < 0.06, -1, 0)


def pat_stone(p, n, lit, s):
    v = noise(p / (2.2 * s), 11.0)
    crack = np.abs(v - 0.5) < 0.07
    d = np.where(crack, -1, 0)
    d = np.where((noise(p / (1.2 * s), 12.0) > 0.8) & lit, 1, d)
    return d


def pat_hide(p, n, lit, s):
    # wrinkles: short curved dark strokes
    v = noise(p * np.array([0.7, 0.7, 1.4]) / s, 13.0)
    return np.where(np.abs(v - 0.5) < 0.085, -1, 0)


PATTERNS = {"fur": pat_fur, "feather": pat_feather, "cloth": pat_cloth, "plate": pat_plate, "scale": pat_scale,
            "leaf": pat_leaf, "bark": pat_bark, "stone": pat_stone, "hide": pat_hide}


# stroke shapes per kind: list of (dy, dx) offsets from the seed, drawn one shade darker
STROKES = {
    "fur": [(0, 0), (1, 0), (2, 0)], "bark": [(0, 0), (1, 0), (2, 0)], "cloth": [(0, 0), (1, 0), (2, 0)],
    "feather": [(0, -1), (0, 0), (0, 1)], "plate": [(0, -1), (0, 0), (0, 1)], "scale": [(0, 0), (0, 1)],
    "stone": [(0, 0), (1, 1), (2, 1)], "hide": [(0, 0), (1, 1)], "leaf": [(0, 0), (0, 1), (1, 0), (1, 1)],
}
LIT_STROKES = {"fur": [(0, 0), (1, 0)], "leaf": [(0, 0), (0, 1)], "feather": [(0, 0), (0, 1)]}


def surface(style, buf, mats: List[str], lvl: np.ndarray) -> np.ndarray:
    """Sparse, deliberate marks: one seed per jittered part-space cell, each a 2-3 px oriented stroke
    in the mid-shade band. Density follows the part's on-screen area, tiny parts get none (review #2)."""
    out = lvl.copy()
    H, W = lvl.shape
    ndl = buf.normal @ style.light
    filled = buf.mat >= 0
    from .shade import shift
    edge = np.zeros_like(filled)
    for dy, dx in N4:
        edge |= filled & ~shift(filled, dy, dx, False)
    for mi, m in enumerate(mats):
        det = style.materials[m].get("detail")
        if not det:
            continue
        kind = det["kind"]
        n = len(style.mat_colors(m))
        sp = float(det.get("spacing", {"leaf": 3.2, "stone": 4.0}.get(kind, 5.0))) * float(det.get("scale", 1.0))
        min_area = int(det.get("min_area", 40))
        per = float(det.get("per_px", {"leaf": 6.0, "fur": 11.0, "stone": 10.0}.get(kind, 14.0))) / \
            max(1e-3, float(det.get("amount", 1.0)))
        sel = buf.mat == mi
        for b in np.unique(buf.bone[sel]):
            region = sel & (buf.bone == b)
            area = int(region.sum())
            if area < min_area:
                continue
            band = region & ~edge & (out >= (1 if n > 2 else 0)) & (out <= max(0, n - 2) if n > 2 else True)
            ys, xs = np.nonzero(band)
            if len(ys) == 0:
                continue
            p = buf.local[ys, xs].astype(np.float64)
            cell = np.floor(p / sp)
            jit = np.stack([_hash(cell[:, 0], cell[:, 1], cell[:, 2], 51.0 + k) for k in range(3)], 1)
            centre = (cell + 0.2 + 0.6 * jit) * sp
            dist = np.linalg.norm(p - centre, axis=1)
            best = {}
            for i in np.argsort(dist):
                if dist[i] > 1.2:
                    break
                key = tuple(cell[i].astype(int))
                if key not in best:
                    best[key] = i
            seeds = sorted(best.values(), key=lambda i: dist[i])[: max(0, int(area / per))]
            for i in seeds:
                y, x = ys[i], xs[i]
                lit = ndl[y, x] > det.get("lit_above", 0.55)
                shape, dl = (LIT_STROKES[kind], 1) if (lit and kind in LIT_STROKES) else (STROKES[kind], -1)
                for dy, dx in shape:
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W and region[yy, xx] and not edge[yy, xx]:
                        out[yy, xx] = int(np.clip(lvl[yy, xx] + dl, 0, n - 1))
    return out


def edges(style, buf, mats: List[str]):
    """Designed silhouette breakup (review #3): a few 2-3 px tapered tufts at boundary points of
    parts at least 6 px across, spaced >= 5 px apart, pointing up or out. No random notches.
    Chosen by a hash of the surface's part-space position, so they stay put while the part moves."""
    from .shade import shift
    H, W = buf.mat.shape
    for mi, m in enumerate(mats):
        e = style.materials[m].get("edge")
        if not e:
            continue
        amount = float(e.get("amount", 0.35))
        sel = buf.mat == mi
        for b in np.unique(buf.bone[sel]):
            region = sel & (buf.bone == b)
            ys, xs = np.nonzero(region)
            if len(ys) == 0 or min(np.ptp(ys), np.ptp(xs)) + 1 < e.get("min_size", 6):
                continue
            empty = buf.mat < 0
            cands = []
            for (dy, dx), weight in (((-1, 0), 1.0), ((0, -1), 0.55), ((0, 1), 0.55)):
                out_empty = shift(empty, dy, dx, False)            # the pixel beyond is empty
                bd = region & out_empty
                for y, x in zip(*np.nonzero(bd)):
                    lp = buf.local[y, x]
                    h = float(_hash(np.floor(lp[0] / 2.5), np.floor(lp[1] / 2.5), np.floor(lp[2] / 2.5), 61.0))
                    cands.append((h * weight, y, x, dy, dx, h))
            if not cands:
                continue
            perim = len(cands)
            limit = max(1, int(perim / 12 * amount / 0.35))
            cands.sort(reverse=True)
            chosen = []
            for sc, y, x, dy, dx, h in cands:
                if len(chosen) >= limit:
                    break
                if any(abs(y - cy) + abs(x - cx) < 5 for cy, cx in chosen):
                    continue
                chosen.append((y, x))
                length = 3 if h > 0.6 else 2
                lean = 1 if h * 7 % 1 > 0.5 else -1
                for k in range(1, length + 1):
                    yy, xx = y + dy * k, x + dx * k
                    if k == length and dy != 0:
                        xx += lean                                   # tip leans: tapered, not a post
                    if not (0 <= yy < H and 0 <= xx < W) or buf.mat[yy, xx] >= 0:
                        break
                    for name in ("mat", "light", "depth", "bone", "hnorm", "height"):
                        a = getattr(buf, name)
                        a[yy, xx] = a[y, x]
                    buf.normal[yy, xx] = buf.normal[y, x]
                    buf.local[yy, xx] = buf.local[y, x]
                    if k == length and e.get("kind", "fur") in ("fur", "feather"):
                        buf.light[yy, xx] -= 0.12          # fur/feather tips step darker; leaf tips don't
