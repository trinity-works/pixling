"""Hour lighting: one painted map, every hour of the day, without repainting anything.

  python3 -m pp light specs/vista/highgate.map.json                     # day, golden, sunset, dusk, night
  python3 -m pp light specs/vista/highgate.map.json --hours 2.6,3.4 --gif # + a day -> night loop

Every pixel moves to its hour through one grade per level (0 day, 1 golden hour, 2 sunset, 3 dusk, 4 night,
5 deep night). The level is the hour plus a slow spatial offset, so dusk does not fall everywhere at once: it
sweeps up the picture, and the seam between two levels is an ordered dither, never a soft blend (colours stay
flat). After sundown the map answers: a few panes of every building light up (each building at its own hour),
lamps and lighthouses glow and throw stepped pools of warm light (grades 6/7), and water does not take the
lamplight's tint, it reflects it as a broken streak below each lamp.

What lights up comes from the map itself (the meaning layer and the object sprites), never from a list typed per
map: window pixels are the style's window material inside each object's body; light sources are objects whose
build name contains "lamp", "torch", "lantern" or "lighthouse". A map spec can add or tune it:
  "light": {"windows": 2,                       panes per building that light up
            "sources": {"st_lamp": {"r": [2, 6]}, "lighthouse": {"r": [4, 10], "reflect": 22}},
            "points": [{"at": [x, y], "r": [3, 8]}],   extra light sources (a campfire painted into the ground)
            "offset": [0.36, 0.1]}              how far dusk leads at the bottom / the right edge (levels)

Writes <out>/light/<map>_h<level>.png per hour, a strip, and light.json for an engine that lights at runtime:
the grade of every colour in the map at every level, the window panes (with the level each building lights at)
and the light sources with their pool radii.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from .variants import keyed

GLOW = ["#f5d890", "#e0a050", "#8a4a2a"]          # firelight: core, rim, ember (the style's glow_fire ramp)
SOURCE_WORDS = ("lamp", "torch", "lantern", "lighthouse")
BAYER4 = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16
LEVELS = {"day": 0.0, "golden": 1.2, "sunset": 2.2, "dusk": 3.1, "night": 4.0}


def _mix(c, tint, t):
    return c * (1 - t) + np.asarray(tint, float) * t


def grade(rgb: np.ndarray, k: int) -> np.ndarray:
    """rgb (n, 3) float -> graded (n, 3) at level k (the Lamplighter's grades)."""
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    s = lambda *a: np.stack(a, 1)
    if k == 0:
        out = rgb
    elif k == 1:
        out = s(np.minimum(255, r * 1.06 + 12), g * 0.98 + 4, b * 0.86)
    elif k == 2:
        out = _mix(s(r * 0.95 + 10, g * 0.8, b * 0.78 + 10), [122, 70, 82], 0.18)
    elif k == 3:
        out = _mix(s(r * 0.7, g * 0.7, b * 0.7), [58, 58, 92], 0.42)
    elif k == 4:
        out = _mix(s(r * 0.5, g * 0.5, b * 0.5), [24, 38, 60], 0.55)
    elif k == 5:
        out = _mix(s(r * 0.38, g * 0.38, b * 0.38), [16, 26, 42], 0.66)
    elif k == 6:                                   # lamplight, inner pool
        out = _mix(s(r * 0.9 + 20, g * 0.8 + 8, b * 0.5), [168, 112, 52], 0.22)
    elif k == 7:                                   # lamplight, outer pool
        out = _mix(s(r * 0.6 + 6, g * 0.52 + 2, b * 0.42), [96, 70, 40], 0.34)
    else:
        raise ValueError(k)
    return np.clip(np.round(out), 0, 255)


def _hex(c) -> np.ndarray:
    c = c.lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], np.uint8)


