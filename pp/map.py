"""Map composer: a living diorama (hub screen, town, world map) from built sprites.

  python3 -m pp.map <map.json> [--builds out] [--out out/<name>] [--still] [--layers]

A map spec lists, in order:
  terrain  painted ground regions (land/grass, path, paving, planks, sea, shore, canopy, wall_face, fill)
           land "blades": {"density": [lo, hi], "cell": px}   small pixel grass whose density drifts (no hard patches)
           water "bank": {"at": [3, 7], "tones": [4, 3, 2], "dither": 2}   bank-to-middle tones, dithered seams
  objects  built props placed by their feet anchor, depth-sorted by feet y (`z` shifts the order only)
           `place`: id  -> exported bounds (tap area + label point) for a game / prototype
           `over`: true -> also drawn in the occluder layer (bridges, walls: movers pass under them)
  walkers  sprites moving along a waypoint path (`speed_px_s`; in the baked GIF they take whole laps)
  fx       ambient life: smoke, glints, waves, flow (rivers), birds, clouds (shadow), butterflies, fireflies
  fog      {"regions": [{"id", poly|rect|ellipse}...]}: fog-of-war clouds per region (layers export)
Every colour comes from the style's ramps; shadows are a ramp step down of what is under them.

--layers writes what a game engine needs instead of one GIF: base.gif (terrain, props and local loops),
over.png (occluders), one strip per mover and sky cloud, fog.png + fog_ids.png, and layers.json with
places, paths and speeds. Movers, birds and clouds then move at any speed, never forced by the loop.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt

from .color import hex_to_rgb
from .forge import load_style, OUT
from .io import save_gif, save_png

DIRS = ["S", "SE", "E", "NE", "N", "NW", "W", "SW"]


# ------------------------------------------------------------------ noise + masks

def _vnoise(W: int, H: int, cell: float, seed: int) -> np.ndarray:
    """Smooth value noise in [0, 1], one lattice value every `cell` px."""
    rng = np.random.default_rng(seed)
    gw, gh = int(W / cell) + 3, int(H / cell) + 3
    g = rng.random((gh, gw))
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    fx, fy = xs / cell, ys / cell
    x0, y0 = fx.astype(int), fy.astype(int)
    tx, ty = fx - x0, fy - y0
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    a = g[y0, x0] * (1 - tx) + g[y0, x0 + 1] * tx
    b = g[y0 + 1, x0] * (1 - tx) + g[y0 + 1, x0 + 1] * tx
    return a * (1 - ty) + b * ty


def _seg_dist(xs, ys, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1e-9
    t = np.clip(((xs - ax) * dx + (ys - ay) * dy) / L2, 0, 1)
    return np.hypot(xs - (ax + t * dx), ys - (ay + t * dy))


def region_sdf(reg: Dict, W: int, H: int) -> np.ndarray:
    """Signed distance-ish field, < 0 inside the region (px)."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32) + 0.5
    if "rect" in reg:
        x, y, w, h = reg["rect"]
        dx = np.maximum(x - xs, xs - (x + w))
        dy = np.maximum(y - ys, ys - (y + h))
        return np.maximum(dx, dy)
    if "ellipse" in reg:
        cx, cy, rx, ry = reg["ellipse"]
        r = np.hypot((xs - cx) / rx, (ys - cy) / ry)
        return (r - 1) * min(rx, ry)
    if "path" in reg:
        pts = reg["path"]
        d = np.full((H, W), 1e9, np.float32)
        for a, b in zip(pts[:-1], pts[1:]):
            d = np.minimum(d, _seg_dist(xs, ys, a, b))
        return d - reg.get("width", 8) / 2
    if "poly" in reg:
        im = Image.new("L", (W, H), 0)
        ImageDraw.Draw(im).polygon([tuple(p) for p in reg["poly"]], fill=1)
        inside = np.array(im) > 0
        return (distance_transform_edt(~inside) - distance_transform_edt(inside)).astype(np.float32)
    return np.full((H, W), -1.0, np.float32)     # whole map


# ------------------------------------------------------------------ palette helpers

