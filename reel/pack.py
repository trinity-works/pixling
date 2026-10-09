"""Matte check: a keyed take over magenta, white and black, the views that expose bad keys."""
from __future__ import annotations

import numpy as np
from PIL import Image

from .io import save_png


def over(frame, bg):
    im = Image.fromarray(np.ascontiguousarray(bg)).convert("RGBA")
    im.alpha_composite(Image.fromarray(frame))
    return np.asarray(im.convert("RGB"))


def matte_check(src_frames, cels, path, n=4, width=360):
    """Source | cutout over magenta | over white | over black: the views that expose bad keys.
    src_frames: [(index, frame)] samples kept while keying."""
    pick = np.linspace(0, len(src_frames) - 1, min(n, len(src_frames))).astype(int)
    tiles = []
    for j in pick:
        i, src = src_frames[j]
        H, W = src.shape[:2]
        full = np.zeros((H, W, 4), np.uint8)
        c = cels[i]
        h, w = c.rgba.shape[:2]
        full[c.y0:c.y0 + h, c.x0:c.x0 + w] = c.rgba
        s = width / W
        views = [src, over(full, np.full((H, W, 3), (255, 0, 255), np.uint8)),
                 over(full, np.full((H, W, 3), 255, np.uint8)), over(full, np.full((H, W, 3), 12, np.uint8))]
        views = [np.asarray(Image.fromarray(v).resize((width, int(H * s)), Image.LANCZOS)) for v in views]
        tiles.append(np.concatenate(views, 1))
    save_png(np.concatenate(tiles, 0), path)
