"""Image output: RGBA frames -> PNG, sprite sheets, GIFs, preview upscales."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
from PIL import Image

Frame = np.ndarray  # (h, w, 4) uint8 RGBA


def to_image(frame: Frame, scale: int = 1) -> Image.Image:
    img = Image.fromarray(frame, "RGBA")
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    return img


def save_png(frame: Frame, path, scale: int = 1) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    to_image(frame, scale).save(path)


def compose_bg(frame: Frame, bg=(0, 0, 0)) -> Frame:
    out = np.empty_like(frame)
    a = frame[..., 3:4].astype(np.float32) / 255
    out[..., :3] = (frame[..., :3] * a + np.array(bg) * (1 - a)).astype(np.uint8)
    out[..., 3] = 255
    return out


def save_gif(frames: Sequence[Frame], durations_ms: Sequence[int], path, scale: int = 4,
             bg: Optional[tuple] = None) -> None:
    """Animated GIF. Transparent unless bg is given."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    imgs = []
    for f in frames:
        f2 = compose_bg(f, bg) if bg is not None else f
        imgs.append(to_image(f2, scale))
    if bg is None:
        pal_imgs = []
        for im in imgs:
            alpha = im.getchannel("A")
            p = im.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
            mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
            p.paste(255, mask)
            pal_imgs.append(p)
        pal_imgs[0].save(path, save_all=True, append_images=pal_imgs[1:], duration=list(durations_ms),
                         loop=0, transparency=255, disposal=2)
    else:
        imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=list(durations_ms),
                     loop=0, disposal=2)


def pack_sheet(rows: List[List[Frame]], pad: int = 0) -> Frame:
    """rows of equally sized frames -> one sheet (row = animation/direction)."""
    fh, fw = rows[0][0].shape[:2]
    cols = max(len(r) for r in rows)
    sheet = np.zeros((len(rows) * (fh + pad), cols * (fw + pad), 4), np.uint8)
    for y, r in enumerate(rows):
        for x, f in enumerate(r):
            sheet[y * (fh + pad):y * (fh + pad) + fh, x * (fw + pad):x * (fw + pad) + fw] = f
    return sheet


def write_sheet_json(path, frame_w: int, frame_h: int, rows: List[Dict]) -> None:
    """Engine-friendly metadata: rows[{name, direction, frames:[{x,y,ms}]}]."""
    Path(path).write_text(json.dumps({"frame_w": frame_w, "frame_h": frame_h, "rows": rows}, indent=1))
