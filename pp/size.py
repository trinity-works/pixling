"""Size understanding: a spec says how big it is, the forge makes it that big.

A spec may declare `"size"`: a class name ("tiny", "small", "medium", "large", "huge") or {"height": px}.
The class table is SIZES below; a style may override any entry with its own `"sizes": {...}`. Height means the
visible pixel height of the rest pose (feet to the top of the highest part, facing south), which is what the
eye compares in a lineup. The forge scales the whole spec uniformly (lengths only: angles, timing, colours and
stamp rows are kept; thin parts are clamped so nothing drops below what the forge can draw), refits the frame and
anchor, and records height_px / width_px / size in the build's meta json.

    "size": "small"            # a critter beside a ~30 px hero
    "size": {"height": 30}
"""
from __future__ import annotations

import copy
import math
from typing import Dict, Optional, Tuple

import numpy as np

# visible rest height in px; a ~30 px humanoid hero sits near "medium", a boss is "large"/"huge"
SIZES = {"tiny": 14, "small": 22, "medium": 32, "large": 44, "huge": 58}
ORDER = list(SIZES)

# keys whose numbers are lengths in pixels
LENGTH = {"at", "a", "b", "r", "r1", "r2", "half", "round", "h", "R", "r_top", "blend", "radius", "width", "height",
          "hand_h", "reach", "head_h", "anchor", "w", "offset", "root", "size", "idle_bob", "hover", "float_bob",
          "attack_lunge", "walk_hop", "run_hop", "death_slide", "walk_bob", "side", "forward", "thick"}
MIN = {"r": 0.9, "r1": 0.9, "r2": 0.85, "half": 0.6, "R": 1.2, "size": 22}  # size: in-sprite vfx canvases
# style motion params that are lengths (scaled with the body so a small creature hops a small hop)
MOTION_LENGTHS = {"idle_bob", "hover", "float_bob", "attack_lunge", "walk_hop", "run_hop", "death_slide", "walk_bob",
                  "prop_swing_px"}


def _scale_num(key, v, k):
    out = v * k
    lo = MIN.get(key)
    if lo is not None and v > 0:
        out = max(out, min(v, lo))
    if key == "size":  # vfx canvas sizes must stay whole pixels
        return int(round(out))
    return round(out, 3)


def _walk(node, k, key=None):
    if isinstance(node, dict):
        return {kk: _walk(vv, k, kk) for kk, vv in node.items()}
    if isinstance(node, list):
        if key in LENGTH and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in node):
            return [_scale_num(key, x, k) for x in node]
        return [_walk(x, k, key if key in ("frames", "parts", "bones", "fx") else None) for x in node]
    if isinstance(node, (int, float)) and not isinstance(node, bool) and key in LENGTH:
        return _scale_num(key, node, k)
    return node


def scale_spec(spec: Dict, k: float) -> Dict:
    """A uniformly scaled copy of a spec (the "size" field itself is left alone)."""
    size = spec.get("size")
    body = {kk: vv for kk, vv in spec.items() if kk not in ("size", "frame", "anchor", "name", "concept", "style")}
    out = _walk(body, k)
    for kk in ("name", "concept", "style"):
        if kk in spec:
            out[kk] = spec[kk]
    if size is not None:
        out["size"] = size
    fr = spec.get("frame", [48, 48])
    an = spec.get("anchor", [fr[0] // 2, fr[1] - 6])
    out["frame"] = [max(16, int(math.ceil(v * k / 2) * 2)) for v in fr]
    out["anchor"] = [int(round(v * k)) for v in an]
    return out


def target_height(spec: Dict, style_spec: Optional[Dict] = None) -> Optional[float]:
    s = spec.get("size")
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    if isinstance(s, dict):
        return float(s["height"])
    table = dict(SIZES, **((style_spec or {}).get("sizes") or {}))
    if s not in table:
        raise ValueError("unknown size class %r (known: %s)" % (s, ", ".join(table)))
    return float(table[s])


def size_label(spec: Dict) -> Optional[str]:
    s = spec.get("size")
    if s is None or isinstance(s, str):
        return s
    return "%gpx" % (s if isinstance(s, (int, float)) else s["height"])


def rest_bbox(spec: Dict, style) -> Tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the visible rest pose facing S, relative to the feet anchor (y up = negative)."""
    from .motion import add_knees
    from .render import Model, render_frame
    st = copy.copy(style)
    st.materials = dict(style.materials)
    st.add_materials(spec.get("materials"))
    model = Model(add_knees(spec), st.material_list())
    S = 256
    buf = render_frame(model, {}, "S", (S, S), (S // 2, S - 32), style.light, ss=2)
    ys, xs = np.nonzero(buf.mat >= 0)
    if not len(ys):
        return 0, 0, 0, 0
    return int(xs.min()) - S // 2, int(ys.min()) - (S - 32), int(xs.max()) + 1 - S // 2, int(ys.max()) + 1 - (S - 32)


def measure(spec: Dict, style) -> Tuple[int, int]:
    """Visible rest-pose (height, width) in px."""
    x0, y0, x1, y1 = rest_bbox(spec, style)
    return max(0, -y0), x1 - x0


def fit(spec: Dict, style) -> Tuple[Dict, float]:
    """Apply spec["size"]: -> (scaled spec, scale factor). Specs without a size come back unchanged (k = 1)."""
    tgt = target_height(spec, style.spec)
    if tgt is None:
        return spec, 1.0
    h0, _ = measure(spec, style)
    if h0 <= 0:
        return spec, 1.0
    k = tgt / h0
    out = scale_spec(spec, k)
    h1, _ = measure(out, style)          # clamped thin parts and pixel rounding: one correction pass
    if h1 > 0 and abs(h1 - tgt) >= 1:
        k *= tgt / h1
        out = scale_spec(spec, k)
    # frame must hold the rest pose with room to move (the scaled frame was fit for the original's animations)
    x0, y0, x1, y1 = rest_bbox(out, style)
    fw, fh = out["frame"]
    ax, ay = out["anchor"]
    m = max(4, int(round(6 * min(1.0, k))))
    left, right, up, down = max(ax, -x0 + m), max(fw - ax, x1 + m), max(ay, -y0 + m), max(fh - ay, y1 + m)
    half = max(left, right)
    out["frame"] = [int(half * 2 + (half * 2) % 2), int(up + down + (up + down) % 2)]
    out["anchor"] = [half, up]
    return out, k


def scale_motion(params: Dict, k: float, own: Dict) -> Dict:
    """Scale the style's motion lengths (hop heights, bobs, lunges) with the body; the spec's own anim values were
    already scaled with the spec."""
    if abs(k - 1) < 1e-6:
        return params
    out = dict(params)
    for key in MOTION_LENGTHS:
        if key in out and key not in own and isinstance(out[key], (int, float)):
            out[key] = round(out[key] * k, 3)
    return out


def class_of(h: float, table: Optional[Dict] = None) -> str:
    """Nearest size class for a measured height."""
    table = table or SIZES
    return min(table, key=lambda c: abs(table[c] - h))