class Lighting:
    """Everything that lights up in a map: window panes per building and light sources."""

    def __init__(self, spec: Dict, meaning, style, sprites):
        cfg = spec.get("light") or {}
        self.W, self.H = spec["size"]
        self.offset = cfg.get("offset", [0.36, 0.1])
        win_cols = []
        mat = style.spec["materials"].get("window")
        if mat:
            ramp = style.spec["ramps"][mat["ramp"]]
            win_cols = [_hex(ramp[i]) for i in mat.get("shades", range(len(ramp)))]
        self.panes: List[Tuple[int, int, float]] = []          # x, y, level at which this building lights up
        self.sources: List[Dict] = []
        n_win = int(cfg.get("windows", 2))
        tune = cfg.get("sources", {})
        for ob, rec in zip(spec.get("objects", []), meaning.objects):
            spr = sprites(ob["build"])
            img = spr.frame(ob.get("clip", "idle"), ob.get("dir", "S"), 0)
            ax, ay = spr.anchor
            if ob.get("flip"):
                img = img[:, ::-1]; ax = img.shape[1] - 1 - ax
            X0, Y0 = int(ob["at"][0]) - ax, int(ob["at"][1]) - ay
            name = ob["build"]
            src = next((v for k, v in tune.items() if k in name), None)
            if src is not None or any(w in name for w in SOURCE_WORDS):
                src = dict(src or {})
                box = rec.get("box")
                if box:
                    top = box[1] + 1
                    self.sources.append({"at": [int(ob["at"][0]) + int(src.get("dx", 0)), top + int(src.get("dy", 0))],
                                         "feet": [int(ob["at"][0]), int(ob["at"][1])], "r": src.get("r", [3, 8]),
                                         "reflect": int(src.get("reflect", 24)), "build": name})
                continue
            if not win_cols or n_win <= 0:
                continue
            body = img[..., 3] > 0
            hit = np.zeros(body.shape, bool)
            for c in win_cols:
                hit |= body & np.all(img[..., :3] == c, axis=-1)
            ys, xs = np.nonzero(hit)
            if not len(xs):
                continue
            order = np.lexsort((ys, xs))
            pts = list(zip(xs[order] + X0, ys[order] + Y0))
            at = 2.7 + 0.8 * keyed(spec.get("name", ""), "lit", rec["id"])      # each building at its own hour
            for f in np.linspace(0.2, 0.8, n_win) if n_win > 1 else [0.5]:
                x, y = pts[int(f * (len(pts) - 1))]
                if 0 <= x < self.W and 0 <= y < self.H:
                    self.panes.append((int(x), int(y), round(float(at), 3)))
        for p in cfg.get("points", []):
            self.sources.append({"at": [int(v) for v in p["at"]], "feet": [int(v) for v in p["at"]], "r": p.get("r", [3, 8]),
                                 "reflect": int(p.get("reflect", 10)), "build": None})

    def levels(self, A: float) -> np.ndarray:
        ys, xs = np.mgrid[0:self.H, 0:self.W].astype(np.float32)
        oy, ox = self.offset
        lv = A + (ys / self.H - 0.5) * oy + (xs / self.W - 0.5) * ox
        return np.clip(lv, 0, 5)

    def render(self, img: np.ndarray, water_depth: np.ndarray, A: float) -> np.ndarray:
        H, W = self.H, self.W
        rgb = img[..., :3].copy()
        ys, xs = np.mgrid[0:H, 0:W]
        bay = BAYER4[ys % 4, xs % 4]
        lv = self.levels(A)
        f = lv - np.floor(lv)
        sharp = np.clip((f - 0.5) * 40 + 0.5, 0, 1)
        K = np.minimum(5, np.floor(lv).astype(np.int32) + (bay < sharp))
        emis = np.zeros((H, W), bool)
        pool = np.zeros((H, W), np.uint8)
        glow = [_hex(c) for c in GLOW]
        water = water_depth > 0
        night = A > 2.6
        if night:
            for x, y, at in self.panes:
                if A >= at:
                    rgb[y, x] = glow[0]; emis[y, x] = True
            for s in self.sources:
                (x, y), (r1, r2) = s["at"], s["r"]
                if 0 <= x < W and 0 <= y < H:
                    rgb[y, x] = glow[0]; emis[y, x] = True
                    if y + 1 < H:
                        rgb[y + 1, x] = glow[1]; emis[y + 1, x] = True
                fx, fy = s["feet"]
                # the pool lies on the ground at the lamp's feet: a flat ellipse, stepped, with a dithered edge
                d = np.hypot(xs - fx, (ys - fy) * 1.8) + bay * 1.6 - 0.8
                pool[d < r2] = np.maximum(pool[d < r2], 1)
                pool[d < r1] = 2
                # the water reflects it: a broken streak straight down from where the water starts below the lamp
                y0 = next((yy for yy in range(fy, min(H, fy + s["reflect"])) if water_depth[yy, fx] > 0), None)
                if y0 is not None:
                    n = s["reflect"]
                    for dd in range(1, n):
                        yy = y0 + dd
                        if yy >= H:
                            break
                        xx = fx + int(round(np.sin(dd * 0.9 + fx) * (dd / n) * 1.5))
                        if 0 <= xx < W and water_depth[yy, xx] >= 1 and ((dd + xx) & 1) and keyed(fx, fy, dd) > dd / n * 0.75:
                            rgb[yy, xx] = glow[0] if dd < n * 0.35 else glow[1]
                            emis[yy, xx] = True
        lamp = (K >= 3) & ~water
        K = np.where(lamp & (pool == 2), 6, np.where(lamp & (pool == 1), 7, K))
        # grade through a table of the colours actually present
        flat = rgb.reshape(-1, 3)
        cols, inv = np.unique(flat, axis=0, return_inverse=True)
        inv = inv.reshape(-1)
        out = np.empty_like(flat)
        Kf = K.reshape(-1)
        for k in np.unique(Kf):
            sel = Kf == k
            g = grade(cols.astype(float), int(k)).astype(np.uint8)
            out[sel] = g[inv[sel]]
        out = out.reshape(H, W, 3)
        out[emis] = rgb[emis]
        res = img.copy()
        res[..., :3] = out
        return res

    def export(self, img: np.ndarray) -> Dict:
        cols = np.unique(img[..., :3].reshape(-1, 3), axis=0)
        hx = lambda c: "#%02x%02x%02x" % tuple(int(v) for v in c)
        lut = {hx(c): [hx(grade(c[None].astype(float), k)[0]) for k in range(8)] for c in cols}
        return {"version": 1, "levels": {"0": "day", "1": "golden", "2": "sunset", "3": "dusk", "4": "night", "5": "deep night",
                                         "6": "lamplight inner", "7": "lamplight outer"},
                "level_offset": {"bottom": self.offset[0], "right": self.offset[1], "seam": "ordered dither (4x4 Bayer), sharpness 40"},
                "glow": GLOW, "grades": lut,
                "panes": [{"at": [x, y], "lights_at": at} for x, y, at in self.panes], "sources": self.sources}