class Pal:
    def __init__(self, style):
        self.style = style
        self.ramps = {k: [tuple(hex_to_rgb(c)) for c in v] for k, v in style.spec["ramps"].items()}
        self.down: Dict[Tuple[int, int, int], Tuple[int, int, int]] = {}
        for name, r in self.ramps.items():
            for i, c in enumerate(r):
                if i > 0 and c not in self.down:
                    self.down[c] = r[i - 1]
        ink = self.ramps.get("ink", [(40, 30, 40)])
        for r in self.ramps.values():
            if r[0] not in self.down:
                self.down[r[0]] = tuple(int(a * 0.72 + b * 0.28) for a, b in zip(r[0], ink[0]))

    def c(self, ref) -> Tuple[int, int, int]:
        """'ramp:i' or '#hex'."""
        if isinstance(ref, (list, tuple)):
            return tuple(ref)
        if ref.startswith("#"):
            return tuple(hex_to_rgb(ref))
        name, _, i = ref.partition(":")
        r = self.ramps[name]
        return r[int(i) if i else len(r) // 2]

    def pick(self, *refs) -> Tuple[int, int, int]:
        """First reference whose ramp exists in this style (defaults that work in any style)."""
        for r in refs:
            if r.startswith("#") or r.partition(":")[0] in self.ramps:
                return self.c(r)
        return self.c(refs[-1])

    def darken(self, img: np.ndarray, mask: np.ndarray, steps: int = 1) -> None:
        """One ramp step down for every masked pixel (colours not in a ramp dim toward ink)."""
        if not mask.any():
            return
        for _ in range(steps):
            px = img[mask][:, :3]
            keys, inv = np.unique(px, axis=0, return_inverse=True)
            out = np.array([self.down.get(tuple(int(v) for v in k),
                                          tuple(int(v * 0.8) for v in k)) for k in keys], np.uint8)
            sub = img[mask]
            sub[:, :3] = out[inv.reshape(-1)]
            img[mask] = sub


# ------------------------------------------------------------------ terrain painters
# Every kind reads its colours from one style ramp (`ramp`, default per kind) by role -> shade index;
# `colors` overrides any role with "ramp:i" or "#hex". Detail is sparse and low-contrast by design:
# neighbouring shades only, never a dark line across a floor.

DEFAULT_RAMP = {"grass": "grass", "land": "grass", "path": "sand", "dirt": "sand", "sand": "sand",
                "paving": "stone", "cobble": "stone", "planks": "wood", "water": "sea", "sea": "sea",
                "wall_face": "stone", "canopy": "leaf", "fill": "grass", "shore": "sea", "bridge": "stone"}


def _ramp_of(pal: Pal, reg: Dict, kind: str) -> str:
    r = reg.get("ramp", DEFAULT_RAMP.get(kind, "grass"))
    if r not in pal.ramps:
        for alt in ("grass", "leaf", "ground", "stone"):
            if alt in pal.ramps:
                return alt
    return r


BAYER4 = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16


def _blades(img, m, base, tone, cfg: Dict, W: int, H: int, seed: int) -> None:
    """Small pixel grass on bare ground: single lit blades, little tufts, blades with a shaded foot, a sunlit tip
    on lush spots. Lushness drifts slowly (`cell` px), so a meadow reads thick or thin by density, never as
    hard-edged tone patches. cfg: {"density": [lo, hi], "cell": 70}; colours: tones "blade", "blade_tip", "blade_foot"."""
    lo, hi = cfg.get("density", [0.008, 0.043])
    lush = _vnoise(W, H, cfg.get("cell", 70.0), seed + 11)
    bare = m & np.all(img[..., :3] == base, axis=-1)
    bare[:2] = False; bare[-2:] = False; bare[:, :2] = False; bare[:, -2:] = False
    rng = np.random.default_rng(seed + 12)
    pick = bare & np.roll(bare, 1, 0) & (rng.random((H, W)) < lo + (hi - lo) * lush ** 1.5)
    ys, xs = np.nonzero(pick)
    k = rng.random(len(ys))
    lit, top, shade = tone("blade", 2), tone("blade_tip", 3), tone("blade_foot", 0)   # own roles: patches may be flat
    one = k < 0.4
    tuft = (k >= 0.4) & (k < 0.7) & bare[ys - 1, xs - 1] & bare[ys - 1, xs + 1]
    foot = (k >= 0.7) & (k < 0.9)
    tip = k >= 0.9
    for sel, cells in ((one, [(0, 0, lit), (-1, 0, lit)]), (tuft, [(0, 0, lit), (-1, -1, lit), (-1, 1, lit)]),
                       (foot, [(0, 0, shade), (-1, 0, lit)]), (tip, [(0, 0, lit), (-1, 0, top)])):
        for dy, dx, c in cells:
            img[ys[sel] + dy, xs[sel] + dx, :3] = c


def paint_terrain(img: np.ndarray, pal: Pal, reg: Dict, W: int, H: int, seed: int) -> np.ndarray:
    kind = reg["kind"]
    d = region_sdf(reg, W, H)
    whole = not any(k in reg for k in ("rect", "ellipse", "path", "poly"))
    rough = 0 if whole else reg.get("rough", 1.6)
    if rough:
        d = d + (_vnoise(W, H, reg.get("rough_cell", 3.0), seed + 1) - 0.5) * 2 * rough
    m = d < 0
    rname = _ramp_of(pal, reg, kind)
    ramp = pal.ramps[rname]
    over = {k: pal.c(v) for k, v in reg.get("colors", {}).items()}
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:H, 0:W]

    def tone(role, i):
        if role in over:
            return over[role]
        i = reg.get("tones", {}).get(role, i)
        return ramp[max(0, min(len(ramp) - 1, i))]

    def put(mask, c):
        img[mask, :3] = c
        img[mask, 3] = 255

    if kind in ("grass", "land", "fill"):
        if kind == "land" and reg.get("cliff"):
            # a rock face under the land's south edge: the land shape pushed down by the cliff height
            h = int(reg["cliff"])
            rr = pal.ramps[reg.get("cliff_ramp", "rock" if "rock" in pal.ramps else "stone")]
            below = np.zeros_like(m)
            for k in range(1, h + 1):
                below[k:] |= m[:-k]
            face = below & ~m
            put(face, rr[1])
            strata = _vnoise(W, H, 2.5, seed + 9)
            put(face & (strata > 0.62), rr[2])
            put(face & (strata < 0.3), rr[0])
            top = face & np.roll(m, 1, axis=0)
            put(top, rr[min(3, len(rr) - 1)])
            foot = face & ~np.roll(face, -1, axis=0)
            put(foot, rr[0])
        base = tone("base", 1)
        put(m, base)
        if kind != "fill":
            patch = _vnoise(W, H, reg.get("patch_cell", 16.0), seed + 2)
            put(m & (patch > 0.64), tone("light", 2))
            put(m & (patch < 0.28), tone("dark", 0))
            n = int(m.sum() * reg.get("tufts", 0.01))
            for _ in range(n):
                x, y = int(rng.integers(1, W - 2)), int(rng.integers(1, H - 1))
                if m[y, x]:
                    c = tone("light", 2) if patch[y, x] <= 0.64 else tone("top", 3)
                    img[y, x:x + 2, :3] = c
            for _ in range(int(m.sum() * reg.get("flowers", 0.0))):
                x, y = int(rng.integers(1, W - 1)), int(rng.integers(1, H - 1))
                if m[y, x]:
                    img[y, x, :3] = pal.c(str(rng.choice(reg.get("flower_colors", ["plaster:3"]))))
            if reg.get("blades"):
                _blades(img, m, base, tone, reg["blades"], W, H, seed)
    elif kind in ("path", "dirt", "sand"):
        put(m, tone("base", 2))
        put(m & (d > -1.0), tone("rim", 1))
        v = _vnoise(W, H, 7.0, seed + 3)
        put(m & (d < -1.5) & (v > 0.68), tone("light", 3))
        for _ in range(int(m.sum() * reg.get("pebbles", 0.012))):
            x, y = int(rng.integers(0, W - 2)), int(rng.integers(0, H))
            if m[y, x] and d[y, x] < -1.5:
                img[y, x:x + 2, :3] = tone("rim", 1)
    elif kind in ("paving", "cobble"):
        # big flat slabs, joints one shade down (quiet), a few slabs a shade off
        fill, joint, alt = tone("base", 3), tone("joint", 2), tone("alt", 2)
        put(m, fill)
        sx, sy = reg.get("slab", reg.get("stone", [6, 4]))
        row = ys // sy
        off = (row % 2) * (sx // 2)
        cell = (xs + off) // sx
        hsh = (cell * 73856093 ^ row * 19349663 ^ seed) % 1000
        put(m & (hsh < reg.get("alt_rate", 180)), alt)
        if reg.get("joints", True):
            put(m & (ys % sy == 0) & ((xs + off) % sx != 0), joint)
            put(m & ((xs + off) % sx == 0) & (ys % sy != 0) & (hsh % 2 == 0), joint)
        if reg.get("rim", True):
            put(m & (d > -1.0) & (np.roll(~m, -1, axis=0)), tone("rim", 1))     # south lip in shadow
    elif kind == "planks":
        a, b2, seam = tone("base", 2), tone("alt", 3), tone("seam", 1)
        vertical = reg.get("vertical", False)
        u, w = (xs, ys) if vertical else (ys, xs)
        board = u // 3
        put(m, a)
        put(m & (board % 2 == 1), b2)
        put(m & (u % 3 == 2) & (w % 2 == 0), seam)
    elif kind in ("water", "sea"):
        # calm: 2-3 neighbouring tones in stretched patches, darker toward `deep_at` (top by default)
        ys_f = ys / max(1, H)
        grad = ys_f if reg.get("deep_at", "top") == "top" else 1 - ys_f
        streak = _vnoise(W * 1, H * 3, reg.get("streak", 10.0), seed + 5)[::3][:H, :W]
        v = grad * reg.get("gradient", 0.5) + streak * (1 - reg.get("gradient", 0.5))
        levels = reg.get("levels", [0.35, 0.62])
        idx = np.digitize(v, levels)
        base_i = reg.get("tones", {}).get("deep", 1)
        bank = reg.get("bank")
        if bank is not None:
            # bank -> middle: tones by distance from the edge, each seam an ordered dither (no patches, no blotches)
            at = bank.get("at", [3.0, 7.0])                   # px from the bank; the foam line is "shore"'s job
            tones = bank.get("tones", [4, 3, 2])
            wd = distance_transform_edt(m)
            dd = wd + (BAYER4[ys % 4, xs % 4] - 0.5) * bank.get("dither", 2.0)
            band = np.digitize(dd, at)
            for k, t in enumerate(tones):
                put(m & (band == k), ramp[min(len(ramp) - 1, t)])
        else:
            for k in range(len(levels) + 1):
                put(m & (idx == k), ramp[min(len(ramp) - 1, base_i + k)])
    elif kind == "shore":
        # light shallows + a foam line wherever the sea touches something else
        sea = np.isin(img[..., :3].reshape(-1, 3).view([("", img.dtype)] * 3).ravel(),
                      np.array([tuple(c) for c in ramp], dtype=img.dtype).view([("", img.dtype)] * 3).ravel()
                      ).reshape(H, W) & (img[..., 3] > 0)
        dist = distance_transform_edt(sea)
        wob = (_vnoise(W, H, 4.0, seed + 6) - 0.5) * 2
        dd = dist + wob
        width = reg.get("width", 4)
        put(sea & m & (dd < width), tone("shallow", 3))
        put(sea & m & (dd < width * 0.45), tone("shallow2", 4))
        put(sea & m & (dist <= 1), tone("foam", 5))
    elif kind == "bridge":
        # a road deck across water at any angle: pale deck, parapet lines one shade down, a shadow on the water
        sh = np.roll(np.roll(m, 1, axis=0), 1, axis=1) & ~m
        pal.darken(img, sh & (img[..., 3] > 0))
        put(m, tone("base", 3))
        put(m & (d > -1.1), tone("rim", 1))
    elif kind == "canopy":
        paint_canopy(img, pal, reg, m, d, W, H, rng, seed)
    elif kind == "massif":
        paint_massif(img, pal, reg, d, W, H, seed)
    elif kind == "wall_face":
        face, joint = tone("base", 2), tone("joint", 1)
        put(m, face)
        ch = reg.get("course", 4)
        put(m & (ys % ch == 0), joint)
        put(m & (ys % ch == 1), tone("lit", 3))
    return m


def paint_massif(img, pal: Pal, reg: Dict, d, W, H, seed):
    """One continuous mountain range: summits on a jittered grid inside the region, each a concave cone,
    blended with a smooth max into one height field (plus a little ridge detail), fading to foothills over
    `edge` px and lowered to the ground in `valleys`. Lit from the style's upper left in the rock ramp,
    snow only near the tallest summits, drawn back to front (height is screen-up) so nearer ridges overlap
    farther ones with a one-step darker rim. The lowest `foot` px of slope take `foot_ramp` (the land)."""
    rng = np.random.default_rng(seed)
    peak, edge, sp = reg.get("peak", 30.0), reg.get("edge", 36.0), reg.get("spacing", 30.0)
    ramp = pal.ramps[reg.get("ramp", "rock" if "rock" in pal.ramps else "stone")]
    snow = pal.ramps.get(reg.get("snow_ramp", "plaster" if "plaster" in pal.ramps else "fur_white"))
    t = np.clip(-d / edge, 0, 1)
    fall = t * t * (3 - 2 * t)
    for v in reg.get("valleys", []):
        u = np.clip(region_sdf(v, W, H) / v.get("width_out", 14.0), 0, 1)
        fall = fall * (u * u * (3 - 2 * u))
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    acc = np.zeros((H, W), np.float32)
    k = 0.35                                                  # smooth max: summits merge into shared ridges
    for gy in np.arange(-sp / 2, H + sp, sp * 0.8):
        for gx in np.arange(-sp / 2, W + sp, sp):
            px = gx + (rng.random() - 0.5) * sp * 0.9 + (sp / 2 if int(gy / sp) % 2 else 0)
            py = gy + (rng.random() - 0.5) * sp * 0.7
            xi, yi = int(min(W - 1, max(0, px))), int(min(H - 1, max(0, py)))
            if fall[yi, xi] < 0.25:
                continue
            hi = peak * (0.5 + 0.5 * rng.random())
            r = sp * (0.8 + 0.5 * rng.random())
            x0, x1, y0, y1 = max(0, int(px - r)), min(W, int(px + r) + 1), max(0, int(py - r)), min(H, int(py + r) + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            dd = np.hypot(xs[y0:y1, x0:x1] - px, (ys[y0:y1, x0:x1] - py) * 1.25) / r
            prof = np.clip(1 - dd, 0, 1) ** 1.5 * hi
            acc[y0:y1, x0:x1] += np.exp(k * prof) - 1
    h = np.log1p(acc) / k
    ridge = 1 - np.abs(2 * _vnoise(W, H, 9.0, seed + 3) - 1)
    h = (h + ridge * 2.2 * (h > 2)) * fall
    gx = np.zeros_like(h)
    gy = np.zeros_like(h)
    gx[:, 1:-1] = (h[:, 2:] - h[:, :-2]) / 2
    gy[1:-1] = (h[2:] - h[:-2]) / 2
    lit = 0.62 * gx + 0.42 * gy                               # > 0: faces the upper-left light
    n = len(ramp)
    lvl = np.clip(np.digitize(lit, reg.get("bands", [-0.6, -0.12, 0.3])), 0, n - 1)
    col = np.array(ramp, np.uint8)[lvl]
    foot = reg.get("foot", 6.0)                               # the lowest slopes wear the land's colour
    fr = pal.ramps.get(reg.get("foot_ramp", "grass"))
    if fr and foot > 0:
        low = h < foot + (_vnoise(W, H, 8.0, seed + 6) - 0.5) * 4
        col[low] = np.array(fr, np.uint8)[np.clip(np.digitize(lit[low], [-0.3, 0.25]), 0, len(fr) - 1)]
    if snow and reg.get("snow", 0.8) < 1:
        line = reg.get("snow", 0.8) * peak + (_vnoise(W, H, 6.0, seed + 5) - 0.5) * 5
        on = h > line
        col[on] = np.array(snow, np.uint8)[np.clip(np.digitize(lit[on], [-0.3, 0.2]) + 1, 1, len(snow) - 1)]
    body = h > 0.6
    painted = np.zeros((H, W), bool)
    top = np.zeros((H, W), np.float32)                        # height of what is drawn at each screen pixel
    maxh = int(np.ceil(h.max())) + 1
    for y in range(H):
        xs_ = np.nonzero(body[y])[0]
        if not len(xs_):
            continue
        hy = h[y, xs_]
        sy = np.round(y - hy).astype(int)
        for kk in range(maxh + 1):
            yy = sy + kk
            ok = (yy <= y) & (yy >= 0)
            if not ok.any():
                if (yy > y).all():
                    break
                continue
            X, Y = xs_[ok], yy[ok]
            c = col[y, X]
            if kk == 0:
                # silhouette of a nearer ridge over a farther, higher slope: a one-step darker rim
                rim = np.nonzero(painted[Y, X] & (top[Y, X] > hy[ok] + 2.5))[0]
                if len(rim):
                    c = c.copy()
                    for i in rim:
                        c[i] = pal.down.get(tuple(int(v) for v in c[i]), c[i])
            img[Y, X, :3] = c
            img[Y, X, 3] = 255
            painted[Y, X] = True
            top[Y, X] = hy[ok]


def paint_canopy(img, pal: Pal, reg: Dict, m, d, W, H, rng, seed):
    """Forest masses as round clumps: lit upper-left, shade lower-right, a dark rim at the bottom,
    drawn north to south so nearer clumps overlap. `mix` = [[ramp, share], ...] picks clump colours in
    noise clusters (e.g. ochre autumn groves inside green forest). Casts a shadow on the ground below."""
    mix = reg.get("mix", [[reg.get("ramp", "leaf"), 1.0]])
    r0, r1 = reg.get("radius", [2.6, 4.2])
    sp = reg.get("spacing", 4.2)
    cluster = _vnoise(W, H, reg.get("cluster", 12.0), seed + 7)
    clear = None
    if reg.get("clear"):
        clear = np.min(np.stack([region_sdf(dict(r, rough=0), W, H) for r in reg["clear"]]), 0)   # px outside the road edge
    pts = []
    for y in np.arange(-r1, H + r1, sp * 0.8):
        for x in np.arange(-r1, W + r1, sp):
            jx, jy = (rng.random() - 0.5) * sp, (rng.random() - 0.5) * sp * 0.8
            px, py = x + jx + (sp / 2 if int(y / sp) % 2 else 0), y + jy
            xi, yi = int(min(W - 1, max(0, px))), int(min(H - 1, max(0, py)))
            if not m[yi, xi] or rng.random() > reg.get("density", 1.0) or (clear is not None and clear[yi, xi] < r1 * 0.9):
                continue
            pts.append((py, px, r0 + rng.random() * (r1 - r0), cluster[yi, xi], rng.random()))
    # `clear`: roads through the forest stay open; `line`: an even row of crowns along each side of them
    for road in reg.get("clear", []):
        if not reg.get("line", True):
            continue
        w = road.get("width", 6) / 2 + r1 * 0.55
        for (ax, ay), (bx, by) in zip(road["path"][:-1], road["path"][1:]):
            L = math.hypot(bx - ax, by - ay)
            nx, ny = -(by - ay) / (L or 1), (bx - ax) / (L or 1)
            for i in range(int(L / (sp * 1.05)) + 1):
                f = i * sp * 1.05 / (L or 1)
                for side in (-1, 1):
                    px, py = ax + (bx - ax) * f + nx * w * side, ay + (by - ay) * f + ny * w * side
                    xi, yi = int(min(W - 1, max(0, px))), int(min(H - 1, max(0, py)))
                    if m[yi, xi] and clear[yi, xi] >= r1 * 0.5:
                        pts.append((py, px, (r0 + r1) / 2, cluster[yi, xi], rng.random()))
    pts.sort()
    # ground shadow first: every clump darkens a disc offset down-right
    sh = np.zeros((H, W), bool)
    for py, px, r, c, _ in pts:
        y0, y1 = max(0, int(py - r + 1)), min(H, int(py + r + 3))
        x0, x1 = max(0, int(px - r + 1)), min(W, int(px + r + 3))
        if y1 > y0 and x1 > x0:
            yy, xx = np.mgrid[y0:y1, x0:x1]
            sh[y0:y1, x0:x1] |= (xx - px - 1.5) ** 2 + ((yy - py - 2.5) * 1.3) ** 2 <= r * r
    pal.darken(img, sh & (img[..., 3] > 0), reg.get("shadow_steps", 1))
    shares = np.cumsum([s for _, s in mix]) / sum(s for _, s in mix)
    for py, px, r, c, u in pts:
        k = int(np.searchsorted(shares, (c * 0.7 + u * 0.3) if reg.get("clustered", True) else u))
        ramp = pal.ramps[mix[min(k, len(mix) - 1)][0]]
        n = len(ramp)
        y0, y1 = max(0, int(py - r - 1)), min(H, int(py + r + 2))
        x0, x1 = max(0, int(px - r - 1)), min(W, int(px + r + 2))
        if y1 <= y0 or x1 <= x0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32) + 0.5
        dx, dy = xx - px, (yy - py) * 1.1
        inside = dx * dx + dy * dy <= r * r
        lit = (dx + dy) / r          # -1.4 upper-left .. +1.4 lower-right
        lvl = np.where(lit < -0.55, 3, np.where(lit < 0.1, 2, np.where(lit < 0.7, 1, 0)))
        lvl = np.minimum(lvl + reg.get("lift", 0), n - 1)
        reg_px = img[y0:y1, x0:x1]
        for L in range(4):
            sel = inside & (lvl == L)
            reg_px[sel, :3] = ramp[min(n - 1, L + reg.get("base", 0))]
            reg_px[sel, 3] = 255
        if reg.get("speck", True) and r > 3:
            sy, sx = int(py - r * 0.45), int(px - r * 0.35)
            if 0 <= sy < H and 0 <= sx < W - 1:
                img[sy, sx:sx + 2, :3] = ramp[min(n - 1, 4 + reg.get("base", 0))] if n > 4 else ramp[-1]


# ------------------------------------------------------------------ sprites

class Sprite:
    def __init__(self, build_dir: Path):
        self.dir = build_dir
        self.meta = json.loads((build_dir / (build_dir.name + ".json")).read_text())
        self.fw, self.fh = self.meta["frame_w"], self.meta["frame_h"]
        self.anchor = self.meta["anchor"]
        self.sheets = {}

    def frame(self, clip: str, direction: str, i: int) -> np.ndarray:
        c = self.meta["clips"].get(clip) or next(iter(self.meta["clips"].values()))
        if clip not in self.sheets:
            self.sheets[clip] = np.array(Image.open(self.dir / c["sheet"]).convert("RGBA"))
        sh = self.sheets[clip]
        dirs = self.meta["directions"]
        r = dirs.index(direction) if direction in dirs else 0
        n = sh.shape[1] // self.fw
        f = i % n
        return sh[r * self.fh:(r + 1) * self.fh, f * self.fw:(f + 1) * self.fw]

    def nframes(self, clip: str) -> int:
        c = self.meta["clips"].get(clip) or next(iter(self.meta["clips"].values()))
        return len(c["frames"])

    def speed(self, clip: str) -> float:
        c = self.meta["clips"].get(clip) or {}
        return float(c.get("speed_px_per_cycle") or 0)


def _blit(canvas, spr, x, y, anchor, flip, pal, shadow_col):
    """Blit a sprite frame with its anchor at (x, y). The sprite's baked ground shadow becomes a
    palette step down of whatever is under it."""
    if flip:
        spr = spr[:, ::-1]
        ax = spr.shape[1] - 1 - anchor[0]
    else:
        ax = anchor[0]
    X0, Y0 = int(x) - ax, int(y) - anchor[1]
    H, W = canvas.shape[:2]
    h, w = spr.shape[:2]
    x0, y0, x1, y1 = max(0, X0), max(0, Y0), min(W, X0 + w), min(H, Y0 + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = spr[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0]
    reg = canvas[y0:y1, x0:x1]
    a = s[..., 3] > 0
    sh = a & np.all(s[..., :3] == shadow_col, axis=-1)
    body = a & ~sh
    if sh.any():
        pal.darken(reg, sh)
    reg[body] = s[body]


# ------------------------------------------------------------------ walkers

def _heading(dx: float, dy_screen: float) -> str:
    ang = math.degrees(math.atan2(dx, dy_screen * 2))   # 0 = south (down), 90 = east
    return DIRS[int(((ang % 360) + 22.5) // 45) % 8]


class Walker:
    def __init__(self, spec: Dict, spr: Sprite, frames: int):
        self.spr, self.spec = spr, spec
        self.clip = spec.get("clip", "walk")
        pts = [p[:2] for p in spec["path"]]
        waits = [p[2] if len(p) > 2 else None for p in spec["path"]]
        if spec.get("loop", True):
            pts = pts + [pts[0]]
            waits = waits + [None]
        stride = spr.speed(self.clip) or 12.0
        n_walk = spr.nframes(self.clip)
        speed = spec.get("speed", stride / n_walk)          # world px / frame
        dist_total = 0.0
        legs = []
        for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy * 2)
            legs.append((a, b, L, _heading(dx, dy)))
            dist_total += L
            if waits[i + 1]:
                legs.append(waits[i + 1])
        wait_frames = sum(w.get("frames", 16) for w in legs if isinstance(w, dict))
        walk_frames = dist_total / speed
        laps = max(1, round(frames / (walk_frames + wait_frames)))
        per_lap = frames / laps
        walk_frames = max(1.0, per_lap - wait_frames)
        # lock the stride so a lap is a whole number of walk cycles (no foot pop at the loop point)
        cycles = max(1, round(dist_total / stride))
        self.stride = dist_total / cycles
        self.v = dist_total / walk_frames
        self.n_walk = n_walk
        self.legs, self.per_lap = legs, per_lap
        self.phase = spec.get("phase", 0.0) * per_lap

    def state(self, t: int):
        """-> (x, y, clip, dir, frame index, flip)."""
        tt = (t + self.phase) % self.per_lap
        dist = 0.0
        last = None
        for leg in self.legs:
            if isinstance(leg, dict):
                n = leg.get("frames", 16)
                if tt < n:
                    x, y = last[1]
                    return x, y, leg.get("clip", "idle"), leg.get("dir", last[3]), int(tt), False
                tt -= n
                continue
            a, b, L, hd = leg
            n = L / self.v
            last = leg
            if tt < n:
                f = tt / n
                d = dist + f * L
                x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
                return round(x), round(y), self.clip, hd, int(d / self.stride * self.n_walk), False
            tt -= n
            dist += L
        a, b, L, hd = last
        return b[0], b[1], self.clip, hd, 0, False


# ------------------------------------------------------------------ ambient fx

def _periodic(t, period, phase=0.0):
    return ((t / period) + phase) % 1.0


def fx_layer(canvas, under, pal: Pal, fx: Dict, t: int, frames: int, W: int, H: int, seed: int, late: bool):
    kind = fx["kind"]
    rng = np.random.default_rng(seed)
    if kind == "smoke" and late:
        x0, y0 = fx["at"]
        n = fx.get("puffs", 5)
        life = fx.get("life", 40)
        cols = [pal.c(c) for c in fx["colors"]] if "colors" in fx else \
            [pal.pick(f"plaster:{i}", f"fur_white:{i}") for i in (3, 2, 1)]
        period = frames / max(1, round(frames / (life / n)))
        k = 0
        while k * period < frames:
            age = (t - k * period) % frames
            k += 1
            if age >= life:
                continue
            u = age / life
            jitter = rng.random()
            px = x0 + u * fx.get("drift", 10) + math.sin(u * 6 + jitter * 6) * 1.2
            py = y0 - u * fx.get("rise", 22)
            r = 1.0 + u * fx.get("grow", 2.4)
            if u > 0.8:
                r *= (1 - u) / 0.2 + 0.3
            ci = min(len(cols) - 1, int(u * len(cols)))
            _disc(canvas, px, py, r, cols[ci], hi=cols[0] if ci > 0 else None)
    elif kind == "glints" and late:
        x, y, w, h = fx["rect"]
        n = fx.get("count", 10)
        col = pal.c(fx["color"]) if "color" in fx else pal.pick("sea:5", "fur_white:3")
        col2 = pal.c(fx["color2"]) if "color2" in fx else pal.pick("sea:4", "water:3")
        for i in range(n):
            gx = x + rng.random() * w
            gy = y + rng.random() * h
            u = _periodic(t, frames / fx.get("rate", 4), rng.random())
            if u < 0.18:
                L = 1 + int(3 * math.sin(u / 0.18 * math.pi))
                xi, yi = int(gx), int(gy)
                if 0 <= yi < H:
                    lo, hi = max(0, xi - L // 2), min(W, xi + (L + 1) // 2 + 1)
                    canvas[yi, lo:hi, :3] = col if L > 2 else col2
    elif kind == "waves" and not late:
        # drifting light dashes on water: only where the ground is the water deep colour
        x, y, w, h = fx["rect"]
        deep = pal.c(fx["on"]) if "on" in fx else pal.pick("sea:1", "water:1")
        col = pal.c(fx["color"]) if "color" in fx else pal.pick("sea:2", "water:2")
        rows = range(int(y), int(y + h), fx.get("spacing", 4))
        for ri, yy in enumerate(rows):
            sp = fx.get("speed", 1) * (1 if ri % 2 else -1)
            shift = int(t * W * sp / frames) % W if sp else 0
            r2 = np.random.default_rng(seed + ri)
            for _ in range(int(w / 9)):
                xx = int(x + r2.random() * w) + shift
                L = int(r2.integers(2, 5))
                wob = int(round(math.sin((t / frames) * 2 * math.pi * 2 + r2.random() * 6)))
                for k in range(L):
                    xk = int(x + (xx + k - x) % w)
                    yk = yy + wob
                    if 0 <= yk < H and 0 <= xk < W and tuple(under[yk, xk, :3]) == deep:
                        canvas[yk, xk, :3] = col
    elif kind == "flow" and not late:
        # water flowing along a path (a river): short light dashes gliding downstream in a few lanes,
        # drawn only on water pixels. Each loop moves the pattern by whole dash spacings: seamless.
        key = id(fx)
        if key not in _FLOW:
            pts = fx["path"]
            samples = []
            for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
                L = max(1, int(math.hypot(bx - ax, by - ay)))
                for i in range(L):
                    f = i / L
                    samples.append((ax + (bx - ax) * f, ay + (by - ay) * f, (bx - ax) / L, (by - ay) / L))
            ramp = pal.ramps[fx.get("ramp", "sea" if "sea" in pal.ramps else "water")]
            _FLOW[key] = (samples, {tuple(c) for c in ramp})
        samples, water = _FLOW[key]
        total = len(samples)
        lanes, width = fx.get("lanes", 3), fx.get("width", 6)
        spacing, dash, loops = fx.get("spacing", 18), fx.get("length", 3), fx.get("loops", 3)
        head = pal.c(fx["color"]) if "color" in fx else pal.pick("sea:3", "water:3")
        tail = pal.c(fx["color2"]) if "color2" in fx else pal.pick("sea:2", "water:2")
        shift = t / frames * loops * spacing
        for j in range(lanes):
            lat = (j - (lanes - 1) / 2) * width / (lanes + 0.5)
            ph = rng.random() * spacing
            n = 0
            while n * spacing < total:
                s0 = n * spacing + ph + shift
                n += 1
                for q in range(dash):
                    si = int(s0 - q) % total
                    x, y, dx, dy = samples[si]
                    wob = math.sin(si * 0.21 + j * 2.0) * 0.8
                    xi, yi = int(round(x - dy * (lat + wob))), int(round(y + dx * (lat + wob)))
                    if 0 <= xi < W and 0 <= yi < H and tuple(under[yi, xi, :3]) in water:
                        canvas[yi, xi, :3] = head if q == 0 else tail
    elif kind == "butterflies" and late:
        x, y, w, h = fx["rect"]
        for i in range(fx.get("count", 3)):
            c = pal.c(fx["colors"][i % len(fx["colors"])]) if "colors" in fx else pal.pick(["gold:2", "banner:3", "plaster:3"][i % 3], "fur_white:3")
            p = rng.random() * 6.28
            u = t / frames * 2 * math.pi
            bx = x + w / 2 + math.sin(u * fx.get("loops", 1) + p) * w / 2
            by = y + h / 2 + math.sin(u * 2 * fx.get("loops", 1) + p * 1.7) * h / 2
            xi, yi = int(bx), int(by)
            flap = (t // 2 + i) % 2
            if 0 < xi < W - 1 and 0 < yi < H - 1:
                if flap:
                    canvas[yi, xi - 1, :3] = c
                    canvas[yi, xi + 1, :3] = c
                else:
                    canvas[yi - 1, xi, :3] = c
                    canvas[yi, xi, :3] = pal.down.get(c, c)
    elif kind == "birds" and late:
        for i in range(fx.get("count", 2)):
            y0 = fx.get("y", [20, 60])[i % len(fx.get("y", [20, 60]))]
            span = W + 20
            u = _periodic(t, frames / fx.get("laps", 1), i / max(1, fx.get("count", 2)))
            bx = -10 + u * span if i % 2 == 0 else W + 10 - u * span
            by = y0 + math.sin(u * 12.6) * 3
            col = pal.c(fx["color"]) if "color" in fx else pal.pick("plaster:3", "fur_white:3")
            sh = pal.c(fx["shade"]) if "shade" in fx else pal.pick("plaster:1", "fur_white:1")
            up = (t // 3 + i) % 2 == 0
            pts = [(-2, -1), (-1, 0), (0, 0), (1, 0), (2, -1)] if up else [(-2, 1), (-1, 0), (0, 0), (1, 0), (2, 1)]
            for dx, dy in pts:
                xi, yi = int(bx) + dx, int(by) + dy
                if 0 <= xi < W and 0 <= yi < H:
                    canvas[yi, xi, :3] = col if dx == 0 or abs(dx) == 1 else sh
            # its shadow on the ground far below
            sy = int(by) + fx.get("shadow_drop", 40)
            if 0 <= sy < H:
                x0, x1 = max(0, int(bx) - 1), min(W, int(bx) + 2)
                if x1 > x0:
                    pal.darken(canvas[sy:sy + 1, x0:x1], np.ones((1, x1 - x0), bool))
    elif kind == "clouds" and late:
        # soft cloud shadows sliding across the whole diorama (a palette step down)
        for i in range(fx.get("count", 2)):
            cw, ch = fx.get("size", [70, 34])
            span = W + cw
            u = _periodic(t, frames / fx.get("laps", 1), i / max(1, fx.get("count", 2)))
            cx = -cw / 2 + u * span
            cy = fx.get("y", [80, 260])[i % len(fx.get("y", [80, 260]))]
            ys, xs, nz = _cloud_field(W, H, seed + i)
            r = np.hypot((xs - cx) / (cw / 2), (ys - cy) / (ch / 2)) + (nz - 0.5) * 0.5
            pal.darken(canvas, r < 1)
    elif kind == "fireflies" and late:
        x, y, w, h = fx["rect"]
        col = pal.c(fx["color"]) if "color" in fx else pal.pick("glow_arcane:3", "glow_leaf:3")
        for i in range(fx.get("count", 6)):
            p = rng.random()
            u = _periodic(t, frames / fx.get("rate", 2), p)
            if math.sin(u * math.pi * 2) < 0.2:
                continue
            fx_ = x + (rng.random() * w + math.sin(t / frames * 6.28 + p * 9) * 4) % w
            fy = y + (rng.random() * h + math.cos(t / frames * 6.28 + p * 7) * 3) % h
            xi, yi = int(fx_), int(fy)
            if 0 <= xi < W and 0 <= yi < H:
                canvas[yi, xi, :3] = col


_CLOUD = {}
_FLOW = {}


def _cloud_field(W, H, seed):
    if (W, H, seed) not in _CLOUD:
        ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
        _CLOUD[(W, H, seed)] = (ys, xs, _vnoise(W + 64, H, 9.0, seed)[:, :W])
    return _CLOUD[(W, H, seed)]


def _disc(canvas, cx, cy, r, col, hi=None):
    H, W = canvas.shape[:2]
    x0, x1 = max(0, int(cx - r - 1)), min(W, int(cx + r + 2))
    y0, y1 = max(0, int(cy - r - 1)), min(H, int(cy + r + 2))
    if x1 <= x0 or y1 <= y0:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32) + 0.5
    m = (xs - cx) ** 2 + (ys - cy) ** 2 <= r * r
    canvas[y0:y1, x0:x1][m, :3] = col
    if hi is not None and r > 1.6:
        mh = m & ((xs - cx + r * 0.35) ** 2 + (ys - cy + r * 0.35) ** 2 <= (r * 0.5) ** 2)
        canvas[y0:y1, x0:x1][mh, :3] = hi


# ------------------------------------------------------------------ compose

LIVE_FX = ("birds", "clouds")      # in a layers export these move in the engine, at their own speed


def resolve_kits(spec: Dict) -> Dict:
    """Objects whose "build" is a list (a kit: ["st_house_c", "st_house_d", ...]) get one member each, picked by a
    keyed draw on the map seed + their position, never the member of the nearest same-kit neighbour already
    placed within `kit_spacing` px (default 40). Kit members should share a footprint (same-size variants of
    one house), or rows break; never auto-flip them, a mirrored sprite is lit from the wrong side.
    Plain objects are returned untouched, so maps without kits render exactly as before."""
    obs = spec.get("objects", [])
    if not any(isinstance(o.get("build"), list) for o in obs):
        return spec
    from .variants import keyed
    seed = spec.get("seed", 1)
    near = float(spec.get("kit_spacing", 40))
    out = [dict(o) for o in obs]
    placed: List[Tuple[tuple, float, float, str]] = []
    for i in sorted(range(len(out)), key=lambda i: (out[i]["at"][1], out[i]["at"][0])):
        o = out[i]
        x, y = o["at"][:2]
        if isinstance(o.get("build"), list):
            kit = tuple(o["build"])
            prev = [p for p in placed if p[0] == kit and math.hypot(p[1] - x, p[2] - y) < near]
            cand = list(kit)
            if prev:
                closest = min(prev, key=lambda p: math.hypot(p[1] - x, p[2] - y))[3]
                cand = [b for b in kit if b != closest] or cand
            o["build"] = cand[int(keyed(seed, "kit", round(x), round(y)) * len(cand))]
            placed.append((kit, x, y, o["build"]))
    return {**spec, "objects": out}


def compose(spec: Dict, builds: Path, frames: int = None, live: bool = False, meaning=None) -> List[np.ndarray]:
    """-> the baked frames. live=True leaves out walkers and LIVE_FX (the layers export draws them).
    meaning: a pp.meaning.Meaning to fill while painting (what each pixel is; see pp/meaning.py)."""
    spec = resolve_kits(spec)
    style = load_style(spec["style"])
    pal = Pal(style)
    W, H = spec["size"]
    N = frames or spec.get("frames", 96)
    seed = spec.get("seed", 1)
    shadow_col = np.array(hex_to_rgb(style.spec.get("shadow_color", "#1f1a2a")), np.uint8)
    ground = np.zeros((H, W, 4), np.uint8)
    for i, reg in enumerate(spec.get("terrain", [])):
        before = ground.copy() if meaning is not None else None
        m = paint_terrain(ground, pal, reg, W, H, seed * 100 + i)
        if meaning is not None:
            meaning.terrain(reg, m, before, ground, pal)
    cache: Dict[str, Sprite] = {}

    def sprite(name):
        if name not in cache:
            cache[name] = Sprite(builds / name)
        return cache[name]

    if meaning is not None:
        for ob in spec.get("objects", []):
            spr = sprite(ob["build"])
            meaning.object(ob, spr.frame(ob.get("clip", "idle"), ob.get("dir", "S"), 0), spr.anchor, shadow_col)
    # footprint shadows of objects (flat, under everything that stands): a step down of the ground
    for ob in spec.get("objects", []):
        s = ob.get("shadow")
        if s:
            x, y = ob["at"]
            w, h = s[:2]
            dx = s[2] if len(s) > 2 else 2
            reg = {"ellipse": [x + dx, y + 0.5, w / 2, h / 2]}
            pal.darken(ground, region_sdf(reg, W, H) < 0)
    # cast shadows: each standing object's silhouette pushed away from the light, a step down on the ground
    cast = spec.get("cast_shadow")
    if cast:
        sm = np.zeros((H, W), bool)
        for ob in spec.get("objects", []):
            if ob.get("cast", True) is False:
                continue
            spr = sprite(ob["build"])
            img = spr.frame(ob.get("clip", "idle"), ob.get("dir", "S"), 0)
            a = img[..., 3] > 0
            ax, ay = spr.anchor
            if ob.get("flip"):
                a = a[:, ::-1]
                ax = a.shape[1] - 1 - ax
            X0, Y0 = int(ob["at"][0]) - ax + int(cast[0]), int(ob["at"][1]) - ay + int(cast[1])
            h, w = a.shape
            x0, y0, x1, y1 = max(0, X0), max(0, Y0), min(W, X0 + w), min(H, Y0 + h)
            if x1 > x0 and y1 > y0:
                sm[y0:y1, x0:x1] |= a[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0]
        pal.darken(ground, sm & (ground[..., 3] > 0))
    walkers = [] if live else [Walker(w, sprite(w["build"]), N) for w in spec.get("walkers", [])]
    fxs = [(k, fx) for k, fx in enumerate(spec.get("fx", [])) if not (live and fx["kind"] in LIVE_FX)]
    out = []
    for t in range(N):
        canvas = ground.copy()
        for k, fx in fxs:
            fx_layer(canvas, ground, pal, fx, t, N, W, H, seed * 1000 + k, late=False)
        items = []
        for ob in spec.get("objects", []):
            spr = sprite(ob["build"])
            clip = ob.get("clip", "idle")
            f = (t + ob.get("phase", 0)) % spr.nframes(clip)
            # z only changes the draw order (e.g. a bridge drawn over the boats under it), never the position
            items.append((ob["at"][1] + ob.get("z", 0), ob["at"][0], spr.frame(clip, ob.get("dir", "S"), f),
                          spr.anchor, ob.get("flip", False), ob["at"][1]))
        for wk in walkers:
            x, y, clip, d, f, flip = wk.state(t)
            items.append((y + wk.spec.get("z", 0), x, wk.spr.frame(clip, d, f), wk.spr.anchor, flip, y))
        items.sort(key=lambda it: (it[0], it[1]))
        for _, x, img, anchor, flip, y in items:
            _blit(canvas, img, x, y, anchor, flip, pal, shadow_col)
        for k, fx in fxs:
            fx_layer(canvas, ground, pal, fx, t, N, W, H, seed * 1000 + k, late=True)
        out.append(canvas)
    return out


# ------------------------------------------------------------------ layers export (for an engine)

def _alpha_box(spr: "Sprite", clip: str, x: int, y: int, flip: bool):
    """Map-space bounds [x0, y0, x1, y1] of a sprite's visible pixels (first frame)."""
    a = spr.frame(clip, "S", 0)[..., 3] > 0
    ys, xs = np.nonzero(a)
    ax, ay = spr.anchor
    if flip:
        xs = a.shape[1] - 1 - xs
        ax = a.shape[1] - 1 - ax
    return [int(x - ax + xs.min()), int(y - ay + ys.min()), int(x - ax + xs.max() + 1), int(y - ay + ys.max() + 1)]


def _strip(spr: "Sprite", clip: str) -> np.ndarray:
    n = spr.nframes(clip)
    return np.concatenate([spr.frame(clip, "S", i) for i in range(n)], axis=1)


def paint_fog(spec: Dict, pal: Pal, W: int, H: int, seed: int, under: np.ndarray = None):
    """Fog-of-war: a haze that still shows a soft ghost of what lies beneath (forests and peaks a shade
    deeper, open land lighter), with a few broad lighter drifts. Every region has its OWN shape: its area
    grown by `overlap` px, rounded (`round` px, no sharp corners) and given a meandering edge with a thin
    dithered fringe. Shapes of neighbours overlap, so together they read as one fog; when one region lifts,
    the fog that remains keeps a soft, rounded edge of its own instead of a straight seam.
    -> (rgba, mask, nearest): mask = bit i set where region i's shape covers the pixel; nearest = region
    index + 1 of the closest region (for deciding which region a place belongs to), 0 outside the fog."""
    from scipy.ndimage import uniform_filter, binary_opening, binary_closing, gaussian_filter
    fog = spec.get("fog") or {}
    regions = fog.get("regions", [])
    rgba = np.zeros((H, W, 4), np.uint8)
    mask = np.zeros((H, W), np.uint8)
    nearest = np.zeros((H, W), np.uint8)
    if not regions:
        return rgba, mask, nearest
    if len(regions) > 8:
        raise ValueError("fog: at most 8 regions (one bit each)")
    ramp = pal.ramps[fog.get("ramp", "plaster" if "plaster" in pal.ramps else "fur_white")]
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0
    ys, xs = np.mgrid[0:H, 0:W]
    dith = bayer[ys % 4, xs % 4]
    rough = (_vnoise(W, H, fog.get("rough_cell", 28.0), seed) - 0.5) * 2 * fog.get("rough", 14) \
        + (_vnoise(W, H, 7.0, seed + 20) - 0.5) * 4
    feather, grow, rnd = fog.get("feather", 2.0), fog.get("overlap", 10.0), fog.get("round", 16)
    raw = np.stack([region_sdf(r, W, H) for r in regions])
    on_any = np.zeros((H, W), bool)
    for i in range(len(regions)):
        own = raw[i] < grow
        if rnd:
            own = gaussian_filter(own.astype(np.float32), rnd) > 0.5
        d = distance_transform_edt(~own) - distance_transform_edt(own) + rough
        on = (d < 0) | ((d < feather) & (dith >= d / feather))
        mask[on] |= np.uint8(1 << i)
        on_any |= on
    nearest[on_any] = raw.argmin(0)[on_any] + 1
    if under is not None:
        lum = (under[..., :3].astype(np.float32) @ np.array([0.3, 0.59, 0.11])) / 255.0
        lum = uniform_filter(lum, fog.get("ghost_blur", 11))
        soft = lambda g: binary_closing(binary_opening(g, np.ones((5, 5))), np.ones((5, 5)))    # soft shapes, no speckle
        q = lambda share: np.quantile(lum[on_any], share) if on_any.any() else -1
        dark = soft(lum < q(fog.get("ghost_share", 0.35)))              # forests, the range: a haze a step deeper
        darker = soft(lum < q(fog.get("ghost_deep", 0.12)))
    else:
        dark = darker = np.zeros((H, W), bool)
    drift = _vnoise(W, H, fog.get("patch_cell", 44.0), seed + 30) > 0.64
    n = len(ramp)
    tone = np.full((H, W), n - 1)
    tone[dark] = n - 2
    tone[darker] = n - 3
    tone[drift] = np.minimum(tone[drift] + 1, n - 1)                   # broad drifts thin the haze
    rgba[on_any, :3] = np.array(ramp, np.uint8)[tone[on_any]]
    rgba[on_any, 3] = 255
    return rgba, mask, nearest


# ------------------------------------------------------------------ atlas: the hand-drawn map

GLYPHS = {   # tiny ink icons for places on the atlas ('a' ink, 'b' accent, 'c' paper-light)
    "castle": ["a.a.a.a.a", "aaaaaaaaa", ".abbbbba.", ".abaaaba.", ".abacaba.", ".aaacaaa.", "aaaaaaaaa"],
    "skull": [".aaa.", "abbba", "acbca", "abbba", ".a.a."],
    "tower": [".a.", "aaa", "aba", "aba", "aba", "aba", "aaa", "a.a", "aaa"],
    "ring": ["..aaa..", ".a...a.", "a..b..a", "a.bbb.a", "a..b..a", ".a...a.", "..aaa.."],
    "camp": ["...a...", "..aba..", ".abbba.", "abbbbba", "aaaaaaa"],
    "cave": [".aaaaa.", "aabbbaa", "abbbbba", "aaaaaaa"],
    "house": ["..a..", ".aba.", "abbba", "aaaaa", "aacaa"],
    "dot": [".a.", "aba", ".a."],
}
COMPASS = ["......a......", "......a......", ".....aba.....", ".....aba.....", "....abbba....", "aaaaabcbaaaaa",
           "....abbba....", ".....aba.....", ".....aba.....", "......a......", "......a......"]


def _classify(base: np.ndarray, pal: Pal) -> Dict[str, np.ndarray]:
    """Terrain masks of a rendered map, read back from its palette (so the atlas follows the art)."""
    rgb = base[..., :3]
    def of(*ramps):
        cols = [c for r in ramps if r in pal.ramps for c in pal.ramps[r]]
        m = np.zeros(rgb.shape[:2], bool)
        for c in cols:
            m |= np.all(rgb == np.array(c, np.uint8), axis=-1)
        return m
    return {"water": of("sea", "water"), "forest": of("leaf", "leaf_gold"), "rock": of("rock"), "road": of("sand")}


def _down(mask: np.ndarray, k: float, thr: float = 0.5) -> np.ndarray:
    """Area-downscale a mask by factor k (<1), majority vote."""
    H, W = mask.shape
    h, w = int(round(H * k)), int(round(W * k))
    im = Image.fromarray((mask * 255).astype(np.uint8)).resize((w, h), Image.BOX)
    return np.array(im) >= thr * 255


def export_atlas(spec: Dict, pal: Pal, base: np.ndarray, places: Dict, L: Path, k: float) -> Dict:
    """The hand-drawn map of a world map: parchment, coast with ripples, rivers, tree and peak symbols,
    dotted roads, place glyphs and a compass, each on its own layer so a viewer can ink them in in turn."""
    H0, W0 = base.shape[:2]
    Wa, Ha = int(round(W0 * k)), int(round(H0 * k))
    m = _classify(base, pal)
    water, forest, rock, road = (_down(m[n], k, t) for n, t in (("water", 0.5), ("forest", 0.5), ("rock", 0.35), ("road", 0.25)))
    ink = np.array(pal.pick("ink:1"), np.uint8)
    ink2 = np.array(pal.pick("ink:2"), np.uint8)
    sand = [np.array(c, np.uint8) for c in pal.ramps.get("sand", pal.ramps.get("fur_tan"))]
    seac = [np.array(c, np.uint8) for c in pal.ramps.get("sea", pal.ramps.get("water"))]
    leafc = [np.array(c, np.uint8) for c in pal.ramps.get("leaf")]
    rng = np.random.default_rng(7)
    ys, xs = np.mgrid[0:Ha, 0:Wa]
    layers = {}

    def new():
        return np.zeros((Ha, Wa, 4), np.uint8)

    def put(img, msk, c):
        img[msk, :3] = c
        img[msk, 3] = 255
    # paper: parchment with soft blotches, a darker rim and a double ink border
    paper = new()
    put(paper, np.ones((Ha, Wa), bool), sand[3])
    put(paper, (_vnoise(Wa, Ha, 26.0, 3) > 0.78) & ((xs + ys) % 2 == 0), sand[2])        # faint stains
    edge = np.minimum(np.minimum(xs, Wa - 1 - xs), np.minimum(ys, Ha - 1 - ys))
    put(paper, (edge < 7) & (_vnoise(Wa, Ha, 5.0, 4) > 0.35), sand[2])
    put(paper, (edge == 2) | (edge == 5), ink2)
    layers["paper"] = paper
    # water: a pale wash, an ink coastline, two ripple lines offshore
    dist = distance_transform_edt(water)
    sea = new()
    put(sea, water, seac[4] if len(seac) > 4 else seac[-1])
    rip = water & (((dist > 2.5) & (dist < 3.5)) | ((dist > 5.5) & (dist < 6.5) & ((xs + ys) % 4 < 2)))
    put(sea, rip, seac[3])
    coast = water & (dist <= 1.0)
    put(sea, coast, seac[1])
    layers["water"] = sea
    # forests: little round trees (crown with an ink rim, lit top-left), in rows north to south
    trees = new()
    for y in range(3, Ha - 3, 4):
        for x in range(3 + (2 if (y // 4) % 2 else 0), Wa - 3, 5):
            px, py = x + int(rng.integers(-1, 2)), y + int(rng.integers(-1, 2))
            if not forest[min(Ha - 1, py), min(Wa - 1, px)]:
                continue
            for dy in range(-2, 2):
                for dx in range(-2, 3):
                    r2 = dx * dx + (dy + 0.5) ** 2 * 1.3
                    if r2 > 5.2:
                        continue
                    yy, xx = py + dy, px + dx
                    if 0 <= yy < Ha and 0 <= xx < Wa:
                        c = ink if r2 > 3.2 else (leafc[3] if dx + dy < 0 else leafc[2])
                        trees[yy, xx, :3] = c
                        trees[yy, xx, 3] = 255
            if py + 2 < Ha:
                trees[py + 2, px, :3] = ink
                trees[py + 2, px, 3] = 255
    layers["forest"] = trees
    # mountains: ink peaks (a light left face, a hatched right face), back to front
    peaks = new()
    for y in range(8, Ha, 9):
        for x in range(4 + (6 if (y // 9) % 2 else 0), Wa - 4, 13):
            px, py = x + int(rng.integers(-3, 4)), y + int(rng.integers(-2, 3))
            if not rock[min(Ha - 1, py), min(Wa - 1, px)]:
                continue
            hgt = int(rng.integers(6, 10))
            for j in range(hgt + 1):
                yy = py - hgt + j
                half = j
                for dx in range(-half, half + 1):
                    xx = px + dx
                    if not (0 <= yy < Ha and 0 <= xx < Wa):
                        continue
                    if abs(dx) == half:
                        c = ink
                    elif dx > 0 and (xx + yy) % 2 == 0:
                        c = ink2
                    else:
                        c = sand[3] if j < 2 else sand[2]
                    peaks[yy, xx, :3] = c
                    peaks[yy, xx, 3] = 255
    layers["peaks"] = peaks
    # roads: a dotted ink line
    roads = new()
    put(roads, road & ~water & ((xs + ys) % 3 != 0), sand[0])
    layers["roads"] = roads
    # place glyphs + compass
    icons = new()
    key = {"a": ink, "b": np.array(pal.pick("banner:2", "cloth_red:2"), np.uint8), "c": sand[3]}
    for pid, p in places.items():
        g = GLYPHS.get(p.get("icon", "dot"), GLYPHS["dot"])
        cx, cy = int(round((p["box"][0] + p["box"][2]) / 2 * k)), int(round(p["box"][3] * k))
        gh, gw = len(g), len(g[0])
        for j, row in enumerate(g):
            for i, ch in enumerate(row):
                if ch in key:
                    yy, xx = cy - gh + j, cx - gw // 2 + i
                    if 0 <= yy < Ha and 0 <= xx < Wa:
                        icons[yy, xx, :3] = key[ch]
                        icons[yy, xx, 3] = 255
        p["atlas"] = [cx, cy - gh]
    ox, oy = Wa - 26, Ha - 30
    for j, row in enumerate(COMPASS):
        for i, ch in enumerate(row):
            if ch in key:
                icons[oy + j, ox + i, :3] = key[ch]
                icons[oy + j, ox + i, 3] = 255
    layers["icons"] = icons
    out = {"size": [Wa, Ha], "scale": k, "layers": []}
    for name in ("paper", "water", "forest", "peaks", "roads", "icons"):
        fn = f"atlas_{name}.png"
        save_png(layers[name], L / fn)
        out["layers"].append({"name": name, "image": fn})
    return out


def save_delta_gif(frames: List[np.ndarray], ms: int, path: Path) -> None:
    """Looping GIF where every frame after the first stores only the pixels that changed (the rest is
    transparent over the previous frame), on one exact shared palette. A map that is mostly still
    (glints, smoke, flags) compresses to a fraction of a full-frame GIF."""
    stack = np.stack([f[..., :3] for f in frames]).astype(np.uint32)
    packed = (stack[..., 0] << 16) | (stack[..., 1] << 8) | stack[..., 2]       # one int per colour: fast unique
    keys, inv = np.unique(packed.ravel(), return_inverse=True)
    if len(keys) > 255:
        raise ValueError(f"{len(keys)} colours: a delta GIF needs at most 255")
    idx = inv.reshape(packed.shape).astype(np.uint8)
    cols = np.stack([(keys >> 16) & 255, (keys >> 8) & 255, keys & 255], 1).astype(np.uint8)
    pal = list(cols.ravel()) + [0, 0, 0] * (256 - len(cols))
    imgs = []
    for k in range(len(frames)):
        a = idx[k].copy()
        if k:
            a[idx[k] == idx[k - 1]] = 255
        im = Image.frombytes("P", (a.shape[1], a.shape[0]), a.tobytes())
        im.putpalette(pal)
        imgs.append(im)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms, loop=0, transparency=255,
                 disposal=1, optimize=False)


def export_layers(spec: Dict, builds: Path, out: Path) -> Dict:
    spec = resolve_kits(spec)
    style = load_style(spec["style"])
    pal = Pal(style)
    W, H = spec["size"]
    ms = spec.get("ms", 100)
    L = out / "layers"
    L.mkdir(parents=True, exist_ok=True)
    from .meaning import Meaning
    mean = Meaning(W, H, spec)
    frames = compose(spec, builds, live=True, meaning=mean)
    mean.save(L)
    save_delta_gif(frames, ms, L / "base.gif")
    save_png(frames[0], L / "base.png")
    cache: Dict[str, Sprite] = {}

    def sprite(name):
        if name not in cache:
            cache[name] = Sprite(builds / name)
        return cache[name]
    shadow_col = np.array(hex_to_rgb(style.spec.get("shadow_color", "#1f1a2a")), np.uint8)
    # occluders: drawn again above the movers
    over = np.zeros((H, W, 4), np.uint8)
    for ob in sorted((o for o in spec.get("objects", []) if o.get("over")), key=lambda o: o["at"][1]):
        spr = sprite(ob["build"])
        _blit(over, spr.frame(ob.get("clip", "idle"), "S", 0), *ob["at"], spr.anchor, ob.get("flip", False), pal, shadow_col)
    save_png(over, L / "over.png")
    fog_rgba, fog_mask, fog_near = paint_fog(spec, pal, W, H, spec.get("seed", 1) * 7, under=frames[0])
    regions = [r["id"] for r in (spec.get("fog") or {}).get("regions", [])]
    places = {}
    for ob in spec.get("objects", []):
        if not ob.get("place"):
            continue
        spr = sprite(ob["build"])
        box = _alpha_box(spr, ob.get("clip", "idle"), *ob["at"], ob.get("flip", False))
        cx = (box[0] + box[2]) // 2
        rid = int(fog_near[min(H - 1, max(0, (box[1] + box[3]) // 2)), min(W - 1, max(0, cx))])
        places[ob["place"]] = {"box": box, "label": [cx, box[1]], "fog": regions[rid - 1] if rid else None,
                               "icon": ob.get("icon", "dot")}
        # outline: a 1 px ring around the sprite's own silhouette (the viewer tints it by the place's state)
        spr_img = spr.frame(ob.get("clip", "idle"), "S", 0)
        a_ = spr_img[..., 3] > 0
        if ob.get("flip"):
            a_ = a_[:, ::-1]
        ring = np.zeros((a_.shape[0] + 2, a_.shape[1] + 2), bool)
        pad = np.pad(a_, 1)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            ring |= np.roll(np.roll(pad, dy, 0), dx, 1)
        ring &= ~pad
        oimg = np.zeros(ring.shape + (4,), np.uint8)
        oimg[ring] = (255, 255, 255, 255)
        ax_ = spr.anchor[0] if not ob.get("flip") else a_.shape[1] - 1 - spr.anchor[0]
        fn = f"outline_{ob['place']}.png"
        save_png(oimg, L / fn)
        places[ob["place"]]["outline"] = {"image": fn, "x": int(ob["at"][0]) - ax_ - 1, "y": int(ob["at"][1]) - spr.anchor[1] - 1}
    meta = {"name": spec["name"], "size": [W, H], "ms": ms, "frames": len(frames), "base": "base.gif", "over": "over.png",
            "places": places, "movers": [], "clouds": [], "birds": []}
    if regions:
        save_png(fog_rgba, L / "fog.png")
        ids = np.zeros((H, W, 4), np.uint8)
        ids[..., 0] = fog_mask                          # bit i = region i's own fog shape covers this pixel
        ids[..., 3] = 255
        save_png(ids, L / "fog_ids.png")
        fog_ramp = (spec.get("fog") or {}).get("ramp", "plaster" if "plaster" in pal.ramps else "fur_white")
        meta["fog"] = {"image": "fog.png", "ids": "fog_ids.png", "ids_are": "bitmask", "regions": regions,
                       "permanent": [r["id"] for r in spec["fog"]["regions"] if r.get("permanent")],
                       "edge": list(pal.pick("plaster:3", "fur_white:3")), "colors": [list(c) for c in pal.ramps[fog_ramp]]}
    meta["sprites"] = {}
    for sp_ in spec.get("sprites", []):
        spr = sprite(sp_["build"])
        clip = sp_.get("clip", "idle")
        fn = f"sprite_{sp_['id']}.png"
        save_png(_strip(spr, clip), L / fn)
        meta["sprites"][sp_["id"]] = {"sheet": fn, "frame": [spr.fw, spr.fh], "anchor": spr.anchor, "frames": spr.nframes(clip),
                                     "frame_ms": sp_.get("frame_ms", 120)}
    if spec.get("atlas"):
        meta["atlas"] = export_atlas(spec, pal, frames[0], places, L, spec["atlas"].get("scale", 0.75))
    for i, w in enumerate(spec.get("walkers", [])):
        spr = sprite(w["build"])
        clip = w.get("clip", "idle")
        fn = f"mover_{i}_{w['build']}.png"
        save_png(_strip(spr, clip), L / fn)
        meta["movers"].append({"sheet": fn, "frame": [spr.fw, spr.fh], "anchor": spr.anchor, "frames": spr.nframes(clip),
                               "frame_ms": w.get("frame_ms", 150), "path": [p[:2] for p in w["path"]], "loop": w.get("loop", True),
                               "speed": w.get("speed_px_s", 6.0), "phase": w.get("phase", 0.0)})
    for k, fx in enumerate(spec.get("fx", [])):
        if fx["kind"] == "clouds":
            cw, ch = fx.get("size", [120, 60])
            for i in range(fx.get("count", 1)):
                cw2, ch2 = int(cw), int(ch)
                layer = np.zeros((ch2 + 8, cw2 + 8, 4), np.uint8)
                d = region_sdf({"ellipse": [cw2 / 2 + 4, ch2 / 2 + 4, cw2 / 2, ch2 / 2]}, cw2 + 8, ch2 + 8)
                d = d + (_vnoise(cw2 + 8, ch2 + 8, 7.0, k * 10 + i) - 0.5) * 10
                paint_canopy(layer, pal, {"mix": [["plaster", 1.0]] if "plaster" in pal.ramps else [["fur_white", 1.0]],
                                          "radius": [4, 8], "spacing": 6, "speck": False, "shadow_steps": 0},
                             d < 0, d, cw2 + 8, ch2 + 8, np.random.default_rng(k * 10 + i), k * 10 + i)
                shadow = np.zeros_like(layer)
                shadow[layer[..., 3] > 0] = (*pal.pick("ink:0"), 255)
                cn, sn = f"cloud_{k}_{i}.png", f"cloud_{k}_{i}_shadow.png"
                save_png(layer, L / cn)
                save_png(shadow, L / sn)
                ys = fx.get("y", [H / 3])
                meta["clouds"].append({"image": cn, "shadow": sn, "y": ys[i % len(ys)], "speed": fx.get("speed_px_s", 2.5),
                                       "phase": i / max(1, fx.get("count", 1)), "alpha": fx.get("alpha", 0.72),
                                       "shadow_drop": fx.get("shadow_drop", 30), "shadow_alpha": fx.get("shadow_alpha", 0.18)})
        elif fx["kind"] == "birds":
            ys = fx.get("y", [H / 3])
            for i in range(fx.get("count", 2)):
                meta["birds"].append({"y": ys[i % len(ys)], "speed": fx.get("speed_px_s", 9.0), "dir": 1 if i % 2 == 0 else -1,
                                      "phase": i / max(1, fx.get("count", 2)), "color": list(pal.pick("plaster:3", "fur_white:3")),
                                      "shade": list(pal.pick("plaster:1", "fur_white:1")), "shadow_drop": fx.get("shadow_drop", 30)})
    (L / "layers.json").write_text(json.dumps(meta, indent=1))
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pp.map")
    ap.add_argument("spec")
    ap.add_argument("--builds", help="dir holding the build dirs (default: spec 'builds' or out/)")
    ap.add_argument("--out")
    ap.add_argument("--frames", type=int)
    ap.add_argument("--still", action="store_true", help="first frame only (fast layout check)")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--layers", action="store_true", help="engine export: base loop, occluders, movers, fog, places")
    ap.add_argument("--meaning", action="store_true", help="also write the meaning layer (material, collision, water "
                    "depth, feet-y depth, object ids) to <out>/meaning/; --layers always writes it")
    a = ap.parse_args(argv)
    spec = json.loads(Path(a.spec).read_text())
    builds = Path(a.builds or spec.get("builds", OUT))
    out = Path(a.out or OUT / spec["name"])
    out.mkdir(parents=True, exist_ok=True)
    if a.layers:
        m = export_layers(spec, builds, out)
        print(f"map {spec['name']}: layers ({m['frames']} base frames, {len(m['movers'])} movers, "
              f"{len(m['places'])} places, {len((m.get('fog') or {}).get('regions', []))} fog regions) -> {out / 'layers'}")
        return 0
    mean = None
    if a.meaning:
        from .meaning import Meaning
        mean = Meaning(spec["size"][0], spec["size"][1], spec)
    frames = compose(spec, builds, 1 if a.still else a.frames, meaning=mean)
    if mean is not None:
        mean.save(out / "meaning")
    ms = spec.get("ms", 75)
    save_png(frames[0], out / f"{spec['name']}.png")
    save_png(frames[0], out / f"{spec['name']}_x{a.scale}.png", scale=a.scale)
    if len(frames) > 1:
        save_gif(frames, [ms] * len(frames), out / f"{spec['name']}.gif", scale=1)
        save_gif(frames, [ms] * len(frames), out / f"{spec['name']}_x{a.scale}.gif", scale=a.scale)
        (out / f"{spec['name']}.json").write_text(json.dumps(
            {"name": spec["name"], "size": spec["size"], "frames": len(frames), "ms": ms}, indent=1))
    print(f"map {spec['name']}: {len(frames)} frames -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
