"""Pixel cleanliness check for a 1x render: orphans, whiskers and stair regularity.

  python3 -m pp pixcheck out/flat_forest/noon_1x.png [--mark marked.png]

- orphan: a pixel with no same-colour pixel among its 8 neighbours (a lone speck; diagonal 1:1 lines are fine).
- whisker: a pixel with exactly one same-colour 8-neighbour (the run dead-ends after one pixel). Many are fine
  (legs, antlers, beaks, window corners); a crowd of them along an edge is dirt.
- stairs: along every colour boundary, the horizontal shift of the edge between consecutive rows. Clean iso art
  shifts by 0, 1 or 2; a shift of 3+ inside an edge is a broken stair.
The marked image shows orphans magenta, whiskers yellow and broken stairs cyan over a dimmed copy, at 4x.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict

import numpy as np
from PIL import Image


def check(path, mark=None) -> Dict:
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.int32)
    key = a[..., 0] * 65536 + a[..., 1] * 256 + a[..., 2]
    H, W = key.shape
    P = np.pad(key, 1, mode="edge")
    c = P[1:-1, 1:-1]
    same8 = sum((P[1 + dy:H + 1 + dy, 1 + dx:W + 1 + dx] == c).astype(int)
                for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    border = np.zeros((H, W), bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True      # edge padding fakes neighbours
    orphan = (same8 == 0) & ~border
    whisker = (same8 == 1) & ~border
    shifts = Counter()
    broken = np.zeros((H, W), bool)
    prev = None
    for y in range(H):
        row = key[y]
        edges = {}
        for x in np.nonzero(row[1:] != row[:-1])[0] + 1:
            edges.setdefault((int(row[x - 1]), int(row[x])), []).append(int(x))
        if prev is not None:
            for pair, xs in edges.items():
                for x in xs if pair in prev else ():
                    d = min(abs(x - px) for px in prev[pair])
                    if d <= 4:
                        shifts[d] += 1
                        broken[y, x] |= d >= 3
        prev = edges
    rep = {"size": [W, H], "orphans": int(orphan.sum()), "whiskers": int(whisker.sum()),
           "stair_shifts": dict(sorted(shifts.items())), "broken_stairs": int(broken.sum())}
    if mark:
        out = (a * 0.35).astype(np.uint8)
        out[orphan] = (255, 0, 255)
        out[whisker] = (255, 220, 0)
        out[broken] = (0, 200, 255)
        Image.fromarray(out).resize((W * 4, H * 4), Image.NEAREST).save(mark)
    return rep