def run(spec_path: str, hours: List[float], out: Path = None, builds: Path = None, gif: bool = False, scale: int = 2) -> Path:
    from .forge import OUT, load_style
    from .io import save_gif, save_png
    from .map import Sprite, compose
    from .meaning import Meaning
    spec = json.loads(Path(spec_path).read_text())
    builds = Path(builds or spec.get("builds", OUT))
    out = Path(out or OUT / spec["name"]) / "light"
    out.mkdir(parents=True, exist_ok=True)
    W, H = spec["size"]
    mean = Meaning(W, H, spec)
    img = compose(spec, builds, 1, meaning=mean)[0]
    _, wd = mean.arrays()
    cache = {}
    sprites = lambda n: cache.setdefault(n, Sprite(builds / n))
    L = Lighting(spec, mean, load_style(spec["style"]), sprites)
    shots = []
    for A in hours:
        im = L.render(img, wd, A)
        save_png(im, out / f"{spec['name']}_h{A:g}.png")
        shots.append(im)
    gap = np.zeros((H, 4, 4), np.uint8)
    strip = np.concatenate(sum([[s, gap] for s in shots], [])[:-1], 1)
    save_png(strip, out / f"{spec['name']}_hours.png", scale=scale)
    if gif:
        seq = list(np.linspace(0, 4.1, 42)) + [4.1] * 8 + list(np.linspace(4.1, 0, 20))
        save_gif([L.render(img, wd, A) for A in seq], [90] * len(seq), out / f"{spec['name']}_day.gif", scale=scale)
    (out / "light.json").write_text(json.dumps(L.export(img), indent=1))
    return out
