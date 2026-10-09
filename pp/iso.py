"""Exact isometric renderer for faceted styles (camera "iso_exact": Crisp Tactics, Flat Minimal).

The world is convex polytopes (half-space lists). Every pixel casts one orthographic ray at its centre; the face
nearest the viewer wins and gives one flat tone. Projection is classic 2:1 pixel isometric:

    sx = x - y          sy = (x + y) / 2 - z          (x, y in units along the iso axes, z in px)

so every edge along x or y is a clean 2:1 stair, verticals are vertical, and nothing is supersampled or resampled:
the image is exact at 1x and only ever scaled by an integer. Terrain is a cell heightfield (columns), props are
small polytopes, cast shadows are exact rays toward one light, so shadow edges are stairs as well.

A scene is a dict (written by a style's kit, e.g. tools/tactics/scenes.py): size, origin, palette (ramps), materials
(ramp + tone index per face class), ground, polys, and optional keys that switch on the extra passes:
  detail      world-pinned moss, grass tufts, flowers        terrain_aa  in-between tone on ground stair corners
  line        soft selout line (pp/iso_line.py)            night       night ramp + window glow (--hour night)
  smoke, anim, glints   ambient loop (whole-pixel steps, seamless over the frame count)

  python3 -m pp.iso scene.json --out out/<name> [--frames 24] [--hour noon|night] [--dither off|night] [--scale 4]
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from typing import Callable, Dict, List

import numpy as np
from PIL import Image

from . import iso_line

DIR = np.array([1.0, 1.0, 1.0])          # view ray toward the viewer (larger t = nearer)


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------------------ geometry

def box_planes(x0, y0, z0, x1, y1, z1):
    return [((1, 0, 0), x1, "px"), ((-1, 0, 0), -x0, "nx"), ((0, 1, 0), y1, "py"), ((0, -1, 0), -y0, "ny"),
            ((0, 0, 1), z1, "top"), ((0, 0, -1), -z0, "bot")]


def box_verts(x0, y0, z0, x1, y1, z1):
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def project(v, ox, oy):
    x, y, z = v
    return x - y + ox, (x + y) / 2 - z + oy


class Poly:
    """A convex polytope: planes [(normal, c, face_key)] meaning n.p <= c, a face table and screen bbox verts."""

    def __init__(self, planes, faces, verts, cast=True, tag="", hidden=False, grp=-1, line=True):
        self.n = np.array([p[0] for p in planes], float)
        self.c = np.array([p[1] for p in planes], float)
        self.keys = [p[2] for p in planes]
        self.faces = faces                      # face_key -> face dict ({"m": material, "decals": [...]})
        self.verts = verts
        self.cast = cast
        self.tag = tag
        self.hidden = hidden          # a shadow proxy: casts, is never drawn
        self.grp = grp                # object id for the line pass (-1 = terrain, never outlined)
        self.line = line              # False: this poly never takes or makes an outline (smoke, decals)

    @staticmethod
    def from_json(d):
        planes = [(tuple(p[0]), p[1], p[2]) for p in d["planes"]]
        return Poly(planes, d["faces"], [tuple(v) for v in d["verts"]], d.get("cast", True), d.get("tag", ""),
                    d.get("hidden", False), d.get("grp", -1), d.get("line", True))


def ray_exit(poly: Poly, X0, Y0):
    """Exit parameter (nearest-to-viewer surface) of rays p0 + t*DIR, p0 = (X0, Y0, 0), through a convex poly."""
    nd = poly.n @ DIR
    t_hi = np.full(X0.shape, np.inf)
    t_lo = np.full(X0.shape, -np.inf)
    which = np.full(X0.shape, -1, np.int16)
    ok = np.ones(X0.shape, bool)
    for i in range(len(poly.c)):
        n = poly.n[i]
        npo = n[0] * X0 + n[1] * Y0
        if nd[i] > 1e-9:
            t = (poly.c[i] - npo) / nd[i]
            m = t < t_hi
            t_hi = np.where(m, t, t_hi)
            which = np.where(m, i, which)
        elif nd[i] < -1e-9:
            t_lo = np.maximum(t_lo, (poly.c[i] - npo) / nd[i])
        else:
            ok &= npo <= poly.c[i]
    ok &= (t_lo < t_hi - 1e-9) & np.isfinite(t_hi)
    return t_hi, which, ok


def shadow_hit(poly: Poly, P, L):
    """True where the ray P + s*L (s > 0) passes through the poly."""
    nL = poly.n @ L
    lo = np.full(P.shape[0], 1e-4)
    hi = np.full(P.shape[0], np.inf)
    ok = np.ones(P.shape[0], bool)
    with np.errstate(all="ignore"):         # macOS Accelerate matmul can flag spurious FP errors on finite input
        nP = P @ poly.n.T
    for i in range(len(poly.c)):
        if nL[i] > 1e-9:
            hi = np.minimum(hi, (poly.c[i] - nP[:, i]) / nL[i])
        elif nL[i] < -1e-9:
            lo = np.maximum(lo, (poly.c[i] - nP[:, i]) / nL[i])
        else:
            ok &= nP[:, i] <= poly.c[i] + 1e-9
    return ok & (lo < hi - 1e-6) & (hi > 1e-3)


# ------------------------------------------------------------------ JSON poly builders (used by the style kits)

def box(x0, y0, z0, x1, y1, z1, faces, grp=-1, cast=True, tag="", hidden=False, line=True) -> Dict:
    """A box as a scene poly. faces: face_key -> {"m": material, "tone": top|lit|shade, "decals": [...]}, with
    "*" as the fallback face."""
    return {"planes": [[list(n), c, k] for n, c, k in box_planes(x0, y0, z0, x1, y1, z1)], "faces": faces,
            "verts": [list(v) for v in box_verts(x0, y0, z0, x1, y1, z1)],
            "cast": cast, "tag": tag, "hidden": hidden, "grp": grp, "line": line}


def shift(p: Dict, dx, dy=None) -> Dict:
    """Move a poly by (dx, dy) along the iso axes, decals included (in place)."""
    dy = dx if dy is None else dy
    p["verts"] = [[v[0] + dx, v[1] + dy, v[2]] for v in p["verts"]]
    p["planes"] = [[n, c + n[0] * dx + n[1] * dy, k] for n, c, k in p["planes"]]
    for key, f in p["faces"].items():
        du = dy if key in ("px", "nx") else dx          # u runs along y on the x faces, along x elsewhere
        for d in f.get("decals", []):
            d["u"] = [d["u"][0] + du, d["u"][1] + du]
            if "u0" in d:
                d["u0"] += du
    return p


def scale(p: Dict, k) -> Dict:
    """Scale a poly by k about the origin, decals included (in place)."""
    p["verts"] = [[v[0] * k, v[1] * k, v[2] * k] for v in p["verts"]]
    p["planes"] = [[n, c * k, kk] for n, c, kk in p["planes"]]
    for f in p["faces"].values():
        for d in f.get("decals", []):
            d["u"] = [d["u"][0] * k, d["u"][1] * k]
            d["v"] = [d["v"][0] * k, d["v"][1] * k]
            for key in ("u0", "z0", "course", "brick"):
                if key in d:
                    d[key] *= k
    return p


def mirror(p: Dict, axis: int, c0) -> Dict:
    """A copy of the poly mirrored across x = c0 (axis 0) or y = c0 (axis 1); face keys px<->nx (py<->ny) swap."""
    sw = {0: ("px", "nx"), 1: ("py", "ny")}[axis]
    p = copy.deepcopy(p)
    p["verts"] = [[(2 * c0 - v[0]) if axis == 0 else v[0], (2 * c0 - v[1]) if axis == 1 else v[1], v[2]]
                  for v in p["verts"]]
    planes = []
    for n, c, k in p["planes"]:
        n2 = list(n)
        n2[axis] = -n[axis]
        planes.append([n2, c - 2 * c0 * n[axis], sw[1] if k == sw[0] else (sw[0] if k == sw[1] else k)])
    p["planes"] = planes
    return p


def swap_xy(p: Dict) -> Dict:
    """A copy of the poly with the x and y axes swapped (a prop built along x now runs along y). Plane keys follow
    the geometry; the face table stays keyed by direction, so each face keeps the tone of the side it now faces."""
    sw = {"px": "py", "py": "px", "nx": "ny", "ny": "nx"}
    p = copy.deepcopy(p)
    p["verts"] = [[v[1], v[0], v[2]] for v in p["verts"]]
    p["planes"] = [[[n[1], n[0], n[2]], c, sw.get(k, k)] for n, c, k in p["planes"]]
    return p


# ------------------------------------------------------------------ scene

class Scene:
    def __init__(self, spec: Dict):
        self.spec = spec
        self.W, self.H = spec["size"]
        self.ox, self.oy = spec["origin"]
        self.pal = {k: [hexrgb(c) for c in v] for k, v in spec["palette"].items()}
        self.mats = spec["materials"]           # material -> {"ramp", "top", "lit", "shade", "shadow"} tone indices
        L = np.array(spec.get("light", [0, -1, 1]), float)
        self.L = L / np.linalg.norm(L)
        self.ground = spec.get("ground")
        self.static = [Poly.from_json(p) for p in spec["polys"]]
        if self.ground:
            self.static = self.ground_polys() + self.static

    def ground_polys(self) -> List[Poly]:
        g = self.ground
        C = g["cell"]
        hts = np.array(g["h"])
        n_y, n_x = hts.shape
        # the water plane: one big slab whose top is coloured per cell
        out = [Poly(box_planes(-400, -400, -64, n_x * C + 400, n_y * C + 400, 0), {"top": {"m": "@cell"}},
                    box_verts(-400, -400, -64, n_x * C + 400, n_y * C + 400, 0), cast=False, tag="water")]
        merge = g.get("merge_rows", False)
        for j in range(n_y):
            i = 0
            while i < n_x:
                h = int(hts[j, i])
                if h <= 0:
                    i += 1
                    continue
                i1 = i + 1
                if merge:
                    while i1 < n_x and hts[j, i1] == h:
                        i1 += 1
                x0, y0 = i * C, j * C
                # a merged run casts only where it stands above a lower neighbour (bank shadows on water)
                lo = hts[max(0, j - 1):j + 2, max(0, i - 1):i1 + 1]
                cast = bool((lo < h).any()) if merge else True
                out.append(Poly(box_planes(x0, y0, -64, i1 * C, y0 + C, h),
                                {"top": {"m": "@cell"}, "px": {"m": g["side"]}, "py": {"m": g["side"]}},
                                box_verts(x0, y0, 0, i1 * C, y0 + C, h), cast=cast, tag="ground"))
                i = i1
        return out

    def cell_mat(self, X, Y):
        g = self.ground
        C = g["cell"]
        i = np.clip(np.floor(X / C).astype(int), 0, len(g["mat"][0]) - 1)
        j = np.clip(np.floor(Y / C).astype(int), 0, len(g["mat"]) - 1)
        inside = (X >= 0) & (Y >= 0) & (X < len(g["mat"][0]) * C) & (Y < len(g["mat"]) * C)
        idx = np.array(g["mat"], np.int16)[j, i]
        return np.where(inside, idx, g.get("outside", 0)), list(g["names"])

    # -------------------------------------------------------------- render

    def compose(self, polys: List[Poly]):
        W, H = self.W, self.H
        px = np.arange(W) + 0.5 - self.ox
        py = np.arange(H) + 0.5 - self.oy
        SX, SY = np.meshgrid(px, py)
        X0 = SY + SX / 2
        Y0 = SY - SX / 2
        T = np.full((H, W), -np.inf)
        PID = np.full((H, W), -1, np.int32)
        PL = np.full((H, W), -1, np.int16)
        for k, poly in enumerate(polys):
            if poly.hidden:
                continue
            xs, ys = zip(*[project(v, self.ox, self.oy) for v in poly.verts])
            a0, a1 = max(0, int(math.floor(min(xs))) - 1), min(W, int(math.ceil(max(xs))) + 1)
            b0, b1 = max(0, int(math.floor(min(ys))) - 1), min(H, int(math.ceil(max(ys))) + 1)
            if a1 <= a0 or b1 <= b0:
                continue
            sl = (slice(b0, b1), slice(a0, a1))
            t, which, ok = ray_exit(poly, X0[sl], Y0[sl])
            win = ok & (t > T[sl])
            T[sl] = np.where(win, t, T[sl])
            PID[sl] = np.where(win, k, PID[sl])
            PL[sl] = np.where(win, which, PL[sl])
        GRP = np.array([p.grp if p.line else -2 for p in polys] + [-1], np.int32)[PID]
        return T, PID, PL, X0 + T, Y0 + T, T, GRP

    def tone_class(self, n):
        v = float(n @ self.L) / float(np.linalg.norm(n))
        return "top" if v >= 0.45 else ("lit" if v >= -0.2 else "shade")

    def shade(self, polys, PID, PL, HX, HY, HZ, casters):
        H, W = PID.shape
        mat_img = np.full((H, W), "", object)
        tone_img = np.full((H, W), "top", object)
        decal = np.full((H, W), "", object)
        normz = np.zeros((H, W))
        cell_idx = cell_names = None
        if self.ground:
            cell_idx, cell_names = self.cell_mat(HX, HY)
        for k, poly in enumerate(polys):
            m = PID == k
            if not m.any():
                continue
            for i, key in enumerate(poly.keys):
                mm = m & (PL == i)
                if not mm.any():
                    continue
                n = poly.n[i]
                normz[mm] = n[2] / np.linalg.norm(n)
                face = poly.faces.get(key) or poly.faces.get("*") or {"m": "ink"}
                if face["m"] == "@cell":
                    mat_img[mm] = np.array(cell_names, object)[cell_idx[mm]]
                else:
                    mat_img[mm] = face["m"]
                tone_img[mm] = face.get("tone") or self.tone_class(n)
                for d in face.get("decals", []):
                    # decal rect in face-local coords: u along the face's horizontal axis, v = z
                    u = HY if key in ("px", "nx") else HX
                    sel = mm & (u >= d["u"][0]) & (u < d["u"][1]) & (HZ >= d["v"][0]) & (HZ < d["v"][1])
                    if "stripe" in d:
                        sel &= (np.floor(HZ / d["stripe"]) % 2) == 0
                    if "course" in d:
                        # masonry: a mortar line at the bottom of every course, joints staggered per course, in
                        # whole units on the face, so courses are clean 2:1 lines and joints are vertical; the
                        # face edges never get a joint or course
                        zc = np.floor(HZ - d.get("z0", 0))
                        crs = np.floor(zc / d["course"])
                        mort = (zc % d["course"]) == 0
                        uu = np.floor(u - d.get("u0", 0) + (crs % 2) * (d["brick"] // 2))
                        joint = (uu % d["brick"]) == 0
                        keep = ((HZ >= d["v"][0] + 1) & (HZ < d["v"][1] - 1) & (u >= d["u"][0] + 1)
                                & (u < d["u"][1] - 1))
                        sel &= (mort | joint) & keep
                    decal[sel] = d["m"]
        # cast shadows on upward faces
        shadow = np.zeros((H, W), bool)
        up = (normz > 0.5) & (PID >= 0)
        if casters and up.any():
            P = np.stack([HX[up], HY[up], HZ[up]], 1)
            hit = np.zeros(P.shape[0], bool)
            for c in casters:
                hit |= shadow_hit(c, P, self.L)
            shadow[up] = hit
        return mat_img, tone_img, decal, shadow

    def paint(self, layers) -> np.ndarray:
        mat_img, tone_img, decal, shadow = layers["mat"], layers["tone"], layers["decal"], layers["shadow"]
        H, W = mat_img.shape
        img = np.zeros((H, W, 3), np.uint8)
        for m in set(mat_img.ravel()):
            if not m:
                continue
            spec = self.mats[m]
            ramp = self.pal[spec["ramp"]]
            for cls in ("top", "lit", "shade"):
                sel = (mat_img == m) & (tone_img == cls) & ~decal.astype(bool)
                if not sel.any():
                    continue
                k = spec.get(cls, spec.get("top"))
                img[sel & ~shadow] = ramp[k]
                if "shadow" in spec:
                    img[sel & shadow] = self.pal[spec.get("shadow_ramp", spec["ramp"])][spec["shadow"]]
                else:
                    img[sel & shadow] = ramp[k]
        for m in set(decal.ravel()):
            if m:
                spec = self.mats[m]
                img[decal == m] = self.pal[spec["ramp"]][spec.get("top", 0)]
        return img

    def render(self, extra: List[Poly] = ()) -> Dict:
        polys = list(self.static) + list(extra)
        T, PID, PL, HX, HY, HZ, GRP = self.compose(polys)
        mat_img, tone_img, decal, shadow = self.shade(polys, PID, PL, HX, HY, HZ, [p for p in polys if p.cast])
        return dict(mat=mat_img, tone=tone_img, decal=decal, shadow=shadow, PID=PID, HZ=HZ, T=T, GRP=GRP,
                    HX=HX, HY=HY)


# ------------------------------------------------------------------ ground detail

def ground_detail(scene: Scene, img, layers, cfg):
    """Moss on stone tops (world-pinned 2x2-unit blocks), grass tufts and flower clusters (fixed spots on open
    grass). Everything is in the closed palette and never moves between frames."""
    img = img.copy()
    mat, tone, shadow, G = layers["mat"], layers["tone"], layers["shadow"], layers["GRP"]
    pal = scene.pal
    if cfg.get("moss"):
        bx = np.floor(layers["HX"] / 2).astype(np.int64)
        by = np.floor(layers["HY"] / 2).astype(np.int64)
        hsh = ((bx * 73856093) ^ (by * 19349663) ^ 0x5bd1e995) & 0xffff
        sel = (mat == "stone") & (tone == "top") & ((hsh / 65535.0) < cfg["moss"])
        img[sel & ~shadow] = pal["moss"][1]
        img[sel & shadow] = pal["moss"][0]
    rng = np.random.RandomState(cfg.get("seed", 3))
    grass = np.isin(mat, ["grass", "grass_b"]) & (G == -1)
    ok = grass.copy()
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-3, -2, -1, 0, 1, 2, 3):
            ok &= np.roll(np.roll(grass, dy, 0), dx, 1)
    ys, xs = np.nonzero(ok[3:-3, 4:-4])
    ys, xs = ys + 3, xs + 4
    if not len(xs):
        return img
    for k in rng.choice(len(xs), min(cfg.get("tufts", 0), len(xs)), replace=False):
        y, x = ys[k], xs[k]
        base = pal["grass"][0 if shadow[y, x] else 1]
        for (dy, dx) in ((0, 0), (0, 2), (-1, 1)) if k % 2 else ((0, 0), (-1, 0), (0, 2), (-1, 3)):
            img[y + dy, x + dx] = base
    for n, k in enumerate(rng.choice(len(xs), min(cfg.get("flowers", 0), len(xs)), replace=False)):
        y, x = ys[k], xs[k]
        if shadow[y, x]:
            continue
        col = pal["cloth"][2] if n % 3 else pal["stone"][1]
        for (dy, dx) in ((0, 0), (1, 2), (-1, 3))[: 1 + n % 3]:
            img[y + dy, x + dx] = col
    return img


# ------------------------------------------------------------------ night grade + optional dither

def night_grade(scene: Scene, layers, base: np.ndarray, dither: str = "off"):
    """Night: each material face maps to a step of the style's night ramp (materials[m]["night"] = {top, lit,
    shade, shadow}), so silhouettes keep their value order; materials without a night entry fall back to their
    lightness. Windows glow and throw flat iso light pools (+1 / +2 steps).
    Dither is an option (off by default): a 1-px checker band only on the pool rims, never inside a flat plane."""
    spec = scene.spec["night"]
    ramp = [hexrgb(c) for c in spec["ramp"]]
    glow = [hexrgb(c) for c in spec["glow"]]
    n = len(ramp)
    lum = base.astype(float) @ np.array([0.30, 0.55, 0.15])
    lo, hi = lum.min(), lum.max()
    q = np.clip(((lum - lo) / max(hi - lo, 1) * (n - 1)).round().astype(int), 0, n - 2)
    mat, tone, shadow = layers["mat"], layers["tone"], layers["shadow"]
    for m in set(mat.ravel()):
        nt = scene.mats.get(m, {}).get("night") if m else None
        if not nt:
            continue
        for cls in ("top", "lit", "shade"):
            sel = (mat == m) & (tone == cls)
            k = nt.get(cls, nt.get("top", 0))
            q[sel & ~shadow] = k
            q[sel & shadow] = nt.get("shadow", max(0, k - 1))
    win = np.zeros(lum.shape, bool)
    for m in spec.get("glow_mats", []):
        win |= layers["decal"] == m
    H, W = lum.shape
    pool = np.zeros(lum.shape, int)
    ys, xs = np.nonzero(win)
    if len(xs):
        YY, XX = np.mgrid[0:H, 0:W]
        r0 = spec.get("pool_r", 10)
        for r, lvl in ((r0, 1), (r0 * 0.5, 2)):
            acc = np.zeros(lum.shape, bool)
            for cx, cy in set(zip((xs // 4) * 4, (ys // 4) * 4)):
                acc |= (np.abs(XX - cx) / 2 + np.abs(YY - (cy + 4))) <= r / 2
            pool = np.maximum(pool, np.where(acc, lvl, 0))
        ground = layers["HZ"] <= scene.spec.get("pool_max_z", 7)
        pool = np.where(ground, pool, np.minimum(pool, 1))
    if dither == "night":
        YY, XX = np.mgrid[0:H, 0:W]
        chk = ((YY + XX // 2) % 2) == 0
        P = np.pad(pool, 1, mode="edge")
        rim_out = pool < np.maximum.reduce([P[:-2, 1:-1], P[2:, 1:-1], P[1:-1, :-2], P[1:-1, 2:]])
        # widen the rim to 2 px outward so the falloff reads, then checker it with the next step
        P2 = np.pad(rim_out, 1)
        rim2 = rim_out | (P2[1:-1, :-2] | P2[1:-1, 2:]) & (pool == 0)
        pool = np.where(rim2 & chk, pool + 1, pool)
    out = np.array(ramp, np.uint8)[np.clip(q + pool, 0, n - 1)]
    out[win] = glow[1]
    return out


# ------------------------------------------------------------------ ambient

def ambient_polys(scene: Scene, frame: int, frames: int) -> List[Poly]:
    """Smoke puffs (small cubes that rise and shrink), whole-pixel steps, seamless over `frames`, plus the scene's
    animated props (one poly list per frame: animals with held key poses)."""
    anim = scene.spec.get("anim")
    out = [Poly.from_json(p) for p in anim[frame % len(anim)]] if anim else []
    for s in scene.spec.get("smoke", []):
        x, y, z = s["at"]
        n = s.get("puffs", 3)
        for i in range(n):
            ph = ((frame / frames) + i / n) % 1.0
            rise = int(ph * s.get("rise", 14))
            size = max(1, int(round(s.get("size", 3) * (1 - ph * 0.6))))
            dx = int(round(ph * s.get("drift", -4)))
            x0, y0, z0 = x + dx, y + dx, z + rise
            out.append(Poly(box_planes(x0, y0, z0, x0 + size, y0 + size, z0 + size),
                            {"*": {"m": s["m"], "tone": "top"}, "top": {"m": s["m"], "tone": "top"}},
                            box_verts(x0, y0, z0, x0 + size, y0 + size, z0 + size), cast=False, tag="smoke"))
    return out


def glints(scene: Scene, img, layers, frame, frames):
    g = scene.spec.get("glints")
    if not g:
        return img
    rng = np.random.RandomState(g.get("seed", 3))
    H, W = layers["mat"].shape
    water = np.isin(layers["mat"], g["on"]) & ~layers["shadow"]
    ys, xs = np.nonzero(water)
    if not len(xs):
        return img
    pick = rng.choice(len(xs), min(g.get("count", 8), len(xs)), replace=False)
    col = hexrgb(scene.spec["palette"][g["ramp"]][g["tone"]])
    for k, p in enumerate(pick):
        on = ((frame + k * 5) % frames) < g.get("on_frames", 4)
        x, y = xs[p] & ~1, ys[p]
        if on and x + 1 < W and water[y, x] and water[y, x + 1]:
            img[y, x:x + 2] = col
    return img


# ------------------------------------------------------------------ frames, sheets, output

def render_frame(scene: Scene, frame=0, frames=1, hour="noon", dither="off", raw=False) -> np.ndarray:
    """One finished frame: render, then the scene's opt-in passes (detail, terrain AA, soft line), then the night
    grade or the water glints."""
    layers = scene.render(ambient_polys(scene, frame, max(frames, 1)))
    img = scene.paint(layers)
    if not raw:
        if scene.spec.get("detail"):
            img = ground_detail(scene, img, layers, scene.spec["detail"])
        if scene.spec.get("terrain_aa"):
            img = iso_line.soft_terrain(img, layers, scene, scene.spec["terrain_aa"])
        if scene.spec.get("line"):
            img, _ = iso_line.soft_line(img, layers, scene, scene.spec["line"])
    if hour == "night":
        return night_grade(scene, layers, img, dither)
    return glints(scene, img, layers, frame, frames) if frames > 1 else img


def save_frames(out_dir, frames: List[np.ndarray], tag: str, ms=120, preview=0) -> str:
    """tag_1x.png (+ tag_1x.gif when animated), plus an integer-scaled tag.png preview when preview > 1."""
    os.makedirs(out_dir, exist_ok=True)
    ims = [Image.fromarray(f) for f in frames]
    ims[0].save(os.path.join(out_dir, tag + "_1x.png"))
    if len(ims) > 1:
        ims[0].save(os.path.join(out_dir, tag + "_1x.gif"), save_all=True, append_images=ims[1:], duration=ms,
                    loop=0, disposal=1)
    if preview > 1:
        ims[0].resize((ims[0].width * preview, ims[0].height * preview), Image.NEAREST).save(
            os.path.join(out_dir, tag + ".png"))
    return os.path.join(out_dir, tag + "_1x.png")


def animal_sheet(base: Dict, pose: Callable[[str, int], List[Dict]], keys: int, fw: int, fh: int, anchor,
                 line: Dict = None, ms=140, name="animal", style="", clip="walk") -> tuple:
    """An 8-direction clip sheet (rows S, SE, E, NE, N, NW, W, SW; `keys` frames each) rendered alone on the
    exact-iso camera. pose(direction, key) returns the animal's polys with its ground centre at the origin. The
    line sits inside the silhouette, so the sprite composites on any ground. Returns (RGBA image, meta)."""
    spec = dict(base, size=[fw, fh], origin=list(anchor), polys=[])
    spec.pop("ground", None)
    scene = Scene(spec)
    rows = ["S", "SE", "E", "NE", "N", "NW", "W", "SW"]
    sheet = Image.new("RGBA", (fw * keys, fh * len(rows)), (0, 0, 0, 0))
    for r, d in enumerate(rows):
        for k in range(keys):
            layers = scene.render([Poly.from_json(p) for p in pose(d, k)])
            img = scene.paint(layers)
            if line:
                img, _ = iso_line.soft_line(img, layers, scene, line)
            alpha = (layers["PID"] >= 0).astype(np.uint8) * 255
            sheet.paste(Image.fromarray(np.dstack([img, alpha]), "RGBA"), (k * fw, r * fh))
    meta = {"name": name, "style": style, "frame_w": fw, "frame_h": fh, "anchor": list(anchor), "directions": rows,
            "clips": {clip: {"loop": True, "frames": [{"ms": ms, "event": None}] * keys}}}
    return sheet, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=int, default=4, help="integer preview scale (the _1x files are exact)")
    ap.add_argument("--frames", type=int, default=1)
    ap.add_argument("--ms", type=int, default=120)
    ap.add_argument("--hour", default="noon", choices=["noon", "night"])
    ap.add_argument("--dither", default="off", choices=["off", "night"], help="optional dither on light-pool rims")
    ap.add_argument("--raw", action="store_true", help="no detail, terrain AA or line (for before/after crops)")
    a = ap.parse_args()
    scene = Scene(json.load(open(a.scene)))
    frames = [render_frame(scene, f, a.frames, a.hour, a.dither, a.raw) for f in range(a.frames)]
    tag = "raw" if a.raw else a.hour + ("_dither" if a.dither != "off" else "")
    print(save_frames(a.out, frames, tag, a.ms, a.scale))


if __name__ == "__main__":
    main()
