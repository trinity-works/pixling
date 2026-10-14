"""Emberleaf Hollow: a kill map (team annihilation, no objectives) in a clearing of red-crowned trees and dark pines on a
forested plateau; past its back edge a valley of canopy, a river, far hills, the sky. Camera 55
degrees (arena/STYLE.md: the camera family).

    place.py    the place in metres (plan, terrain, layout with zones, the back's bands)
    palette.py  the midday autumn palette, the embers' hues and the units' reserved hue bands (gold, violet)
    biome.py    materials and ramps, zone overrides, the ground painter (grass patches, dirt, cobbles, tufts,
                flowers, water), the sky, the layers and the viewer's ambience (leaves, motes, the pond's shimmer)
    level.py    the level hooks: prop shapes, spawns, the fairness targets, chokepoints
    blender.py  the Blender builders (red-crowned trees, pines, bushes, boulders, stumps, the log, ruin walls,
                waystones, lanterns, the pond; the valley's canopy, river, hills and cumulus)
    art/        the painted map and its level (committed)
"""
from __future__ import annotations

import importlib
from pathlib import Path

KEY = "emberleaf"
NAME = "emberleaf_hollow"
TITLE = "Emberleaf Hollow"
HERE = Path(__file__).resolve().parent
ART = HERE / "art"
BLENDER = HERE / "blender.py"
PARTS = ("place", "palette", "biome", "level")


def __getattr__(name):
    if name in PARTS:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(name)
