"""Scene preview: sprites standing on the style's ground, side by side, at game scale.

Pixel artists design *in the scene* and keep zooming out to game size;
this is that view. Feet anchors sit on one baseline so relative sizes are honest.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

from .color import hex_to_rgb
from .forge import load_style


def ground(style, w: int, h: int, seed: int = 0) -> np.ndarray:
    ramp = style.ramps.get("ground") or [hex_to_rgb(style.spec.get("bg", "#3a3e4a"))]
    rng = np.random.default_rng(seed)
    base = np.zeros((h, w, 4), np.uint8)
    base[..., :3] = ramp[len(ramp) // 2]
    base[..., 3] = 255
    # clustered patches (never single-pixel noise): short horizontal dashes + tufts
    for _ in range(w * h // 60):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        L = int(rng.integers(2, 5))
        c = ramp[0] if rng.random() < 0.5 else ramp[-1]
        base[y, x:x + L, :3] = c
        if rng.random() < 0.3 and y > 0 and x + L // 2 < w:
            base[y - 1, x + L // 2, :3] = c
    return base


def compose(build_dirs: List[str], style_name: Optional[str] = None, clip: str = "idle", direction: str = "S",
            gap: int = 6, scale: int = 4, out=None, frame: int = 0) -> Path:
    sprites = []
    style = None
    for d in build_dirs:
        d = Path(d)
        meta = json.loads((d / (d.name + ".json")).read_text())
        style = style or load_style(style_name or meta["style"])
        c = meta["clips"].get(clip) or next(iter(meta["clips"].values()))
        sheet = np.array(Image.open(d / c["sheet"]).convert("RGBA"))
        dirs = meta["directions"]
        r = dirs.index(direction) if direction in dirs else 0
        fw, fh = meta["frame_w"], meta["frame_h"]
        f = min(frame, sheet.shape[1] // fw - 1)
        img = sheet[r * fh:(r + 1) * fh, f * fw:(f + 1) * fw]
        ys, xs = np.nonzero(img[..., 3])
        x0, x1 = xs.min(), xs.max() + 1
        sprites.append((img[:, x0:x1], meta["anchor"][1], x0))
    above = max(a for _, a, _ in sprites)
    below = max(s.shape[0] - a for s, a, _ in sprites)
    W = sum(s.shape[1] for s, _, _ in sprites) + gap * (len(sprites) + 1)
    H = above + below + 10
    canvas = ground(style, W, H)
    x = gap
    base_y = above + 4
    for s, a, _ in sprites:
        y = base_y - a
        region = canvas[y:y + s.shape[0], x:x + s.shape[1]]
        m = s[..., 3] > 0
        region[m] = s[m]
        x += s.shape[1] + gap
    out = Path(out or "out/scene.png")
    Image.fromarray(canvas).resize((W * scale, H * scale), Image.NEAREST).save(out)
    return out


def silhouettes(build_dirs: List[str], direction: str = "S", scale: int = 4, out=None) -> Path:
    """Top row: sprites in colour. Bottom row: the same, filled solid off-white (the
    lock-alpha silhouette test). Dark background, feet on one baseline."""
    sprites = []
    for d in build_dirs:
        d = Path(d)
        meta = json.loads((d / (d.name + ".json")).read_text())
        c = meta["clips"].get("idle") or next(iter(meta["clips"].values()))
        sheet = np.array(Image.open(d / c["sheet"]).convert("RGBA"))
        r = meta["directions"].index(direction) if direction in meta["directions"] else 0
        fw, fh = meta["frame_w"], meta["frame_h"]
        img = sheet[r * fh:(r + 1) * fh, 0:fw]
        ys, xs = np.nonzero(img[..., 3])
        sprites.append((img[:, xs.min():xs.max() + 1], meta["anchor"][1]))
    above = max(a for _, a in sprites)
    below = max(s.shape[0] - a for s, a in sprites)
    gap = 6
    W = sum(s.shape[1] for s, _ in sprites) + gap * (len(sprites) + 1)
    rowh = above + below + 4
    canvas = np.zeros((rowh * 2, W, 4), np.uint8)
    canvas[..., :3] = (20, 22, 28)
    canvas[..., 3] = 255
    x = gap
    for s, a in sprites:
        m = s[..., 3] > 0
        for row in (0, 1):
            y = row * rowh + 2 + above - a
            reg = canvas[y:y + s.shape[0], x:x + s.shape[1]]
            if row == 0:
                reg[m] = s[m]
            else:
                reg[m] = (235, 237, 233, 255)
        x += s.shape[1] + gap
    out = Path(out or "out/silhouettes.png")
    Image.fromarray(canvas).resize((W * scale, rowh * 2 * scale), Image.NEAREST).save(out)
    return out


def sizes(build_dirs: List[str], scale: int = 4, out=None) -> Path:
    """Size lineup: idle S frame 0 of each build on the style ground, feet on one baseline, sorted by measured
    height, with the size-class heights ruled across (pp/size.py SIZES + style overrides) and each sprite
    labelled with its class and measured px."""
    from PIL import ImageDraw
    from .size import SIZES, class_of
    items = []
    style = None
    for d in build_dirs:
        d = Path(d)
        meta = json.loads((d / (d.name + ".json")).read_text())
        st = load_style(meta["style"])
        style = style or st
        c = meta["clips"].get("idle") or next(iter(meta["clips"].values()))
        sheet = np.array(Image.open(d / c["sheet"]).convert("RGBA"))
        fw, fh = meta["frame_w"], meta["frame_h"]
        img = sheet[:fh, :fw]
        ys, xs = np.nonzero(img[..., 3])
        h = meta.get("height_px") or int(meta["anchor"][1] - ys.min())
        items.append((h, img[:, xs.min():xs.max() + 1], meta["anchor"][1], meta.get("size"), meta["name"]))
    items.sort(key=lambda t: t[0])
    table = dict(SIZES, **(style.spec.get("sizes") or {}))
    gap = 10
    above = max(max(a for _, _, a, _, _ in items), max(table.values()) + 6)
    below = max(s.shape[0] - a for _, s, a, _, _ in items)
    W = sum(s.shape[1] for _, s, _, _, _ in items) + gap * (len(items) + 1) + 24
    H = above + below + 10
    canvas = ground(style, W, H)
    base_y = above + 4
    x = gap + 24
    for _, s, a, _, _ in items:
        region = canvas[base_y - a:base_y - a + s.shape[0], x:x + s.shape[1]]
        m = s[..., 3] > 0
        region[m] = s[m]
        x += s.shape[1] + gap
    im = Image.fromarray(canvas).resize((W * scale, H * scale), Image.NEAREST)
    dr = ImageDraw.Draw(im)
    for name, hpx in table.items():
        y = (base_y - hpx) * scale
        for xx in range(0, W * scale, 8):
            dr.line([(xx, y), (xx + 3, y)], fill=(255, 240, 200), width=1)
        dr.text((4, y - 12), "%s %d" % (name, hpx), fill=(255, 240, 200))
    dr.line([(0, base_y * scale), (W * scale, base_y * scale)], fill=(255, 255, 255), width=1)
    x = gap + 24
    for h, s, _, size, name in items:
        label = "%s\n%dpx %s" % (name, h, size or ("~" + class_of(h, table)))
        dr.text((x * scale, (base_y + 2) * scale), label, fill=(255, 255, 255))
        x += s.shape[1] + gap
    out = Path(out or "out/sizes.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out
