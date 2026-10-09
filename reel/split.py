"""Split a one-row facing sheet (S, SE, E, NE, N on a flat key colour) into start frames.

  python3 -m reel split reel/chars/<name>/ref/sheet.png [--names s,se,e,ne,n] [--size 2048]
      -> ref/start_<facing>.png beside the sheet

Every facing gets the SAME scale (the sheet's relative sizes are the design), the feet go on one shared baseline,
and each figure is centred on its body (the bottom band of its silhouette), not on its weapon, so idle/walk/attack
takes start from frames that line up. Small detached parts (a blade tip, a tassel) join the nearest figure.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from . import key


def figures(rgb: np.ndarray, n: int, cfg: key.KeyCfg = key.KeyCfg()):
    """-> n boolean masks (left to right) of the figures on a key-colour sheet."""
    k = key.border_key(rgb, cfg.ring) / 255.0
    fg = key.alpha_raw(rgb.astype(np.float32) / 255.0, k, cfg.drop_shadow) > 0.5
    fg = ndimage.binary_opening(fg, iterations=2)
    lab, m = ndimage.label(ndimage.binary_dilation(fg, iterations=3))
    if m < n:
        raise ValueError(f"found {m} figures on the sheet, expected {n}")
    sizes = np.bincount(lab.ravel(), minlength=m + 1)[1:]
    boxes = ndimage.find_objects(lab)                          # (y slice, x slice) per component
    big = sorted(np.argsort(sizes)[::-1][:n] + 1, key=lambda i: boxes[i - 1][1].start)
    owner = np.zeros(m + 1, int)
    for j, i in enumerate(big):
        owner[i] = j + 1
    def gap(a, b):                                             # distance between two components' boxes
        (ya, xa), (yb, xb) = boxes[a - 1], boxes[b - 1]
        dx = max(0, xa.start - xb.stop, xb.start - xa.stop)
        dy = max(0, ya.start - yb.stop, yb.start - ya.stop)
        return np.hypot(dx, dy)
    for i in range(1, m + 1):                                  # a stray (blade tip, tassel) joins the figure it
        if owner[i] == 0:                                      # sits next to, not the one whose centre is nearest
            owner[i] = 1 + int(np.argmin([gap(i, b) for b in big]))
    own = owner[lab]
    return [fg & (own == j + 1) for j in range(n)]


def body_x(mask: np.ndarray, band=0.3) -> float:
    """x centre of the bottom `band` of the silhouette (feet/robe), robust to a weapon held out to one side."""
    ys, xs = np.nonzero(mask)
    y0 = ys.max() - band * (ys.max() - ys.min())
    return float(np.median(xs[ys >= y0]))


def split(sheet, names=("s", "se", "e", "ne", "n"), size=2048, height=0.5, base=0.8, margin=0.04, out=None):
    """Write start_<name>.png per figure; returns {name: path}. height = tallest figure / frame, base = feet line."""
    sheet = Path(sheet)
    rgb = np.asarray(Image.open(sheet).convert("RGB"))
    masks = figures(rgb, len(names))
    kc = tuple(int(round(c)) for c in key.border_key(rgb))
    boxes = []
    for m in masks:
        ys, xs = np.nonzero(m)
        boxes.append((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1, body_x(m)))
    s = height * size / max(b[3] - b[1] for b in boxes)
    # shrink so every figure (weapon included) fits inside the frame with a margin on both sides
    lim = size * (0.5 - margin)
    for x0, y0, x1, y1, bx in boxes:
        s = min(s, lim / max(bx - x0, x1 - bx, 1e-6), (base - margin) * size / (y1 - y0))
    out = Path(out) if out else sheet.parent
    res = {}
    for name, m, (x0, y0, x1, y1, bx) in zip(names, masks, boxes):
        a = ndimage.binary_dilation(m, iterations=2)[y0:y1, x0:x1]
        crop = rgb[y0:y1, x0:x1].copy()
        crop[~a] = kc
        w, h = max(1, round((x1 - x0) * s)), max(1, round((y1 - y0) * s))
        fig = Image.fromarray(crop).resize((w, h), Image.LANCZOS)
        am = Image.fromarray((a * 255).astype(np.uint8)).resize((w, h), Image.LANCZOS)
        frame = Image.new("RGB", (size, size), kc)
        frame.paste(fig, (round(size / 2 - (bx - x0) * s), round(base * size) - h), am)
        p = out / f"start_{name}.png"
        frame.save(p)
        res[name] = p
    return res
