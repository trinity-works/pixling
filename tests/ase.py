#!/usr/bin/env python3
"""
ase.py - pure-Python reader for Aseprite (.ase/.aseprite) files.

Implements the public spec
https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md

Supported:
  * header (canvas, colour depth RGBA/Grayscale/Indexed, transparent index, pixel ratio, grid)
  * frames + per-frame durations (ms)
  * layers (name, flags/visibility, type normal/group/tilemap, child level -> tree,
    blend mode, opacity, reference-layer flag)
  * cels (raw, linked, zlib-compressed; tilemap cels are recorded but not rendered),
    cel opacity, z-index
  * palettes (new 0x2019, old 0x0004 / 0x0011)
  * tags (name, from, to, direction, repeat, colour)
  * slices (keys, 9-patch centre, pivot)
  * user-data chunks attached to the previous object (text / colour only)

Compositing: visible layers (layer + all ancestor groups visible, reference layers skipped),
cel opacity x layer opacity x group opacity, common blend modes.

Dependencies: numpy, Pillow (only for export helpers).

Library use:
    from ase import AseFile
    a = AseFile.load("x.aseprite")
    img = a.render_frame(0)            # HxWx4 uint8 numpy array
    a.tags, a.frames[0].duration, a.palette, a.layers

CLI:
    python ase.py info  FILE             # JSON summary to stdout
    python ase.py export FILE OUTDIR [--scale 4]
"""
from __future__ import annotations

import io
import json
import os
import struct
import sys
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

# --------------------------------------------------------------------------- constants
CHUNK_OLD_PALETTE_256 = 0x0004
CHUNK_OLD_PALETTE_64 = 0x0011
CHUNK_LAYER = 0x2004
CHUNK_CEL = 0x2005
CHUNK_CEL_EXTRA = 0x2006
CHUNK_COLOR_PROFILE = 0x2007
CHUNK_EXTERNAL_FILES = 0x2008
CHUNK_MASK = 0x2016
CHUNK_PATH = 0x2017
CHUNK_TAGS = 0x2018
CHUNK_PALETTE = 0x2019
CHUNK_USER_DATA = 0x2020
CHUNK_SLICE = 0x2022
CHUNK_TILESET = 0x2023

BLEND_NAMES = [
    "normal", "multiply", "screen", "overlay", "darken", "lighten", "color_dodge",
    "color_burn", "hard_light", "soft_light", "difference", "exclusion", "hue",
    "saturation", "color", "luminosity", "addition", "subtract", "divide",
]
DIRECTIONS = ["forward", "reverse", "pingpong", "pingpong_reverse"]
LAYER_TYPES = ["normal", "group", "tilemap"]

LF_VISIBLE = 1
LF_EDITABLE = 2
LF_LOCK_MOVE = 4
LF_BACKGROUND = 8
LF_PREFER_LINKED = 16
LF_COLLAPSED = 32
LF_REFERENCE = 64


# --------------------------------------------------------------------------- data classes
@dataclass
class Layer:
    index: int
    name: str
    flags: int
    type: int
    child_level: int
    blend_mode: int
    opacity: int
    parent: Optional[int] = None
    tileset_index: Optional[int] = None
    user_text: Optional[str] = None

    @property
    def visible(self) -> bool:
        return bool(self.flags & LF_VISIBLE)

    @property
    def is_group(self) -> bool:
        return self.type == 1

    @property
    def is_reference(self) -> bool:
        return bool(self.flags & LF_REFERENCE)

    @property
    def is_background(self) -> bool:
        return bool(self.flags & LF_BACKGROUND)

    @property
    def blend(self) -> str:
        return BLEND_NAMES[self.blend_mode] if self.blend_mode < len(BLEND_NAMES) else str(self.blend_mode)


@dataclass
class Cel:
    layer_index: int
    frame_index: int
    x: int
    y: int
    opacity: int
    cel_type: int
    z_index: int = 0
    width: int = 0
    height: int = 0
    pixels: Optional[np.ndarray] = None  # raw decoded: HxWx4 (RGBA), HxWx2 (gray), HxW (indexed)
    linked_frame: Optional[int] = None


