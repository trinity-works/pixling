"""Procedural spec generators for trees, bushes, rocks (static props).

They emit ordinary model specs (bones + parts) so the same renderer, palette
lock and lints apply. Each foliage clump is its own bone: the inner-line pass
then separates clumps with a dark seam on the far side, which is what gives
pixel trees their readable "cluster" structure instead of one shaded ball.
Wind sway = clumps offset by whole pixels in a travelling wave (no swimming).
"""
from __future__ import annotations

import math
from typing import Dict, List

import numpy as np


def _rng(seed):
    return np.random.default_rng(seed)


def tree_round(seed: int = 1, height: float = 44, crown: float = 15, clumps: int = 7,
               leaf: str = "leaf", bark: str = "bark", lean: float = 0.0, trunk_frac: float = 0.42,
               trunk_r: float = 2.6) -> Dict:
    r = _rng(seed)
    trunk_h = height * trunk_frac
    bones: List[Dict] = [{"name": "root"}]
    trunk_parts = [
        {"shape": "capsule", "a": [0, 0, 0], "b": [lean, 0, trunk_h + crown * 0.3], "r1": trunk_r,
         "r2": trunk_r * 0.62, "mat": bark},
        {"shape": "capsule", "a": [0, 0, 0.5], "b": [-3.2, -0.5, -0.2], "r1": 1.3, "r2": 0.8, "mat": bark},
        {"shape": "capsule", "a": [0, 0, 0.5], "b": [3.4, 0.2, -0.2], "r1": 1.3, "r2": 0.8, "mat": bark},
    ]
    # two visible branches into the crown
    for side in (-1, 1):
        trunk_parts.append({"shape": "capsule", "a": [lean * 0.6, 0, trunk_h * 0.7],
                            "b": [lean + side * crown * 0.45, -0.5, trunk_h + crown * 0.25],
                            "r1": trunk_r * 0.46, "r2": trunk_r * 0.27, "mat": bark})
    bones.append({"name": "trunk", "parent": "root", "parts": trunk_parts})
    cz = trunk_h + crown * 0.55
    # crown clumps: a big back mass, then clumps around it biased to the lit upper-left
    specs = [(0.0, 2.5, 0.1, 0.8)]
    for k in range(clumps):
        a = 2 * math.pi * k / clumps + r.uniform(-0.3, 0.3)
        rad = crown * r.uniform(0.58, 0.72)
        specs.append((math.cos(a) * rad, -abs(math.sin(a)) * 1.5 - 1.5, math.sin(a) * rad * 0.62,
                      r.uniform(0.38, 0.47)))
    specs.append((-crown * 0.18, -3.5, crown * 0.3, 0.45))   # front highlight clump
    for i, (x, y, z, s) in enumerate(specs):
        R = crown * s
        parts = [{"shape": "ellipsoid", "r": [R, R * 0.9, R * 0.85], "mat": leaf}]
        # leafy bumps on the silhouette of each clump
        for j in range(5):
            b = 2 * math.pi * j / 5 + r.uniform(-0.4, 0.4)
            parts.append({"shape": "sphere", "at": [math.cos(b) * R * 0.8, 0, math.sin(b) * R * 0.7],
                          "r": R * r.uniform(0.32, 0.42), "mat": leaf, "blend": 0.8})
        bones.append({"name": "clump%d" % i, "parent": "root", "at": [lean + x, y, cz + z],
                      "blend": 0.8, "parts": parts})
    return {"bones": bones, "clumps": [b["name"] for b in bones if b["name"].startswith("clump")]}


def tree_pine(seed: int = 1, height: float = 52, width: float = 13, tiers: int = 4,
              leaf: str = "leaf", bark: str = "bark", tips: int = 9, droop: float = 1.0) -> Dict:
    r = _rng(seed)
    bones: List[Dict] = [{"name": "root"},
                         {"name": "trunk", "parent": "root",
                          "parts": [{"shape": "capsule", "a": [0, 0, 0], "b": [0, 0, height * 0.35],
                                     "r1": 2.0, "r2": 1.4, "mat": bark}]}]
    base = height * 0.18
    span = height - base
    for t in range(tiers):
        u = t / tiers
        w = width * (1 - u * 0.62) * r.uniform(0.95, 1.05)
        h = span / tiers * 1.55
        z = base + span * u * 0.92
        parts = [{"shape": "cone", "r": w, "h": h, "mat": leaf}]
        # drooping needle tips on the skirt give the saw-tooth silhouette
        for j in range(tips):
            a = 2 * math.pi * j / tips + r.uniform(-0.15, 0.15) + t * 0.7
            tip_r = max(1.3, w * 0.2)
            parts.append({"shape": "cone", "at": [math.cos(a) * w * 0.86, math.sin(a) * w * 0.86, 1.2 * droop],
                          "r": tip_r, "h": tip_r * 2.8, "rot": [180, 0, 0], "mat": leaf, "blend": 0.15})
        bones.append({"name": "clump%d" % t, "parent": "root", "at": [0, 0, z], "blend": 0.15, "parts": parts,
                      "seam": True})
    return {"bones": bones, "clumps": [b["name"] for b in bones if b["name"].startswith("clump")]}


