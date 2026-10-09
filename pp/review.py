"""Review views: zoomed grids of chosen clips/directions, cheap to look at."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

from .color import hex_to_rgb
from .paths import DATA


def review_sheet(build_dir, clips: Optional[List[str]] = None, dirs: Optional[List[str]] = None,
                 scale: int = 5, bg: Optional[str] = None, out=None) -> Path:
    d = Path(build_dir)
    meta = json.loads(next(d.glob("*.json")).read_text()) if not (d / "meta.json").exists() else None
    fw, fh = meta["frame_w"], meta["frame_h"]
    alld = meta["directions"]
    dirs = dirs or alld
    clips = clips or list(meta["clips"].keys())
    rows = []
    for c in clips:
        sheet = np.array(Image.open(d / meta["clips"][c]["sheet"]).convert("RGBA"))
        for dn in dirs:
            r = alld.index(dn)
            rows.append(sheet[r * fh:(r + 1) * fh])
    W = max(r.shape[1] for r in rows)
    canvas = np.zeros((len(rows) * fh, W, 4), np.uint8)
    for i, r in enumerate(rows):
        canvas[i * fh:(i + 1) * fh, :r.shape[1]] = r
    if bg is None:
        # judge sprites on the ground they ship on: the style's bg (dark neutral if unknown)
        sp = DATA / "styles" / ("%s.json" % meta.get("style", ""))
        bg = json.loads(sp.read_text()).get("bg") if sp.exists() else None
    bgc = hex_to_rgb(bg or "#2a2f3a")
    img = Image.new("RGBA", (W, canvas.shape[0]), (*bgc, 255))
    img.alpha_composite(Image.fromarray(canvas))
    # faint frame grid so frames are distinguishable
    arr = np.array(img)
    arr[::fh, :, :3] = np.clip(arr[::fh, :, :3].astype(int) + 14, 0, 255)
    arr[:, ::fw, :3] = np.clip(arr[:, ::fw, :3].astype(int) + 14, 0, 255)
    img = Image.fromarray(arr).resize((W * scale, canvas.shape[0] * scale), Image.NEAREST)
    out = Path(out or d / ("review_%s_%s.png" % ("-".join(clips), "".join(dirs))))
    img.save(out)
    return out


def onion_sheet(build_dir, clips: Optional[List[str]] = None, dirs: Optional[List[str]] = None,
                scale: int = 5, out=None) -> Path:
    """Animation check: every frame of a clip overlaid in one cell (early frames faint and cool, late
    frames strong and warm) over a ground line at the anchor, so arcs, hops, lunges and drift show
    at a glance. One row per clip, one column per direction."""
    d = Path(build_dir)
    meta = json.loads(next(p for p in d.glob("*.json") if p.stem == d.name).read_text())
    fw, fh = meta["frame_w"], meta["frame_h"]
    alld = meta["directions"]
    dirs = dirs or alld
    clips = clips or list(meta["clips"].keys())
    canvas = np.zeros((len(clips) * fh, len(dirs) * fw, 3), np.float32)
    canvas[:] = (236, 232, 224)
    ax, ay = meta["anchor"]
    for ci, c in enumerate(clips):
        sheet = np.array(Image.open(d / meta["clips"][c]["sheet"]).convert("RGBA")).astype(np.float32)
        n = sheet.shape[1] // fw
        for di, dn in enumerate(dirs):
            r = alld.index(dn)
            y0, x0 = ci * fh, di * fw
            canvas[y0 + ay, x0:x0 + fw] = (170, 160, 150)                     # ground line
            for k in range(n):
                fr = sheet[r * fh:(r + 1) * fh, k * fw:(k + 1) * fw]
                t = k / max(1, n - 1)
                tint = np.array([40 + 200 * t, 70, 220 - 200 * t], np.float32)   # blue (first) -> red (last)
                m = fr[..., 3] > 0
                edge = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1))
                cell = canvas[y0:y0 + fh, x0:x0 + fw]
                cell[m] = cell[m] * 0.86 + tint * 0.14                        # faint fill: where the body spends time
                cell[edge] = tint                                             # outline: the path of each frame
    img = Image.fromarray(canvas.clip(0, 255).astype(np.uint8))
    arr = np.array(img)
    arr[::fh, :] = (200, 196, 188)
    arr[:, ::fw] = (200, 196, 188)
    img = Image.fromarray(arr).resize((arr.shape[1] * scale, arr.shape[0] * scale), Image.NEAREST)
    out = Path(out or d / ("onion_%s_%s.png" % ("-".join(clips), "".join(dirs))))
    img.save(out)
    return out