@dataclass
class Frame:
    index: int
    duration: int
    cels: List[Cel] = field(default_factory=list)


@dataclass
class Tag:
    name: str
    from_frame: int
    to_frame: int
    direction: str
    repeat: int
    color: Tuple[int, int, int]

    @property
    def frames(self) -> List[int]:
        return list(range(self.from_frame, self.to_frame + 1))


@dataclass
class SliceKey:
    frame: int
    x: int
    y: int
    w: int
    h: int
    center: Optional[Tuple[int, int, int, int]] = None
    pivot: Optional[Tuple[int, int]] = None


@dataclass
class Slice:
    name: str
    flags: int
    keys: List[SliceKey]


# --------------------------------------------------------------------------- reader
class _R:
    def __init__(self, b: bytes):
        self.b = b
        self.p = 0

    def read(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def u8(self):
        v = self.b[self.p]; self.p += 1; return v

    def u16(self):
        v, = struct.unpack_from("<H", self.b, self.p); self.p += 2; return v

    def i16(self):
        v, = struct.unpack_from("<h", self.b, self.p); self.p += 2; return v

    def u32(self):
        v, = struct.unpack_from("<I", self.b, self.p); self.p += 4; return v

    def i32(self):
        v, = struct.unpack_from("<i", self.b, self.p); self.p += 4; return v

    def string(self):
        n = self.u16()
        return self.read(n).decode("utf-8", errors="replace")

    def skip(self, n):
        self.p += n


class AseFile:
    def __init__(self):
        self.path: str = ""
        self.width = self.height = 0
        self.color_depth = 32
        self.flags = 0
        self.transparent_index = 0
        self.num_colors = 0
        self.pixel_ratio = (1, 1)
        self.grid = (0, 0, 16, 16)
        self.frames: List[Frame] = []
        self.layers: List[Layer] = []
        self.tags: List[Tag] = []
        self.slices: List[Slice] = []
        self.palette: List[Tuple[int, int, int, int]] = []
        self.warnings: List[str] = []

    # ---------------------------------------------------------------- parsing
    @classmethod
    def load(cls, path: str) -> "AseFile":
        with open(path, "rb") as f:
            data = f.read()
        a = cls.from_bytes(data)
        a.path = path
        return a

    @classmethod
    def from_bytes(cls, data: bytes) -> "AseFile":
        a = cls()
        r = _R(data)
        _filesize = r.u32()
        magic = r.u16()
        if magic != 0xA5E0:
            raise ValueError("not an aseprite file (bad magic %04x)" % magic)
        nframes = r.u16()
        a.width = r.u16()
        a.height = r.u16()
        a.color_depth = r.u16()
        a.flags = r.u32()
        _speed = r.u16()
        r.skip(8)
        a.transparent_index = r.u8()
        r.skip(3)
        a.num_colors = r.u16()
        pw, ph = r.u8(), r.u8()
        a.pixel_ratio = (pw or 1, ph or 1)
        gx, gy, gw, gh = r.i16(), r.i16(), r.u16(), r.u16()
        a.grid = (gx, gy, gw, gh)
        r.p = 128

        last_obj = None  # for user data attachment
        tag_ud_queue: List[Tag] = []
        for fi in range(nframes):
            fstart = r.p
            fbytes = r.u32()
            fmagic = r.u16()
            if fmagic != 0xF1FA:
                raise ValueError("bad frame magic at frame %d" % fi)
            old_chunks = r.u16()
            duration = r.u16()
            r.skip(2)
            new_chunks = r.u32()
            nchunks = new_chunks if new_chunks != 0 else old_chunks
            frame = Frame(fi, duration)
            a.frames.append(frame)
            for _ in range(nchunks):
                cstart = r.p
                csize = r.u32()
                ctype = r.u16()
                cend = cstart + csize
                body = _R(data[r.p:cend])
                try:
                    obj = a._chunk(ctype, body, frame)
                except Exception as e:  # keep going on malformed chunks
                    a.warnings.append("frame %d chunk %04x: %s" % (fi, ctype, e))
                    obj = None
                if ctype == CHUNK_USER_DATA:
                    ud = obj
                    if tag_ud_queue:
                        tag_ud_queue.pop(0)  # user data for tags; ignored
                    elif isinstance(last_obj, Layer) and ud and ud.get("text"):
                        last_obj.user_text = ud["text"]
                elif ctype == CHUNK_TAGS:
                    tag_ud_queue = list(obj or [])
                    last_obj = None
                elif obj is not None:
                    last_obj = obj
                    tag_ud_queue = []
                r.p = cend
            r.p = fstart + fbytes

        # parents for layer tree
        stack: List[int] = []
        for L in a.layers:
            while len(stack) > L.child_level:
                stack.pop()
            L.parent = stack[-1] if stack else None
            if L.is_group:
                stack = stack[:L.child_level] + [L.index]
        # resolve linked cels
        for fr in a.frames:
            for c in fr.cels:
                if c.cel_type == 1 and c.linked_frame is not None:
                    src = a._find_cel(c.linked_frame, c.layer_index)
                    if src is not None:
                        c.x, c.y, c.width, c.height, c.pixels = src.x, src.y, src.width, src.height, src.pixels
                        # opacity/z of the linked cel stays its own
        return a

    def _find_cel(self, frame: int, layer: int) -> Optional[Cel]:
        if frame >= len(self.frames):
            return None
        for c in self.frames[frame].cels:
            if c.layer_index == layer:
                return c
        return None

    def _chunk(self, ctype: int, r: _R, frame: Frame):
        if ctype in (CHUNK_OLD_PALETTE_256, CHUNK_OLD_PALETTE_64):
            # only use old palettes if no new palette chunk was seen
            npk = r.u16()
            idx = 0
            pal = list(self.palette)
            for _ in range(npk):
                idx += r.u8()
                n = r.u8() or 256
                for _k in range(n):
                    rr, gg, bb = r.u8(), r.u8(), r.u8()
                    if ctype == CHUNK_OLD_PALETTE_64:
                        rr, gg, bb = [(v << 2) | (v >> 4) for v in (rr, gg, bb)]
                    while len(pal) <= idx:
                        pal.append((0, 0, 0, 255))
                    pal[idx] = (rr, gg, bb, 255)
                    idx += 1
            if not getattr(self, "_new_palette_seen", False):
                self.palette = pal
            return None
        if ctype == CHUNK_PALETTE:
            size = r.u32(); first = r.u32(); last = r.u32(); r.skip(8)
            pal = list(self.palette)
            while len(pal) < size:
                pal.append((0, 0, 0, 255))
            pal = pal[:size]
            for i in range(first, last + 1):
                fl = r.u16()
                rr, gg, bb, aa = r.u8(), r.u8(), r.u8(), r.u8()
                if fl & 1:
                    r.string()
                pal[i] = (rr, gg, bb, aa)
            self.palette = pal
            self._new_palette_seen = True
            return None
        if ctype == CHUNK_LAYER:
            flags = r.u16(); ltype = r.u16(); lvl = r.u16()
            r.u16(); r.u16()
            blend = r.u16(); opacity = r.u8(); r.skip(3)
            name = r.string()
            valid = bool(self.flags & 1) and (ltype != 1 or bool(self.flags & 2))
            L = Layer(len(self.layers), name, flags, ltype, lvl,
                      blend if (ltype != 1 or self.flags & 2) else 0,
                      opacity if valid else 255)
            if ltype == 2:
                L.tileset_index = r.u32()
            self.layers.append(L)
            return L
        if ctype == CHUNK_CEL:
            li = r.u16(); x = r.i16(); y = r.i16(); op = r.u8(); ct = r.u16(); z = r.i16(); r.skip(5)
            c = Cel(li, frame.index, x, y, op, ct, z)
            bpp = {32: 4, 16: 2, 8: 1}[self.color_depth]
            if ct == 0:
                c.width, c.height = r.u16(), r.u16()
                raw = r.read(c.width * c.height * bpp)
                c.pixels = self._decode(raw, c.width, c.height, bpp)
            elif ct == 1:
                c.linked_frame = r.u16()
            elif ct == 2:
                c.width, c.height = r.u16(), r.u16()
                raw = _inflate(r.b[r.p:])
                c.pixels = self._decode(raw, c.width, c.height, bpp)
            elif ct == 3:
                c.width, c.height = r.u16(), r.u16()  # tilemap: not rendered
            frame.cels.append(c)
            return c
        if ctype == CHUNK_TAGS:
            n = r.u16(); r.skip(8)
            out = []
            for _ in range(n):
                fr, to = r.u16(), r.u16()
                d = r.u8(); rep = r.u16(); r.skip(6)
                col = (r.u8(), r.u8(), r.u8()); r.skip(1)
                name = r.string()
                t = Tag(name, fr, to, DIRECTIONS[d] if d < 4 else str(d), rep, col)
                out.append(t)
            self.tags.extend(out)
            return out
        if ctype == CHUNK_USER_DATA:
            fl = r.u32()
            ud = {}
            if fl & 1:
                ud["text"] = r.string()
            if fl & 2:
                ud["color"] = (r.u8(), r.u8(), r.u8(), r.u8())
            return ud
        if ctype == CHUNK_SLICE:
            nk = r.u32(); fl = r.u32(); r.u32(); name = r.string()
            keys = []
            for _ in range(nk):
                k = SliceKey(r.u32(), r.i32(), r.i32(), r.u32(), r.u32())
                if fl & 1:
                    k.center = (r.i32(), r.i32(), r.u32(), r.u32())
                if fl & 2:
                    k.pivot = (r.i32(), r.i32())
                keys.append(k)
            s = Slice(name, fl, keys)
            self.slices.append(s)
            return s
        return None

    def _decode(self, raw: bytes, w: int, h: int, bpp: int) -> np.ndarray:
        arr = np.frombuffer(raw, dtype=np.uint8)[: w * h * bpp]
        if bpp == 1:
            return arr.reshape(h, w).copy()
        return arr.reshape(h, w, bpp).copy()

    # ---------------------------------------------------------------- helpers
    @property
    def color_mode(self) -> str:
        return {32: "RGBA", 16: "Grayscale", 8: "Indexed"}.get(self.color_depth, str(self.color_depth))

    def layer_effective_visible(self, li: int) -> bool:
        L = self.layers[li]
        while L is not None:
            if not L.visible or L.is_reference:
                return False
            L = self.layers[L.parent] if L.parent is not None else None
        return True

    def layer_effective_opacity(self, li: int) -> float:
        L = self.layers[li]
        o = 1.0
        while L is not None:
            o *= L.opacity / 255.0
            L = self.layers[L.parent] if L.parent is not None else None
        return o

    def layer_path(self, li: int) -> str:
        parts = []
        L = self.layers[li]
        while L is not None:
            parts.append(L.name)
            L = self.layers[L.parent] if L.parent is not None else None
        return "/".join(reversed(parts))

    def cel_rgba(self, c: Cel) -> Optional[np.ndarray]:
        """Return cel pixels as HxWx4 uint8 RGBA."""
        if c.pixels is None:
            return None
        p = c.pixels
        if self.color_depth == 32:
            return p
        if self.color_depth == 16:
            v, a = p[..., 0], p[..., 1]
            return np.stack([v, v, v, a], -1)
        pal = np.array(self.palette + [(0, 0, 0, 0)] * max(0, 256 - len(self.palette)), dtype=np.uint8)[:256]
        out = pal[p]
        L = self.layers[c.layer_index]
        if not L.is_background:
            out = out.copy()
            out[p == self.transparent_index] = 0
        return out

    def cels_for_frame(self, fi: int, include_hidden=False) -> List[Cel]:
        cels = [c for c in self.frames[fi].cels
                if c.layer_index < len(self.layers)
                and self.layers[c.layer_index].type == 0
                and (include_hidden or self.layer_effective_visible(c.layer_index))]
        # z-index ordering, per spec: order = layer_index + z_index, ties -> z_index
        cels.sort(key=lambda c: (c.layer_index + c.z_index, c.z_index))
        return cels

    def render_frame(self, fi: int, layers: Optional[List[int]] = None,
                     include_hidden=False) -> np.ndarray:
        """Composite a frame -> HxWx4 uint8. `layers` restricts to given layer indices."""
        W, H = self.width, self.height
        dst = np.zeros((H, W, 4), dtype=np.float32)
        for c in self.cels_for_frame(fi, include_hidden=include_hidden or layers is not None):
            if layers is not None and c.layer_index not in layers:
                continue
            src = self.cel_rgba(c)
            if src is None:
                continue
            x0, y0 = max(c.x, 0), max(c.y, 0)
            x1, y1 = min(c.x + c.width, W), min(c.y + c.height, H)
            if x1 <= x0 or y1 <= y0:
                continue
            s = src[y0 - c.y:y1 - c.y, x0 - c.x:x1 - c.x].astype(np.float32) / 255.0
            op = (c.opacity / 255.0) * self.layer_effective_opacity(c.layer_index)
            d = dst[y0:y1, x0:x1]
            _blend(d, s, op, self.layers[c.layer_index].blend_mode)
        return (np.clip(dst, 0, 1) * 255 + 0.5).astype(np.uint8)

    def frame_sequence(self, tag: Tag) -> List[int]:
        f = tag.frames
        if tag.direction == "reverse":
            return f[::-1]
        if tag.direction == "pingpong":
            return f + f[-2:0:-1]
        if tag.direction == "pingpong_reverse":
            r = f[::-1]
            return r + r[-2:0:-1]
        return f

    def layer_tree(self) -> List[dict]:
        out = []
        for L in self.layers:
            out.append({
                "index": L.index, "name": L.name, "path": self.layer_path(L.index),
                "type": LAYER_TYPES[L.type] if L.type < 3 else L.type,
                "depth": L.child_level, "parent": L.parent,
                "visible": L.visible, "effective_visible": self.layer_effective_visible(L.index),
                "reference": L.is_reference, "background": L.is_background,
                "blend": L.blend, "opacity": L.opacity,
                "cel_count": sum(1 for fr in self.frames for c in fr.cels if c.layer_index == L.index),
            })
        return out

    def background_layers(self) -> List[int]:
        """Heuristic: layers flagged background or named like BG/background/backdrop."""
        out = []
        for L in self.layers:
            n = L.name.strip().lower().rstrip(".")
            if L.is_background or n in ("bg", "background", "backdrop", "bg color"):
                out.append(L.index)
                continue
            # a bottom-ish plain layer whose cel fills >=90% of the canvas in frame 0
            if L.type == 0 and L.index <= 1 and self.frames:
                c = self._find_cel(0, L.index)
                if c is not None and c.pixels is not None:
                    rgba = self.cel_rgba(c)
                    if rgba is not None and (rgba[..., 3] > 0).sum() >= 0.9 * self.width * self.height:
                        out.append(L.index)
        return out

    def content_layers(self) -> List[int]:
        bg = set(self.background_layers())
        return [L.index for L in self.layers
                if L.type == 0 and L.index not in bg and self.layer_effective_visible(L.index)]

    def summary(self, rendered: Optional[List[np.ndarray]] = None) -> dict:
        if rendered is None:
            rendered = [self.render_frame(i) for i in range(len(self.frames))]
        colors = set()
        bboxes = []
        content = self.content_layers()
        bgl = self.background_layers()
        for i, img in enumerate(rendered):
            m = img[..., 3] > 0
            px = img[m]
            colors.update(map(tuple, px[:, :3].tolist()))
            cm = self.render_frame(i, layers=content)[..., 3] > 0 if bgl else m
            bboxes.append(bbox(cm))
        return {
            "file": os.path.basename(self.path),
            "canvas": [self.width, self.height],
            "color_mode": self.color_mode,
            "pixel_ratio": list(self.pixel_ratio),
            "transparent_index": self.transparent_index,
            "frames": len(self.frames),
            "durations_ms": [f.duration for f in self.frames],
            "total_duration_ms": sum(f.duration for f in self.frames),
            "layers": self.layer_tree(),
            "tags": [{"name": t.name, "from": t.from_frame, "to": t.to_frame,
                      "frames": t.to_frame - t.from_frame + 1, "direction": t.direction,
                      "repeat": t.repeat, "durations_ms": [self.frames[i].duration for i in t.frames],
                      "total_ms": sum(self.frames[i].duration for i in t.frames)}
                     for t in self.tags],
            "slices": [{"name": s.name, "keys": [k.__dict__ for k in s.keys]} for s in self.slices],
            "palette_size": len(self.palette),
            "palette": [hexc(c) for c in self.palette],
            "unique_colors_used": len(colors),
            "used_colors": sorted(hexc(c) for c in colors),
            "background_layers": [self.layers[i].name for i in bgl],
            "bbox_per_frame": bboxes,
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- blending
def _blend(d: np.ndarray, s: np.ndarray, op: float, mode: int):
    """In-place 'src over dst' with blend function (straight alpha, float 0..1)."""
    sa = s[..., 3:4] * op
    if not np.any(sa):
        return
    da = d[..., 3:4]
    Cs, Cb = s[..., :3], d[..., :3]
    name = BLEND_NAMES[mode] if mode < len(BLEND_NAMES) else "normal"
    if name == "multiply":
        B = Cs * Cb
    elif name == "screen":
        B = Cs + Cb - Cs * Cb
    elif name == "overlay":
        B = np.where(Cb <= 0.5, 2 * Cs * Cb, 1 - 2 * (1 - Cs) * (1 - Cb))
    elif name == "hard_light":
        B = np.where(Cs <= 0.5, 2 * Cs * Cb, 1 - 2 * (1 - Cs) * (1 - Cb))
    elif name == "darken":
        B = np.minimum(Cs, Cb)
    elif name == "lighten":
        B = np.maximum(Cs, Cb)
    elif name == "addition":
        B = np.minimum(Cs + Cb, 1)
    elif name == "subtract":
        B = np.maximum(Cb - Cs, 0)
    elif name == "difference":
        B = np.abs(Cb - Cs)
    elif name == "exclusion":
        B = Cs + Cb - 2 * Cs * Cb
    elif name == "color_dodge":
        B = np.where(Cs >= 1, 1, np.minimum(1, Cb / np.maximum(1 - Cs, 1e-6)))
    elif name == "color_burn":
        B = np.where(Cs <= 0, 0, 1 - np.minimum(1, (1 - Cb) / np.maximum(Cs, 1e-6)))
    else:
        B = Cs
    # where dst transparent, blend result is just source colour
    Cmix = (1 - da) * Cs + da * B
    ra = sa + da * (1 - sa)
    with np.errstate(invalid="ignore", divide="ignore"):
        rc = np.where(ra > 0, (Cmix * sa + Cb * da * (1 - sa)) / np.maximum(ra, 1e-9), 0)
    d[..., :3] = rc
    d[..., 3:4] = ra


# --------------------------------------------------------------------------- utils
def _inflate(buf: bytes) -> bytes:
    """zlib inflate tolerant of missing trailer (some exporters e.g. Pixquare omit it)."""
    try:
        return zlib.decompress(buf)
    except zlib.error:
        o = zlib.decompressobj()
        return o.decompress(buf) + o.flush()


def hexc(c) -> str:
    return "#%02x%02x%02x" % tuple(c[:3]) + ("" if len(c) < 4 or c[3] == 255 else "%02x" % c[3])


def bbox(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return {"x": int(xs.min()), "y": int(ys.min()), "w": int(xs.max() - xs.min() + 1),
            "h": int(ys.max() - ys.min() + 1)}


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name).strip("_") or "untitled"


def palette_swatch(palette, cell=16, cols=16):
    from PIL import Image
    n = max(1, len(palette))
    rows = (n + cols - 1) // cols
    img = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 0))
    px = img.load()
    for i, c in enumerate(palette):
        cx, cy = (i % cols) * cell, (i // cols) * cell
        for y in range(cy, cy + cell):
            for x in range(cx, cx + cell):
                px[x, y] = tuple(c[:3]) + (255,)
    return img


def export(a: AseFile, outdir: str, scale: int = 4, max_strip_w: int = 16000) -> dict:
    """Export per-tag strips/GIFs (x1 + xscale), palette swatch + JSON, and summary JSON."""
    from PIL import Image
    os.makedirs(outdir, exist_ok=True)
    rendered = [a.render_frame(i) for i in range(len(a.frames))]
    summ = a.summary(rendered)

    def up(img: "Image.Image") -> "Image.Image":
        return img.resize((img.width * scale, img.height * scale), Image.NEAREST)

    def save_seq(name, seq):
        frames = [Image.fromarray(rendered[i], "RGBA") for i in seq]
        durs = [max(a.frames[i].duration, 20) for i in seq]
        W, H = a.width, a.height
        strip = Image.new("RGBA", (W * len(frames), H))
        for k, f in enumerate(frames):
            strip.paste(f, (k * W, 0))
        strip.save(os.path.join(outdir, f"{name}_strip_x1.png"))
        if strip.width * scale <= max_strip_w:
            up(strip).save(os.path.join(outdir, f"{name}_strip_x{scale}.png"))
        # gif: transparent -> keep alpha via disposal 2
        gframes = [up(f) for f in frames]
        _save_gif(gframes, durs, os.path.join(outdir, f"{name}_x{scale}.gif"))
        _save_gif(frames, durs, os.path.join(outdir, f"{name}_x1.gif"))

    if a.tags:
        for t in a.tags:
            save_seq("tag_" + _safe(t.name), a.frame_sequence(t))
    save_seq("all", list(range(len(a.frames))))
    # palette
    if a.palette:
        palette_swatch(a.palette).save(os.path.join(outdir, "palette.png"))
    with open(os.path.join(outdir, "palette.json"), "w") as f:
        json.dump({"palette": [hexc(c) for c in a.palette], "used": summ["used_colors"]}, f, indent=1)
    with open(os.path.join(outdir, "summary.json"), "w") as f:
        json.dump(summ, f, indent=1)
    return summ


def _save_gif(frames, durs, path):
    if not frames:
        return
    conv = []
    for f in frames:
        rgba = f.convert("RGBA")
        alpha = rgba.split()[3]
        p = rgba.convert("RGB").quantize(colors=255, method=Image_FASTOCTREE())
        mask = alpha.point(lambda v: 255 if v < 128 else 0)
        p.paste(255, mask)
        p.info["transparency"] = 255
        conv.append(p)
    conv[0].save(path, save_all=True, append_images=conv[1:], duration=durs, loop=0,
                 disposal=2, transparency=255, optimize=False)


def Image_FASTOCTREE():
    from PIL import Image
    return Image.Quantize.FASTOCTREE


# --------------------------------------------------------------------------- cli
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Aseprite file reader/exporter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("info"); p1.add_argument("file")
    p2 = sub.add_parser("export"); p2.add_argument("file"); p2.add_argument("outdir")
    p2.add_argument("--scale", type=int, default=4)
    args = ap.parse_args(argv)
    a = AseFile.load(args.file)
    if args.cmd == "info":
        s = a.summary()
        s.pop("used_colors", None)
        print(json.dumps(s, indent=1))
    else:
        s = export(a, args.outdir, args.scale)
        print(f"exported {args.file} -> {args.outdir} ({s['frames']} frames, {len(a.tags)} tags)")


if __name__ == "__main__":
    main()
