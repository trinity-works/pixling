"""Soft selective line for the exact-iso camera (opt-in: scene key "line", and "terrain_aa" for the ground).

A 1-px near-black ring drawn outside a silhouette reads as zig-zag: every stair step gets an extra L-corner pixel,
so the line thickens at each step and every step pops against light ground. This pass avoids that:

1. The line sits inside each object's silhouette (the sprite footprint never grows), on pixels whose 4-neighbour
   belongs to something farther away (another object behind, terrain or nothing).
2. Pixel-perfect: L-corner pixels (line on two perpendicular sides and none opposite, with one arm a 1-2 px stair
   step) are removed, so every stair is a single-pixel step.
3. Selout: bottom/right edges (contact, shadow side) take the style's ink; top/left edges take one tone darker
   than the face they wrap, and are dropped where the form and what is behind it already differ strongly.
4. Corner AA: each removed corner, and each ground stair corner, gets one in-between tone, picked from the closed
   palette (the nearest palette colour to the 50% mix), so long diagonals read as smooth lines.
"""
from __future__ import annotations

import numpy as np


def _lum(c):
    c = np.asarray(c, float)
    return c[..., 0] * 0.30 + c[..., 1] * 0.55 + c[..., 2] * 0.15


def _shift(a, dy, dx, fill):
    out = np.full_like(a, fill)
    H, W = a.shape[:2]
    ys = slice(max(0, dy), H + min(0, dy))
    yd = slice(max(0, -dy), H + min(0, -dy))
    xs = slice(max(0, dx), W + min(0, dx))
    xd = slice(max(0, -dx), W + min(0, -dx))
    out[ys, xs] = a[yd, xd]
    return out


def _palette(scene):
    return np.array(sorted({tuple(c) for ramp in scene.pal.values() for c in ramp}), np.uint8)


def nearest(pal, col):
    d = ((pal.astype(float) - np.asarray(col, float)) ** 2).sum(-1)
    return pal[int(d.argmin())]


def run_len(mask, axis):
    """Length of the run (along axis) each True pixel belongs to."""
    if axis == 0:
        return run_len(mask.T, 1).T
    H, W = mask.shape
    out = np.zeros(mask.shape, int)
    for y in range(H):
        row = mask[y]
        x = 0
        while x < W:
            if row[x]:
                x1 = x
                while x1 < W and row[x1]:
                    x1 += 1
                out[y, x:x1] = x1 - x
                x = x1
            else:
                x += 1
    return out


