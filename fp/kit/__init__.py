"""The Hushfall kit: one builder per asset. `python3 -m fp assets` lists them.

A builder is `build(seed=0) -> Asset`. The asset's origin is its ground point (x=z=0 at the base, y=0 on the ground);
+x is the asset's right, -z its front (the way a car drives). Layouts place assets by name and seed ("pine:3").
Each builder file belongs to one artist at a time; shared shapes live in fp/mesh.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..mesh import Lines, Mesh


@dataclass
class Asset:
    mesh: Mesh
    lines: Optional[Lines] = None
    collide: Optional[float] = None          # radius of the walk-blocking circle around the origin (metres)
    box: Optional[tuple] = None              # or a blocking box (half-width x, half-depth z) in the asset's frame
    lights: list = field(default_factory=list)   # spot lights in the asset's frame (see fp/README.md)
    anchors: dict = field(default_factory=dict)  # named points the layout uses (wire ends, rope eyes)
    sink: float = 0.0                        # push the asset this far into the ground when placed
    shadow: bool = True                      # casts into the shadow map


def registry():
    from . import car, fence, grass, pine, pole, shrub
    return {
        "pine": pine.build,
        "pine_small": pine.build_small,
        "shrub": shrub.build,
        "car": car.build,
        "pole": pole.build,
        "post": fence.build,
        "grass": grass.build,
    }


def build(name: str, seed: int = 0) -> Asset:
    reg = registry()
    if name not in reg:
        raise SystemExit("fp: no asset %r (have: %s)" % (name, ", ".join(sorted(reg))))
    return reg[name](seed)


def describe() -> dict:
    return {k: (v.__doc__ or "").strip().splitlines()[0] if v.__doc__ else "" for k, v in registry().items()}
