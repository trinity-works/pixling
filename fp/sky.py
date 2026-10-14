"""The painted sky: one panorama at art-pixel size, painted in Python and drawn behind the world as its own layer.

Clouds are cumulus clumps built from overlapping round puffs, back to front: a lower puff overlaps the one above
it, so each clump reads as a cauliflower of scalloped, lit tops over rose bellies. Every puff is shaded in a few
bands (light from above, a touch from the sun side) with an ordered dither between them, which is what gives the
reference its soft painterly look while every pixel stays a palette colour. Then the hot-pink clusters near the
sun, their stray specks, the ridges with a pink rim on the sun side, and the glow line under the sun.

The panorama is equirectangular: x is azimuth (-180..180 degrees, 0 = straight ahead at the start, + toward +x),
y is elevation (sky.el_max at the top row down to sky.el_min). One pixel is `sky.px_deg` degrees, the size of a
splat texel, so sky pixels and world pixels match.
"""
from __future__ import annotations

import math

import numpy as np

BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16.0 + 1 / 32


def _hex(h):
    return np.array([int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)], np.uint8)


def _noise1(x, seed, octaves=4):
    """smooth 1D value noise in -1..1, periodic over x in [0, 1)."""
    rng = np.random.default_rng(seed)
    out = np.zeros_like(x, dtype=np.float64)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        n = 6 * 2 ** o
        v = rng.uniform(-1, 1, n)
        t = (x % 1.0) * n
        i = np.floor(t).astype(int)
        f = t - i
        f = f * f * (3 - 2 * f)
        out += amp * (v[i % n] * (1 - f) + v[(i + 1) % n] * f)
        tot += amp
        amp *= 0.5
    return out / tot


class Canvas:
    def __init__(self, st):
        sk = st["sky"]
        self.px = float(sk.get("px_deg", 0.225))
        self.el_min, self.el_max = float(sk.get("el_min", -12)), float(sk.get("el_max", 78))
        self.W = int(round(360 / self.px))
        self.H = int(round((self.el_max - self.el_min) / self.px))
        self.img = np.zeros((self.H, self.W, 3), np.uint8)
        ys, xs = np.mgrid[0:self.H, 0:self.W]
        self.az = xs * self.px - 180 + self.px / 2                 # degrees
        self.el = self.el_max - (ys + 0.5) * self.px
        self.dither = BAYER[ys % 4, xs % 4]                        # 0..1, pinned to the sky's own pixels

    def x_of(self, az):
        return (az + 180) / self.px

    def y_of(self, el):
        return (self.el_max - el) / self.px


def _gradient(c, stops):
    e = np.sin(np.radians(c.el)) + (c.dither - 0.5) * 0.018      # dithered band borders
    out = np.zeros_like(c.img)
    out[:] = _hex(stops[0][1])
    for pos, h in stops:
        out[e >= pos] = _hex(h)
    c.img[:] = out


def _puff(c, az, el, r, tones, light_az, warm, mask=None):
    """one round puff of radius r degrees, banded top -> body -> belly with a dithered seam."""
    cosl = max(math.cos(math.radians(el)), 0.2)
    rx, ry = r / cosl / c.px, r / c.px                             # keep it round on the sky, not in the panorama
    cx, cy = c.x_of(az), c.y_of(el)
    x0, x1 = int(math.floor(cx - rx)) - 1, int(math.ceil(cx + rx)) + 1
    y0, y1 = max(int(math.floor(cy - ry)) - 1, 0), min(int(math.ceil(cy + ry)) + 1, c.H)
    if y1 <= y0:
        return
    xs = np.arange(x0, x1)
    ys = np.arange(y0, y1)
    X, Y = np.meshgrid(xs, ys)
    u = (X + 0.5 - cx) / rx
    v = (cy - (Y + 0.5)) / ry                                       # +1 at the top
    d2 = u * u + v * v
    inside = d2 <= 1.0
    if mask is not None:
        inside &= mask(Y)
    if not inside.any():
        return
    Xw = X % c.W
    dith = c.dither[Y, Xw]
    side = math.sin(math.radians(light_az - az))                    # the sun side of the puff catches a little more
    light = 0.80 * v + 0.25 * (-u * np.sign(side) * min(abs(side) * 2, 1)) + warm + (dith - 0.5) * 0.32
    k = np.where(light > 0.32, 0, np.where(light > -0.30, 1, np.where(light > -0.78, 2, 3)))
    k = np.minimum(k, len(tones) - 1)
    pal = np.stack([_hex(t) for t in tones])
    Ys, Xs = Y[inside], Xw[inside]
    c.img[Ys, Xs] = pal[k[inside]]


