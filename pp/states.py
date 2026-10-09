"""Building states: a ruin, construction stages and the finished building, all from one building spec.

  python3 -m pp states specs/vista/house_5.json                       # ruin, build 25/50/75/90 %, built
  python3 -m pp states specs/vista/house_5.json --states ruin,build:0.6 --out out

A state is a transform of the SPEC, not of pixels: the engine re-renders the changed geometry with its own light,
materials and outline, so a ruin is shaded like every other building. It works on any building made of the usual
parts: wall boxes standing on the ground (any bone), window/door stamps on them, `roof` shapes, and boxes that
start above the walls (chimneys, belfries).

  ruin        the roof has burned away; plaster has fallen from the broken wall tops (stone shows); a few charred rafters lean from the wall tops; the walls stand at broken
              heights (each wall is cut into upright slices of keyed heights); windows are empty dark holes; a
              chimney stack survives; rubble and weeds at the foot of the walls
  build:k     k in 0..1. Walls rise course by course (whole courses, so you see each course go on) inside a
              scaffold of poles and a plank walk at the working height; bare rafters at k >= 0.75; the roof from
              k >= 0.9; stone and timber piled in front. build:1 is the finished building without scaffold.
  built       the spec as it is

Each state builds like any spec, to <out>/<name>~<state>/ (state names: ruin, build25, ..., built), so a map can
place "house_5~ruin" as an ordinary object. A strip of all states is written next to them as <name>~states.png.
Randomness is keyed on (spec name, part, slice), so a state never reshuffles when another one changes.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from .sdf import STAMP_SHAPES
from .variants import keyed

WALL_MATS = ("plaster", "stone", "wood", "rock")
COURSES = 6                 # a wall goes up in this many visible courses
DEFAULT_STATES = ["ruin", "build:0.25", "build:0.5", "build:0.75", "build:0.9", "built"]


def _walls(spec: Dict) -> List[Tuple[Dict, Dict]]:
    """(bone, part) for every wall box standing on the ground."""
    out = []
    for b in spec["bones"]:
        for p in b.get("parts", []):
            if p["shape"] == "box" and p.get("mat") in WALL_MATS and not p.get("subtract"):
                if p["at"][2] - p["half"][2] <= 0.6:
                    out.append((b, p))
    return out


def _span(p: Dict) -> Tuple[float, float, float, float, float]:
    """x0, x1, y0, y1, top of a wall box (z up, y toward the viewer is negative)."""
    (x, y, z), (hx, hy, hz) = p["at"], p["half"]
    return x - hx, x + hx, y - hy, y + hy, z + hz


def _box(at, half, mat, **kw) -> Dict:
    return {"shape": "box", "at": [round(float(v), 3) for v in at], "half": [round(float(v), 3) for v in half], "mat": mat, **kw}


def _cap(a, b, r, mat) -> Dict:
    return {"shape": "capsule", "at": [0, 0, 0], "a": [round(float(v), 3) for v in a], "b": [round(float(v), 3) for v in b],
            "r": r, "mat": mat}


def _sphere(at, r, mat) -> Dict:
    return {"shape": "sphere", "at": [round(float(v), 3) for v in at], "r": r, "mat": mat}


def _keep_stamps(bone: Dict, top_at, lowest_top: float) -> None:
    """Drop window/door stamps the (lowered) wall no longer reaches; top_at(x) = wall top at x. A stamp_row spans the
    wall, so it is kept only below the lowest top (its own layout then skips anything not on the wall)."""
    keep = []
    for p in bone.get("parts", []):
        if p["shape"] == "stamp" and p["at"][2] + 0.8 > top_at(p["at"][0]):
            continue
        if p["shape"] == "stamp_row" and p["at"][2] + len(p["rows"]) + 0.8 > lowest_top:
            continue
        keep.append(p)
    bone["parts"] = keep


def _roofs(spec: Dict) -> List[Dict]:
    return [p for b in spec["bones"] for p in b.get("parts", []) if p["shape"] == "roof"]


def _drop_roofs(spec: Dict) -> None:
    for b in spec["bones"]:
        b["parts"] = [p for p in b.get("parts", []) if p["shape"] != "roof"]


def _stacks(spec: Dict):
    """Boxes that start above the ground (chimneys, belfries): (bone, part)."""
    return [(b, p) for b in spec["bones"] for p in b.get("parts", [])
            if p["shape"] == "box" and p["at"][2] - p["half"][2] > 0.6]


def ruin(spec: Dict) -> Dict:
    s = copy.deepcopy(spec)
    name = s["name"]
    roofs = _roofs(s)
    extra: List[Dict] = []
    for wi, (bone, p) in enumerate(_walls(s)):
        x0, x1, y0, y1, top = _span(p)
        H = top
        n = max(3, int(round((x1 - x0) / 3.0)))
        w = (x1 - x0) / n
        tops = []
        new = []
        for k in range(n):
            # broken heights: the middle of a wall often stands higher than its ends, never the full height
            h = H * (0.42 + 0.4 * keyed(name, "ruin", wi, k) + 0.08 * math.sin(math.pi * (k + 0.5) / n))
            h = min(h, H * 0.86)
            tops.append(h)
            new.append(_box([x0 + w * (k + 0.5), (y0 + y1) / 2, h / 2], [w / 2 + 0.02, (y1 - y0) / 2, h / 2], p["mat"]))
            if p["mat"] == "plaster":                            # the plaster has fallen off the broken top: stone shows
                c = 0.5 + 0.6 * keyed(name, "cap", wi, k)
                new.append(_box([x0 + w * (k + 0.5), (y0 + y1) / 2, h - c / 2 + 0.05], [w / 2 + 0.06, (y1 - y0) / 2 + 0.06, c / 2], "stone"))
        bone["parts"] = [q for q in bone["parts"] if q is not p] + new
        top_at = lambda x, x0=x0, w=w, tops=tops: tops[max(0, min(len(tops) - 1, int((x - x0) / w)))]
        _keep_stamps(bone, top_at, min(tops))
        for q in bone["parts"]:                                  # empty windows: dark holes
            if q["shape"] in STAMP_SHAPES:
                q["key"] = {k: ("dark" if v in ("window", "glass", "door") else v) for k, v in q["key"].items()}
        # rubble along the front and the near side, weeds between it
        for k in range(int((x1 - x0) * 0.9)):
            u = keyed(name, "rubble", wi, k)
            x = x0 + (x1 - x0) * u
            side = keyed(name, "side", wi, k)
            y = y0 - 0.6 - 1.2 * keyed(name, "dy", wi, k) if side < 0.7 else y0 + (y1 - y0) * keyed(name, "in", wi, k)
            r = 0.6 + 0.6 * keyed(name, "r", wi, k)
            extra.append(_sphere([x, y, r * 0.6], r, "stone" if keyed(name, "m", wi, k) < 0.75 else "leaf"))
    for rf in roofs:                                             # charred rafters leaning from the wall tops
        (cx, cy, cz), (hx, hy), h = rf["at"], rf["half"], rf["h"]
        for k in range(3):
            if keyed(name, "rafter", k) < 0.25:
                continue
            x = cx - hx * 0.7 + hx * 1.4 * (k + 0.3 * keyed(name, "rx", k)) / 2.6
            frac = 0.45 + 0.4 * keyed(name, "rl", k)                 # burned through part way up
            a = [x, cy - hy * 0.9, cz * 0.62]
            b = [x + 0.6 * (keyed(name, "rt", k) - 0.5), cy - hy * 0.9 * (1 - frac), cz * 0.62 + h * 0.7 * frac]
            extra.append(_cap(a, b, 0.5, "dark"))
    _drop_roofs(s)
    for bone, p in _stacks(s):                                   # the chimney stack survives, a little shorter
        p["half"][2] *= 0.8
    s["bones"].append({"name": "ruin_debris", "parent": "root", "parts": extra})
    return s


def build(spec: Dict, k: float) -> Dict:
    k = max(0.0, min(1.0, float(k)))
    if k >= 1.0:
        return copy.deepcopy(spec)
    s = copy.deepcopy(spec)
    name = s["name"]
    kw = min(1.0, k / 0.7)                                       # walls finish at 70 %
    roofs = _roofs(s)
    extra: List[Dict] = []
    wall_top = 0.0
    for wi, (bone, p) in enumerate(_walls(s)):
        x0, x1, y0, y1, top = _span(p)
        h = max(0.6, top * math.floor(kw * COURSES + 1e-6) / COURSES) if kw > 0 else 0.6
        wall_top = max(wall_top, h)
        bone["parts"] = [q for q in bone["parts"] if q is not p] + [
            _box([(x0 + x1) / 2, (y0 + y1) / 2, h / 2], [(x1 - x0) / 2, (y1 - y0) / 2, h / 2], p["mat"])]
        _keep_stamps(bone, lambda x, h=h: h, h)
        # scaffold: poles just outside the corners and along the front, a plank walk at the working height
        work = h + 0.6
        for px in (x0 - 0.9, x1 + 0.9):                          # four corner poles: a frame, not a cage
            for py in (y0 - 0.9, y1 + 0.9):
                extra.append(_cap([px, py, 0], [px, py, work + 2.0], 0.24, "wood"))
        if k < 0.9:
            extra.append(_box([(x0 + x1) / 2, y0 - 0.9, work], [(x1 - x0) / 2 + 1.0, 0.45, 0.18], "wood"))
            extra.append(_box([x1 + 0.9, (y0 + y1) / 2, work], [0.45, (y1 - y0) / 2 + 1.0, 0.18], "wood"))
        # a pile of stone and timber in front while the walls go up
        if kw < 1:
            for j in range(5):
                u = keyed(name, "pile", wi, j)
                extra.append(_box([x0 + 1.5 + u * 3, y0 - 2.6 - 0.8 * keyed(name, "py", wi, j), 0.35 + 0.35 * (j % 2)],
                                  [0.7, 0.5, 0.35], "stone" if j % 3 else "wood"))
    if k < 0.75:
        _drop_roofs(s)
        for bone, p in _stacks(s):
            bone["parts"] = [q for q in bone["parts"] if q is not p]
    elif k < 0.9:                                                # bare rafters: the roof's frame
        for rf in roofs:
            (cx, cy, cz), (hx, hy), h = rf["at"], rf["half"], rf["h"]
            n = max(2, int(hx / 3.5))                            # few rafters read; many become noise
            for j in range(n + 1):
                x = cx - hx * 0.85 + hx * 1.7 * j / n
                extra.append(_cap([x, cy - hy * 0.95, cz], [x, cy, cz + h * 0.92], 0.28, "wood"))
            extra.append(_cap([cx - hx * 0.95, cy, cz + h * 0.92], [cx + hx * 0.95, cy, cz + h * 0.92], 0.25, "wood"))
        _drop_roofs(s)
    s["bones"].append({"name": "site", "parent": "root", "parts": extra})
    return s


def apply(spec: Dict, state: str) -> Tuple[str, Dict]:
    """state 'ruin' | 'build:k' | 'built' -> (suffix, transformed spec)."""
    if state == "ruin":
        out, tag = ruin(spec), "ruin"
    elif state.startswith("build"):
        k = float(state.split(":", 1)[1]) if ":" in state else 0.5
        out, tag = build(spec, k), "build%d" % round(k * 100)
    elif state == "built":
        out, tag = copy.deepcopy(spec), "built"
    else:
        raise ValueError("unknown state %r (ruin, build:k, built)" % state)
    out["name"] = "%s~%s" % (spec["name"], tag)
    out["concept"] = "%s (%s)" % (spec.get("concept", spec["name"]), tag)
    return tag, out


def run(spec_path: str, states: List[str], out_root: str = "out", scale: int = 3) -> List[Path]:
    from PIL import Image, ImageDraw
    from .forge import Forge, load_spec
    from .color import hex_to_rgb
    base = load_spec(spec_path)
    dirs, frames = [], []
    for st in states:
        tag, spec = apply(base, st)
        f = Forge(spec)
        d = Path(out_root) / spec["name"]
        meta = f.build(d)
        clip = next(iter(meta["clips"]))
        sheet = Image.open(d / meta["clips"][clip]["sheet"]).convert("RGBA")
        frames.append((tag, sheet.crop((0, 0, meta["frame_w"], meta["frame_h"]))))
        dirs.append(d)
    bg = tuple(hex_to_rgb(Forge(base).style.spec.get("bg", "#3a3e4a")))
    fw = max(im.width for _, im in frames); fh = max(im.height for _, im in frames)
    strip = Image.new("RGBA", (len(frames) * (fw + 4) * scale, (fh + 10) * scale), bg + (255,))
    dr = ImageDraw.Draw(strip)
    for i, (tag, im) in enumerate(frames):
        strip.alpha_composite(im.resize((im.width * scale, im.height * scale), Image.NEAREST), (i * (fw + 4) * scale, 10 * scale))
        dr.text((i * (fw + 4) * scale + 2, 2), tag, fill=(230, 226, 210, 255))
    p = Path(out_root) / ("%s~states.png" % base["name"])
    strip.save(p)
    return dirs + [p]
