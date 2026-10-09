"""Export the hidden 3D models (SDF parts + per-frame bone transforms) for the showroom's 3D view.

Nothing here is a mesh: each asset is the same list of primitives the forge ray-marches, plus the
bone matrices for every frame of every clip, so the browser can ray-march the identical shapes.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict

import numpy as np

from pp.flora import build_spec
from pp.forge import Forge, load_json
from pp.render import YAW

ROOT = Path(__file__).resolve().parent.parent
SHAPES = {"ellipsoid": 0, "sphere": 0, "capsule": 1, "box": 2, "cylinder": 3, "torus": 4, "cone": 5}


def _r(v, n=3):
    return [round(float(x), n) for x in np.asarray(v).ravel()]


def _part(p: Dict, mat_idx: Dict[str, int]) -> Dict:
    from pp.sdf import rot_matrix
    s = p["shape"]
    out = {"t": SHAPES[s], "m": mat_idx[p["mat"]], "at": _r(p.get("at", (0, 0, 0))),
           "rot": _r(rot_matrix(*p["rot"]).ravel()) if "rot" in p else None,
           "blend": p.get("blend"), "sub": bool(p.get("subtract"))}
    if s in ("ellipsoid", "sphere"):
        r = p.get("r", 1.0)
        out["a"] = _r((r, r, r) if np.isscalar(r) else r)
    elif s == "capsule":
        out["a"] = _r(p.get("a", (0, 0, 0)))
        out["b"] = _r(p["b"])
        out["r1"] = p.get("r1", p.get("r", 1))
        out["r2"] = p.get("r2", p.get("r", 1))
    elif s == "box":
        out["a"] = _r(p["half"])
        out["rr"] = p.get("round", 0.0)
    elif s == "cylinder":
        out["r1"], out["h"], out["rr"] = p["r"], p["h"], p.get("round", 0.0)
    elif s == "torus":
        out["r1"], out["r2"] = p["R"], p["r"]
    elif s == "cone":
        out["r1"], out["h"] = p["r"], p["h"]
        out["flat"] = bool(p.get("flat") or "r_top" in p)
        out["r2"] = p.get("r_top", 0.0)
        out["rr"] = p.get("round", 0.0)
    return out


def export_asset(spec_path: Path) -> Dict:
    spec = load_json(spec_path)
    if "generator" in spec:
        spec = build_spec(spec)
    fg = Forge(spec)
    model, style = fg.model, fg.style
    used = sorted({p["mat"] for b in model.bones.values() for p in b.parts})
    mat_idx = {m: i for i, m in enumerate(used)}
    mats = []
    for m in used:
        cols = style.mat_colors(m)
        d = style.materials[m]
        th = d.get("thresholds") or style.thresholds
        mats.append({"name": m, "ramp": ["#%02x%02x%02x" % c for c in cols], "emissive": bool(d.get("emissive")),
                     "th": list(th)[:max(0, len(cols) - 1)], "bias": d.get("bias", 0.0)})
    bones = []
    for name in model.order:
        b = model.bones[name]
        bones.append({"name": name, "blend": b.blend, "parts": [_part(p, mat_idx) for p in b.parts]})
    clips = {}
    for clip in fg.clips():
        frames = []
        for fr in clip.frames:
            world = model.world(fr.pose, YAW["S"], tuple(fr.squash))
            root = np.array([math.floor(v + 0.5) for v in fr.root], float)
            fb = []
            for name in model.order:
                M, o = world[name]
                inv = np.linalg.inv(M)
                sv = np.linalg.svd(M, compute_uv=False)
                hidden = name in (fr.hide or [])
                fb.append(_r(inv.T.ravel(), 4) + _r(o + root) + [round(float(sv.min()), 4), 0 if hidden else 1])
            frames.append(fb)
        clips[clip.name] = frames
    return {"name": spec["name"], "frame": list(fg.size), "anchor": list(fg.anchor), "bones": bones,
            "mats": mats, "light": _r(style.light), "clips": clips}


def export_all(names_by_style: Dict[str, list]) -> Dict[str, Dict]:
    out = {}
    for style, names in names_by_style.items():
        for n in names:
            p = ROOT / "specs" / style / (n + ".json")
            if p.exists():
                out[n] = export_asset(p)
    return out


if __name__ == "__main__":
    import sys
    d = export_asset(Path(sys.argv[1]))
    print(json.dumps(d)[:400], len(json.dumps(d)))
