"""The arena's maps. Each map is a package here: its place in metres (place.py), its palette (palette.py), its biome
(biome.py: materials, ramps, zone-budget overrides, the ground and sky painters, the viewer's ambience), its level
hooks (level.py: collision shapes of its props, spawns, objectives, chokepoints), its Blender builders (blender.py)
and its painted art (art/). The engine (arena/*.py) is shared and binds to ONE map at a time:

    from arena import maps
    maps.activate("emberleaf")        # every engine module now reads that map (arena.place is its place, ...)

`python3 -m arena <cmd> --map NAME` activates NAME first. With no --map the default is Hushfall Crossing.
"""
from __future__ import annotations

import importlib
import sys

MAPS = {"hushfall": "hushfall", "emberleaf": "emberleaf"}      # name -> package (arena.maps.<package>)
ALIASES = {"hushfall_crossing": "hushfall", "emberleaf_hollow": "emberleaf"}
DEFAULT = "hushfall"
_active = None
# engine modules that keep derived module globals; activate() rebinds them (each defines _bind())
ENGINE = ("zones", "paint", "layers", "level", "check", "build", "sheets")


def names():
    return list(MAPS)


def get(name: str):
    # the engine's zones first: a biome imports it, and it binds to the active map's biome on import
    if "arena.zones" not in sys.modules:
        importlib.import_module("arena.zones")
    key = ALIASES.get(name, name)
    if key not in MAPS:
        raise SystemExit(f"arena: no map {name!r} (maps: {', '.join(MAPS)})")
    return importlib.import_module(f"arena.maps.{MAPS[key]}")


def active():
    global _active
    if _active is None:
        _active = get(DEFAULT)
    return _active


def activate(name: str):
    """make NAME the map every engine module reads; returns its package"""
    global _active
    m = get(name)
    if _active is m:
        return m
    _active = m
    for mod in ENGINE:
        full = f"arena.{mod}"
        if full in sys.modules and hasattr(sys.modules[full], "_bind"):
            sys.modules[full]._bind()
    return m
