"""Looking aids for the arena: the palette strip, the zone/grey/squint views, the scale sheet.

    python3 -m arena palette [--out FILE]    the palette by role, each colour as every zone renders it
    python3 -m arena zones [--out DIR]       zone map, greyscale, squint of art/map.png
    python3 -m arena scale [--out FILE]      the map with the 1 m grid, people at 1.7 m and the key dimensions
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import place as P
from . import zones as Z
from . import palette as C
from .palette import rgb

INK = (20, 26, 48)
TXT = (228, 182, 164)
DIM = (150, 160, 170)


def font(size):
    for name in ("DejaVuSans.ttf", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def palette_strip(out: Path, art: Path | None = None) -> Path:
    """every colour by role (swatch, key, luma), then the map's own value structure: each zone's colours as it
    renders them, sorted by value; and the hue bands kept free for units"""
    sw, gap, lab = 50, 6, 250
    f, fs = font(14), font(11)
    from .maps import active
    M = active()
    GROUPS = M.biome.GROUPS
    rows = len(GROUPS)
    zrows = [n for n in Z.ZONES if n != "focus"]
    Wd = lab + 12 * (sw + gap) + 30
    Hh = 60 + rows * (sw + 34) + 50 + len(zrows) * 30 + 140
    im = Image.new("RGB", (Wd, Hh), INK)
    d = ImageDraw.Draw(im)
    d.text((16, 14), f"{M.TITLE}: the palette by role (luma under each swatch)", fill=TXT, font=font(17))
    y = 52
    for name, keys in GROUPS:
        d.text((16, y + 14), name, fill=DIM, font=f)
        for i, k in enumerate(keys):
            x = lab + i * (sw + gap)
            c = rgb(C.PAL[k])
            d.rectangle([x, y, x + sw - 1, y + sw - 1], fill=c)
            d.text((x, y + sw + 2), k[:8], fill=DIM, font=fs)
            d.text((x, y + sw + 14), f"{Z.luma(np.array(c)):.2f}", fill=DIM, font=fs)
        y += sw + 34
    # the value structure the map actually shows: every zone's pixels, sorted by luma (a vertical slice each)
    y += 14
    d.text((16, y), "the map's value structure: each zone's pixels sorted dark -> light (from art/map.png)", fill=TXT, font=f)
    y += 24
    if art is not None and (Path(art) / "map.png").exists():
        img = np.asarray(Image.open(Path(art) / "map.png").convert("RGB"))
        zm = np.asarray(Image.open(Path(art) / "zones.png"))
        bw = 12 * (sw + gap) - gap
        for n in zrows:
            px = img[zm == Z.CODE[n]]
            if len(px) == 0:
                continue
            order = np.argsort(Z.luma(px))
            pick = px[order][np.linspace(0, len(px) - 1, bw).astype(int)]
            band = np.repeat(pick[None], 22, 0).astype(np.uint8)
            im.paste(Image.fromarray(band), (lab, y))
            m = Z.measure(img, zm)[n]
            d.text((16, y + 3), f"{n:10s} {m['share']:5.1%}  luma {m['lo']:.2f}-{m['hi']:.2f}", fill=DIM, font=fs)
            y += 30
    y += 10
    d.text((16, y), "hues kept free for units (no pixel of the map shows them above chroma 0.2):", fill=TXT, font=f)
    y += 24
    for i, (name, (lo, hi)) in enumerate(C.UNIT_HUES.items()):
        x = lab + i * 4 * (sw + gap)
        for j, h in enumerate(np.linspace(lo, hi, 4)):
            import colorsys
            r, g, b = colorsys.hsv_to_rgb(h / 360, 0.72, 0.9)
            d.rectangle([x + j * (sw + gap), y, x + j * (sw + gap) + sw - 1, y + sw - 1], fill=(int(r * 255), int(g * 255), int(b * 255)))
        d.text((x, y + sw + 4), f"{name} {lo}-{hi} deg", fill=DIM, font=fs)
    d.text((16, y + 8), "units:", fill=DIM, font=f)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def looks(src: Path, zones_png: Path, odir: Path, name: str) -> None:
    """NAME_zones.png (each zone tinted over grey), NAME_grey.png, NAME_squint.png (blurred grey: the big shapes)"""
    odir.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    zm = np.asarray(Image.open(zones_png))
    if zm.shape == (im.height, im.width):
        Image.fromarray(Z.tint(np.asarray(im), zm)).save(odir / f"{name}_zones.png")
    im.convert("L").save(odir / f"{name}_grey.png")
    im.filter(ImageFilter.GaussianBlur(14)).convert("L").save(odir / f"{name}_squint.png")


def person(d: ImageDraw.ImageDraw, x: float, y: float, h_px: float, col=(240, 236, 220), edge=(20, 26, 48)):
    """a neutral 1.7 m figure standing with its feet at (x, y): head, body, legs; h_px = its height on screen"""
    s = h_px / 1.7
    hw = 0.22 * s
    d.ellipse([x - 0.32 * s, y - 0.12 * s, x + 0.32 * s, y + 0.12 * s], fill=(0, 0, 0))
    d.rectangle([x - hw, y - 0.95 * s, x + hw, y - 0.05 * s], fill=col, outline=edge)
    d.rectangle([x - 0.25 * s, y - 1.48 * s, x + 0.25 * s, y - 0.9 * s], fill=col, outline=edge)
    d.ellipse([x - 0.12 * s, y - 1.7 * s, x + 0.12 * s, y - 1.45 * s], fill=col, outline=edge)


def dim_line_maker(d):
    f = font(15)

    def dim_line(a, b, text, off=(0, 0)):
        d.line([a, b], fill=(250, 220, 160), width=2)
        for q in (a, b):
            d.ellipse([q[0] - 3, q[1] - 3, q[0] + 3, q[1] + 3], fill=(250, 220, 160))
        mx, my = (a[0] + b[0]) / 2 + off[0], (a[1] + b[1]) / 2 + off[1]
        tw = d.textlength(text, font=f)
        d.rectangle([mx - tw / 2 - 4, my - 10, mx + tw / 2 + 4, my + 10], fill=(20, 26, 48))
        d.text((mx - tw / 2, my - 8), text, fill=(250, 220, 160), font=f)
    return dim_line


def scale_sheet(art: Path, out: Path) -> Path:
    """the map under a 1 m grid on the ground (every 5th line stronger), people at 1.7 m standing on every level, the
    key dimensions measured on it"""
    art = Path(art)
    img = Image.open(art / "map.png").convert("RGB")
    lv = json.loads((art / "level.json").read_text())
    g = lv["grid"]
    nv, nu, c = g["nv"], g["nu"], g["cell"]
    kind = np.array([[int(ch) for ch in row] for row in g["kind"]])
    hz = np.array(g["height_cm"], float) / 100.0
    dim = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(dim)
    # the metre grid on the walkable ground: each cell's edges at its own height
    for i in range(nv):
        for j in range(nu):
            if kind[i, j] == 0:
                continue
            u = g["u0"] + j * c; v = g["v0"] + i * c
            z = hz[i, j]
            if abs(u - round(u)) < 1e-6:
                strong = round(u) % 5 == 0
                a = P.proj(u, v, z); b = P.proj(u, v + c, z)
                d.line([a, b], fill=(255, 255, 255, 120 if strong else 46), width=1)
            if abs(v - round(v)) < 1e-6:
                strong = round(v) % 5 == 0
                a = P.proj(u, v, z); b = P.proj(u + c, v, z)
                d.line([a, b], fill=(255, 255, 255, 120 if strong else 46), width=1)
    out_im = Image.alpha_composite(img.convert("RGBA"), dim)
    d = ImageDraw.Draw(out_im)
    hp = P.HUMAN * P.CE * P.PPM
    zof = lambda u, v: float(P.terrain(np.array(u), np.array(v)))
    from .maps import active
    note = active().biome.scale_marks(d, person, dim_line_maker(d), hp, zof)
    # the legend
    lines = [f"1 m grid on the walkable ground (every 5 m stronger); 1 m = {P.PPM:.0f} px across, "
             f"{P.PPM * P.SE:.1f} px into the picture, {P.PPM * P.CE:.1f} px up",
             f"people are {P.HUMAN} m ({hp:.0f} px tall on screen){note}"] + \
            [f"{k}: {v}" for k, v in P.DIMENSIONS.items()]
    bx, by = 18, 18
    wmax = max(d.textlength(t, font=font(13)) for t in lines)
    d.rectangle([bx - 8, by - 6, bx + wmax + 10, by + 17 * len(lines) + 6], fill=(20, 26, 48, 230))
    for i, t in enumerate(lines):
        d.text((bx, by + i * 17), t, fill=(228, 182, 164) if i < 2 else (200, 205, 210), font=font(13))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out_im.convert("RGB").save(out)
    return out


def family(out: Path, names=None, crop=None) -> Path:
    """every map's painted picture side by side at the same scale (1 m = 32 px across on all of them), each with a
    1.7 m person standing on its fighting ground and its palette in a strip: is it one style family?"""
    from . import maps
    was = maps.active().KEY
    names = names or maps.names()
    tiles = []
    for n in names:
        M = maps.activate(n)
        if not (M.ART / "map.png").exists():
            continue
        im = Image.open(M.ART / "map.png").convert("RGB")
        if crop:
            im = im.crop(crop)
        d = ImageDraw.Draw(im)
        L = json.loads((M.ART / "level.json").read_text())
        sp = L["zones"]["spawns"]["west"]["origin"]
        u, v = sp[0] + 4.0, sp[1]
        x, y = P.proj(u, v, float(P.terrain(np.array(u), np.array(v))))
        if crop:
            x, y = x - crop[0], y - crop[1]
        person(d, x, y, P.HUMAN * P.CE * P.PPM)
        strip = Image.new("RGB", (im.width, 46), INK)
        sd = ImageDraw.Draw(strip)
        keys = list(C.PAL)
        w = im.width / len(keys)
        for i, k in enumerate(keys):
            sd.rectangle([int(i * w), 0, int((i + 1) * w), 45], fill=rgb(C.PAL[k]))
        t = Image.new("RGB", (im.width, im.height + 46 + 34), INK)
        t.paste(im, (0, 34)); t.paste(strip, (0, 34 + im.height))
        ImageDraw.Draw(t).text((12, 6), f"{M.TITLE}: {P.EL_DEG:.0f} deg, 1 m = {P.PPM:.0f} px across, a 1.7 m person "
                                         f"{P.HUMAN * P.CE * P.PPM:.0f} px tall", fill=TXT, font=font(18))
        tiles.append(t)
    maps.activate(was)
    W = sum(t.width for t in tiles) + 16 * (len(tiles) - 1)
    sheet = Image.new("RGB", (W, max(t.height for t in tiles)), INK)
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0)); x += t.width + 16
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