def bush(seed: int = 1, width: float = 12, height: float = 9, clumps: int = 4, leaf: str = "leaf",
         berries: str = "", berry_r: float = 1.3) -> Dict:
    r = _rng(seed)
    bones: List[Dict] = [{"name": "root"}]
    for i in range(clumps):
        x = (i - (clumps - 1) / 2) * width / clumps * 1.1 + r.uniform(-1, 1)
        R = r.uniform(0.35, 0.5) * width * (1.15 if i in (clumps // 2, (clumps - 1) // 2) else 0.9)
        parts = [{"shape": "ellipsoid", "r": [R, R * 0.8, R * 0.8], "mat": leaf}]
        if berries and i % 2 == 0:
            for bx, bz in ((0.3, 0.25), (-0.35, -0.05), (0.05, 0.5)):
                parts.append({"shape": "sphere", "at": [R * bx, -R * 0.8, R * bz], "r": berry_r, "mat": berries})
        bones.append({"name": "clump%d" % i, "parent": "root", "at": [x, -abs(x) * 0.2, R * 0.75], "parts": parts})
    return {"bones": bones, "clumps": [b["name"] for b in bones[1:]]}


def rock(seed: int = 1, size: float = 8, mat: str = "stone") -> Dict:
    r = _rng(seed)
    parts = [{"shape": "box", "at": [0, 0, size * 0.35], "half": [size * 0.6, size * 0.45, size * 0.38],
              "round": size * 0.25, "rot": [0, r.uniform(-8, 8), r.uniform(-25, 25)], "mat": mat}]
    for j in range(2):
        parts.append({"shape": "box", "at": [r.uniform(-size * 0.4, size * 0.4), r.uniform(-1, 1), size * 0.2],
                      "half": [size * 0.35, size * 0.3, size * 0.25], "round": size * 0.15,
                      "rot": [0, 0, r.uniform(-40, 40)], "mat": mat, "blend": 0.5})
    return {"bones": [{"name": "root", "parts": parts}], "clumps": []}


def dead_tree(seed: int = 1, height: float = 40, bark: str = "bark") -> Dict:
    r = _rng(seed)
    parts = [{"shape": "capsule", "a": [0, 0, 0], "b": [1, 0, height * 0.6], "r1": 2.6, "r2": 1.3, "mat": bark}]

    def branch(a, d, length, rad, depth):
        b = [a[0] + d[0] * length, a[1] + d[1] * length, a[2] + d[2] * length]
        parts.append({"shape": "capsule", "a": list(a), "b": b, "r1": rad, "r2": max(0.5, rad * 0.6), "mat": bark})
        if depth > 0:
            for s in (-1, 1):
                ang = s * r.uniform(0.4, 0.8)
                nd = [d[0] * math.cos(ang) - d[2] * math.sin(ang) * 0.6, d[1], d[2] * math.cos(ang) + abs(d[0]) * 0.3]
                n = math.sqrt(sum(v * v for v in nd))
                branch(b, [v / n for v in nd], length * 0.62, rad * 0.65, depth - 1)

    top = [1, 0, height * 0.6]
    branch(top, [-0.6, 0, 0.8], height * 0.3, 1.2, 2)
    branch(top, [0.7, 0, 0.7], height * 0.28, 1.1, 2)
    branch([0.5, 0, height * 0.35], [0.9, 0, 0.45], height * 0.18, 0.9, 1)
    return {"bones": [{"name": "root", "parts": parts}], "clumps": []}


GENERATORS = {"tree_round": tree_round, "tree_pine": tree_pine, "bush": bush, "rock": rock, "dead_tree": dead_tree}


def build_spec(prop: Dict) -> Dict:
    """prop = {name, style, generator, params, frame?, anchor?, sway?} -> full model spec."""
    g = GENERATORS[prop["generator"]](**prop.get("params", {}))
    spec = {k: v for k, v in prop.items() if k not in ("generator", "params")}
    spec["bones"] = g["bones"]
    spec["rig"] = "prop"
    spec.setdefault("directions", ["S"])
    sway = prop.get("sway", 1 if g["clumps"] else 0)
    spec["custom_clips"] = {"idle": {"frames": [{"pose": {}}], "loop": True}}
    spec["clips"] = ["idle"]
    if sway and g["clumps"]:
        # travelling wave across clumps in whole pixels (pp/layers.py sway)
        spec.setdefault("life", {})["sway"] = {"bones": g["clumps"], "px": sway * 0.9, "frames": 8, "wave": 0.9}
    return spec