def soft_line(img, layers, scene, cfg):
    """cfg: ink_ramp, ink_tone (shadow-side line colour), drop_contrast (skip the lit-side line where the form
    already differs this much in value from what is behind it), selout_step, aa. Returns (image, line mask)."""
    img = img.copy()
    H, W = img.shape[:2]
    G, T, mat, tone = layers["GRP"], layers["T"], layers["mat"], layers["tone"]
    pal = _palette(scene)
    ink = np.array(scene.pal[cfg.get("ink_ramp", "ink")][cfg.get("ink_tone", 1)], np.uint8)
    obj = G >= 0
    # 1. inner boundary, per side: the neighbour on that side is another object (farther away) or terrain
    sides = {"down": (1, 0), "right": (0, 1), "up": (-1, 0), "left": (0, -1)}
    edge = {}
    for name, (dy, dx) in sides.items():
        Gq = _shift(G, -dy, -dx, -1)
        Tq = _shift(T, -dy, -dx, -np.inf)
        edge[name] = obj & (Gq != G) & ((Gq < 0) | (Tq < T - 1e-6))
    line = edge["down"] | edge["right"] | edge["up"] | edge["left"]
    # 2. pixel-perfect: drop L corners, but keep the true corners of a box (both perpendicular arms long)
    corners = np.zeros_like(line)
    for _ in range(2):
        L = line
        u, d, l, r = _shift(L, 1, 0, False), _shift(L, -1, 0, False), _shift(L, 0, 1, False), _shift(L, 0, -1, False)
        Lc = L & (((u & r) & ~d & ~l) | ((u & l) & ~d & ~r) | ((d & r) & ~u & ~l) | ((d & l) & ~u & ~r))
        hl = run_len(L & ~Lc, 1)
        vl = run_len(L & ~Lc, 0)
        Lc &= ((_shift(hl, 0, 1, 0) <= 2) | (_shift(hl, 0, -1, 0) <= 2) | (_shift(vl, 1, 0, 0) <= 2)
               | (_shift(vl, -1, 0, 0) <= 2))
        corners |= Lc
        line = line & ~Lc
    # 3. selout colour per line pixel
    behind = np.zeros((H, W, 3), float)
    n_b = np.zeros((H, W))
    for name, (dy, dx) in sides.items():
        m = edge[name]
        behind[m] += _shift(img, -dy, -dx, 0).astype(float)[m]
        n_b[m] += 1
    behind /= np.maximum(n_b, 1)[..., None]
    own_dark = np.zeros((H, W, 3), np.uint8)
    for m in set(mat[line].ravel()):
        if not m or m not in scene.mats:
            continue
        spec = scene.mats[m]
        ramp = scene.pal[spec["ramp"]]
        for cls in ("top", "lit", "shade"):
            k = spec.get(cls, spec.get("top", 0))
            own_dark[line & (mat == m) & (tone == cls)] = ramp[max(0, k - cfg.get("selout_step", 1))]
    contrast = np.abs(_lum(img) - _lum(behind)) / 255.0
    shadow_side = edge["down"] | edge["right"]
    sel_px = line & ~shadow_side & (contrast < cfg.get("drop_contrast", 0.33))
    img[line & shadow_side] = ink
    img[sel_px] = own_dark[sel_px]
    # 4. corner AA: a removed L corner sits between a line pixel and fill; give it the in-between tone
    if cfg.get("aa", True):
        for (y, x) in zip(*np.nonzero(corners)):
            nb = [img[y + dy, x + dx].astype(float) for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if 0 <= y + dy < H and 0 <= x + dx < W and line[y + dy, x + dx]]
            if nb:
                img[y, x] = nearest(pal, 0.5 * np.mean(nb, 0) + 0.5 * img[y, x].astype(float))
    return img, line


def soft_terrain(img, layers, scene, cfg):
    """Ground stair corners between two ground colours get one in-between tone (closed palette), so 2:1 shore, path
    and plaza edges read as smooth lines. Only on ground runs at least `min_run` long."""
    img = img.copy()
    ground = layers["GRP"] == -1
    pal = _palette(scene)
    key = (img[..., 0].astype(np.int32) << 16) | (img[..., 1].astype(np.int32) << 8) | img[..., 2].astype(np.int32)
    up, dn = _shift(key, 1, 0, -1), _shift(key, -1, 0, -1)
    lf, rt = _shift(key, 0, 1, -1), _shift(key, 0, -1, -1)
    gu, gd = _shift(ground, 1, 0, False), _shift(ground, -1, 0, False)
    gl, gr = _shift(ground, 0, 1, False), _shift(ground, 0, -1, False)
    done = np.zeros(key.shape, bool)
    long_run = run_len(ground, 1) >= cfg.get("min_run", 2)
    # a stair corner differs from its up (or down) and its left (or right) neighbour, and those two neighbours
    # share one colour: it is the inner notch of a 2:1 step
    for (a, ga), (b, gb) in (((up, gu), (lf, gl)), ((up, gu), (rt, gr)), ((dn, gd), (lf, gl)), ((dn, gd), (rt, gr))):
        m = ground & ga & gb & (a == b) & (a != key) & (a >= 0) & ~done & long_run
        for y, x in zip(*np.nonzero(m)):
            o = a[y, x]
            oc = np.array([(o >> 16) & 255, (o >> 8) & 255, o & 255], float)
            img[y, x] = nearest(pal, 0.5 * oc + 0.5 * img[y, x].astype(float))
        done |= m
    return img
