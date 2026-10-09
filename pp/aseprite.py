"""Minimal .aseprite writer (RGBA, one layer, tags, palette) so packs ship editable sources.

Spec: https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np


def _string(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<H", len(b)) + b


def _chunk(ctype: int, data: bytes) -> bytes:
    return struct.pack("<IH", len(data) + 6, ctype) + data


def write_aseprite(path, frames: Sequence[np.ndarray], durations: Sequence[int],
                   tags: Sequence[Tuple[str, int, int]] = (), palette: Sequence[tuple] = (),
                   layer_name: str = "sprite") -> None:
    """frames: (h, w, 4) uint8 all the same size. tags: (name, from, to) inclusive frame indices."""
    h, w = frames[0].shape[:2]
    body = b""
    for i, (f, ms) in enumerate(zip(frames, durations)):
        chunks: List[bytes] = []
        if i == 0:
            if palette:
                pal = struct.pack("<III", len(palette), 0, len(palette) - 1) + b"\0" * 8
                for c in palette:
                    pal += struct.pack("<HBBBB", 0, c[0], c[1], c[2], c[3] if len(c) > 3 else 255)
                chunks.append(_chunk(0x2019, pal))
            chunks.append(_chunk(0x2004, struct.pack("<HHHHHHB3x", 3, 0, 0, 0, 0, 0, 255) + _string(layer_name)))
            if tags:
                t = struct.pack("<H8x", len(tags))
                for name, a, b in tags:
                    t += struct.pack("<HHBH6x3Bx", a, b, 0, 0, 120, 160, 220) + _string(name)
                chunks.append(_chunk(0x2018, t))
        ys, xs = np.nonzero(f[..., 3])
        if len(ys):
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            crop = np.ascontiguousarray(f[y0:y1, x0:x1])
            cel = struct.pack("<HhhBHh5x", 0, int(x0), int(y0), 255, 2, 0)
            cel += struct.pack("<HH", x1 - x0, y1 - y0) + zlib.compress(crop.tobytes())
            chunks.append(_chunk(0x2005, cel))
        data = b"".join(chunks)
        n = len(chunks)
        body += struct.pack("<IHHH2xI", len(data) + 16, 0xF1FA, min(n, 0xFFFF), int(ms), n) + data
    header = struct.pack("<IHHHHHIHII", 128 + len(body), 0xA5E0, len(frames), w, h, 32, 1,
                         int(durations[0]) if durations else 100, 0, 0)
    header += struct.pack("<B3xHBBhhHH", 0, len(palette) if palette else 0, 1, 1, 0, 0, 16, 16)
    header += b"\0" * (128 - len(header))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(header + body)


def export_build(build_dir, out_path=None, palette: Sequence[tuple] = ()) -> Path:
    """All clips x directions of a build dir into one .aseprite, tagged "<clip>_<dir>"."""
    import json
    from PIL import Image
    d = Path(build_dir)
    meta = json.loads((d / (d.name + ".json")).read_text())
    fw, fh = meta["frame_w"], meta["frame_h"]
    frames, durs, tags = [], [], []
    for clip, c in meta["clips"].items():
        sheet = np.array(Image.open(d / c["sheet"]).convert("RGBA"))
        for r, dn in enumerate(meta["directions"]):
            start = len(frames)
            for i, fr in enumerate(c["frames"]):
                frames.append(sheet[r * fh:(r + 1) * fh, i * fw:(i + 1) * fw])
                durs.append(fr["ms"])
            tags.append(("%s_%s" % (clip, dn), start, len(frames) - 1))
    out = Path(out_path or d / (d.name + ".aseprite"))
    write_aseprite(out, frames, durs, tags, palette)
    return out
