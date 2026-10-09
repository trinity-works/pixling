"""Spell effects: a take of an effect on pure black -> one additive overlay sheet + json.

  python3 -m reel fx reel/fx/<name>.json   -> out/reel/_fx/<name>/<name>.png + <name>.json (+ preview.png)

Effects are generated on black (first = last frame = black, so they appear and vanish on their own) and never keyed
by colour: glow and fire are semi-transparent, which a chroma key would fringe. Instead alpha = brightness above the
black level and the colour is un-premultiplied, so the sheet draws correctly both additively (canvas 'lighter',
alpha * rgb gives back the original light) and plainly over the game. The crop is the union of every frame's
footprint, so the effect never shifts between frames, and `anchor` (0..1 of that crop) is the point placed on the
target's feet.

Spec:
  {"name": "fireball_rain", "take": "takes/fireball_rain_a.mp4",
   "range": [0, 120],          source frames used (default: all)
   "frames": 20,               keys, evenly spaced over the range
   "fps": 12,                  playback rate in the export
   "size": 384,                longest side of a cell in px
   "black": 14,                0..255 level treated as black (compression noise)
   "anchor": [0.5, 0.62],      target point in the generated frame (0..1), mapped into the crop
   "tiles": 2.5,               on-screen width in board tiles (the demo scales by this)
   "layer": "over",            draw over ("over") or under ("under") the units
   "feather": 0.06,            fade the light over this fraction of the frame at its border (0 = off)
   "vignette": 0}              also fade to an oval: 0.3 = the last 30% of the inscribed ellipse's radius
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .io import read_frames
from .take import OUT


def light_to_rgba(rgb: np.ndarray, black: float = 14) -> np.ndarray:
    """HxWx3 uint8 on black -> HxWx4 uint8: alpha = brightness above black, colour un-premultiplied."""
    f = rgb.astype(np.float32)
    mx = f.max(-1, keepdims=True)
    a = np.clip((mx[..., 0] - black) / (255 - black), 0, 1)
    col = np.where(mx > 0, f * 255 / np.maximum(mx, 1e-3), 0)        # brightest channel -> 255, never clips
    return np.dstack([col, a * 255]).round().astype(np.uint8)


def _peaks(v, prom=0.25):
    """Local maxima of v that rise at least prom * max(v) above the lowest point since the previous peak."""
    if v.max() <= 0:
        return []
    out, lo = [], v[0]
    for i in range(1, len(v) - 1):
        lo = min(lo, v[i])
        if v[i] >= v[i - 1] and v[i] > v[i + 1] and v[i] - lo >= prom * v.max():
            out.append(i)
            lo = v[i]
    return out or [int(np.argmax(v))]


def edge_fade(shape, feather=0.06, vignette=0.0):
    """Alpha multiplier that fades the light out toward the frame: `feather` over that fraction of the short side
    at the border (an effect grazing the edge dissolves instead of ending in a straight cut), `vignette` over that
    fraction of the inscribed ellipse's radius (for blasts that fill the frame, where a box edge reads as a cut).
    None when both are off."""
    if feather <= 0 and vignette <= 0:
        return None
    H, W = shape
    ramp = np.ones((H, W))
    if feather > 0:
        m = max(1.0, feather * min(H, W))
        ry = np.clip(np.minimum(np.arange(H), H - 1 - np.arange(H)) / m, 0, 1)
        rx = np.clip(np.minimum(np.arange(W), W - 1 - np.arange(W)) / m, 0, 1)
        ramp = np.outer(ry, rx)
    if vignette > 0:
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.hypot((xx + 0.5) / W * 2 - 1, (yy + 0.5) / H * 2 - 1)      # 1 on the inscribed ellipse
        ramp = np.minimum(ramp, np.clip((1 - r) / vignette, 0, 1))
    return ramp * ramp * (3 - 2 * ramp)


def export(spec_path) -> Path:
    spec_path = Path(spec_path)
    s = json.loads(spec_path.read_text())
    name = s.get("name", spec_path.stem)
    take = (spec_path.parent / s["take"]).resolve()
    src = list(read_frames(take))
    lo, hi = s.get("range", [0, len(src)])
    hi = min(hi, len(src))
    n = s.get("frames", 20)
    idx = np.linspace(lo, hi - 1, n).round().astype(int)
    black = s.get("black", 14)
    cels = [light_to_rgba(src[i], black) for i in idx]
    ramp = edge_fade(cels[0].shape[:2], s.get("feather", 0.06), s.get("vignette", 0))
    if ramp is not None:
        for c in cels:
            c[..., 3] = (c[..., 3] * ramp).round().astype(np.uint8)

    alpha = np.max([c[..., 3] for c in cels], axis=0)
    ys, xs = np.nonzero(alpha > 8)
    H, W = alpha.shape
    ax, ay = s.get("anchor", [0.5, 0.5])
    px, py = ax * W, ay * H
    if len(ys) == 0:
        raise SystemExit(f"{take.name}: no effect found above black level {black}")
    pad = 4
    x0, x1 = max(0, xs.min() - pad), min(W, xs.max() + 1 + pad)
    y0, y1 = max(0, ys.min() - pad), min(H, ys.max() + 1 + pad)
    # keep the anchor inside the crop so it always maps to a real point
    x0, x1 = min(x0, int(px)), max(x1, int(px) + 1)
    y0, y1 = min(y0, int(py)), max(y1, int(py) + 1)
    cw, ch = x1 - x0, y1 - y0
    sc = s.get("size", 384) / max(cw, ch)
    w, h = max(1, round(cw * sc)), max(1, round(ch * sc))

    out = OUT / "_fx" / name
    out.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGBA", (w * n, h), (0, 0, 0, 0))
    for i, c in enumerate(cels):
        sheet.paste(Image.fromarray(c[y0:y1, x0:x1]).resize((w, h), Image.LANCZOS), (i * w, 0))
    sheet.save(out / f"{name}.png")
    # impact frames: peaks of the effect's light near the target (bottom half around the anchor), for hit flashes
    near = [c[max(0, int(py) - (y1 - y0) // 4):y1, x0:x1, 3].astype(float).sum() for c in cels]
    hits = _peaks(np.asarray(near), s.get("hit_prominence", 0.25))
    meta = {"name": name, "file": name, "frames": n, "w": w, "h": h, "frameDuration": round(1 / s.get("fps", 12), 4),
            "anchor": [round((px - x0) / cw, 4), round((py - y0) / ch, 4)],
            "tiles": s.get("tiles", 2.5), "layer": s.get("layer", "over"), "hits": s.get("hits", hits), "src": [int(i) for i in idx]}
    (out / f"{name}.json").write_text(json.dumps(meta, indent=1))

    # preview: every key over a dark board colour, the anchor marked with a cross
    pv = Image.new("RGB", (w * n, h), (34, 44, 38))
    pv.paste(sheet, (0, 0), sheet)
    dr = ImageDraw.Draw(pv)
    for i in range(n):
        cx, cy = i * w + meta["anchor"][0] * w, meta["anchor"][1] * h
        dr.line([(cx - 6, cy), (cx + 6, cy)], fill="white")
        dr.line([(cx, cy - 6), (cx, cy + 6)], fill="white")
    pv.save(out / "preview.png")
    return out
