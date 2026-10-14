"""Hushfall Crossing: a ledge in the winter forest above a sea of dusk cloud, laid out as a two-camp arena (two camps,
a ruin terrace with the Stones, a bridge to an overlook, a corridor under it). Camera 40 degrees.

    place.py    the place in metres (plan, terrain, ruin, layout with zones, the scenery's bands, the cloud layers)
    palette.py  the dusk palette, the sun's hues and the units' reserved hue bands
    biome.py    materials and ramps, the dusk sky, rims, the sunk cliffs, the layers and the viewer's ambience
    level.py    the level hooks: prop shapes, the bridge deck, ramps, spawns, objectives, chokepoints
    blender.py  the Blender builders (spruces, the ruin, camps, bridge; the forest ridges and the cumulus)
    art/        the painted map and its level (committed)
"""
from __future__ import annotations

import importlib
from pathlib import Path

KEY = "hushfall"
NAME = "hushfall_crossing"
TITLE = "Hushfall Crossing"
HERE = Path(__file__).resolve().parent
ART = HERE / "art"
BLENDER = HERE / "blender.py"
PARTS = ("place", "palette", "biome", "level")


def __getattr__(name):
    if name in PARTS:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(name)