def _clump(c, rng, az, el_base, width, height, tones, light_az, warm):
    """a cumulus: a dome of puffs over a flat-ish base, painted back to front (top puffs first, low ones over them)."""
    n = max(4, int(width * height / 7))
    puffs = []
    for _ in range(n):
        t = rng.uniform(-1, 1)
        dome = (1 - t * t) ** 0.6
        r = height * rng.uniform(0.32, 0.6) * (0.55 + 0.45 * dome)
        x = az + t * width / 2
        y = el_base + r * 0.55 + dome * height * rng.uniform(0.15, 0.75)
        puffs.append((y, x, r))
    # small fringe puffs along the base so the bottom edge is soft and scalloped, not ruled
    for _ in range(int(width / 3)):
        t = rng.uniform(-0.95, 0.95)
        r = height * rng.uniform(0.18, 0.3)
        puffs.append((el_base + r * 0.4, az + t * width / 2, r))
    base_y = c.y_of(el_base - height * 0.12)
    mask = lambda Y: Y <= base_y                                   # a flattened belly
    for y, x, r in sorted(puffs, reverse=True):                    # highest first, lowest painted over them
        _puff(c, x, y, r, tones, light_az, warm, mask)


def _ridges(c, ridges, sun_az):
    for i, r in enumerate(ridges):
        x01 = (c.az[0] + 180) / 360
        e = r["height"] + r["rough"] * _noise1(x01 * r["freq"] / 3 + i * 0.37, r["seed"]) \
            + r["rough"] * 0.35 * _noise1(x01 * r["freq"] * 1.7, r["seed"] + 11)
        h_el = np.degrees(np.arcsin(np.clip(e, -1, 1)))             # ridge top elevation per column
        below = c.el <= h_el[None, :]
        c.img[below] = _hex(r["color"])
        # a one-pixel rim on the sun side, two pixels right under the sun
        sunside = np.cos(np.radians(c.az[0] - sun_az))
        rim_px = np.where(sunside > 0.75, 2, np.where(sunside > 0.25, 1, 0))
        top_row = np.clip(np.round(c.y_of(h_el) - 0.5).astype(int), 0, c.H - 1)
        for k in (0, 1):
            cols = np.nonzero(rim_px > k)[0]
            rows = np.clip(top_row[cols] + k, 0, c.H - 1)
            c.img[rows, cols] = _hex(r["rim"])


def paint(st) -> tuple:
    """-> (H x W x 3 uint8 panorama, meta for the runtime)."""
    sk = st["sky"]
    c = Canvas(st)
    rng = np.random.default_rng(int(sk.get("seed", 5)))
    sun_az = float(st["sun"]["azimuth"])
    _gradient(c, sk["stops"])

    cl = sk["cumulus"]
    # high, small, cool clumps first (far), then the bank low over the horizon (near), warmest at the bottom
    for layer in cl["layers"]:
        for _ in range(int(layer["count"])):
            az = rng.uniform(-180, 180)
            bias = layer.get("sun_bias", 0.0)                       # denser toward the sun
            if rng.random() > (1 - bias) + bias * (0.5 + 0.5 * math.cos(math.radians(az - sun_az))):
                continue
            el = rng.uniform(*layer["el"])
            w = rng.uniform(*layer["width"])
            h = rng.uniform(*layer["height"])
            _clump(c, rng, az, el, w, h, layer["tones"], sun_az, layer.get("warm", 0.0))

    ac = sk["accent"]
    for i in range(int(ac.get("clumps", 3))):
        az = ac["azimuth"] + rng.uniform(-1, 1) * ac.get("spread_deg", 14)
        el = ac["elevation_deg"] + rng.uniform(-1, 1) * ac.get("rise_deg", 6)
        _clump(c, rng, az, el, rng.uniform(*ac["width"]), rng.uniform(*ac["height"]), ac["tones"], sun_az, 0.15)
    # specks drifting off the clusters: single pixels and a few 2x2, thinning with distance
    pink = _hex(ac["tones"][0])
    for _ in range(int(ac.get("specks", 260))):
        r = abs(rng.normal(0, ac.get("speck_spread", 16)))
        a = rng.uniform(0, 2 * math.pi)
        az = ac["azimuth"] + math.cos(a) * r * 1.4
        el = ac["elevation_deg"] + math.sin(a) * r * 0.8
        x, y = int(c.x_of(az)) % c.W, int(c.y_of(el))
        if 0 <= y < c.H - 1 and el > 3:
            s = 2 if rng.random() < 0.18 else 1
            c.img[y:y + s, x:x + s] = pink

    _ridges(c, sk["ridges"], sun_az)
    g = sk.get("sun_glow")
    if g:
        near = np.cos(np.radians(c.az - sun_az))
        line = (np.abs(c.el - 0.15) < g.get("px", 1.2) * c.px * np.clip(near, 0, 1) * 1.6) & (near > 0.4)
        c.img[line] = _hex(g["color"])
    meta = {"el_min": c.el_min, "el_max": c.el_max, "px_deg": c.px, "w": c.W, "h": c.H, "drift": sk.get("drift", 0.25)}
    return c.img, meta


def save(st, path) -> dict:
    from PIL import Image
    img, meta = paint(st)
    Image.fromarray(img).save(path, optimize=True)
    return meta
