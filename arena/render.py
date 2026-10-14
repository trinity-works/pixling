"""Run the arena's Blender pass (the map as data) into a work folder.

A python with the bpy module (ARENA_BPY, or FP_BPY) or a blender binary (ARENA_BLENDER / FP_BLENDER / on PATH).
EEVEE wants a display, so the run goes under xvfb-run when there is none.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from . import place as P

HERE = Path(__file__).resolve().parent


def blender_cmd():
    for env in ("ARENA_BLENDER", "FP_BLENDER"):
        if os.environ.get(env):
            return [os.environ[env], "-b", "--python-exit-code", "1", "-P"]
    for env in ("ARENA_BPY", "FP_BPY"):
        if os.environ.get(env):
            return [os.environ[env]]
    b = shutil.which("blender")
    return [b, "-b", "--python-exit-code", "1", "-P"] if b else None


def blender(script: Path, *args) -> None:
    cmd = blender_cmd()
    if cmd is None:
        raise SystemExit("arena: no Blender. Set ARENA_BPY=/path/to/python-with-bpy or ARENA_BLENDER=/path/to/blender")
    full = cmd + [str(script), "--"] + [str(a) for a in args]
    if not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        full = ["xvfb-run", "-a", "-s", "-screen 0 1280x720x24"] + full
    t = time.time()
    subprocess.run(full, check=True)
    print(f"arena: {script.name} took {time.time() - t:.0f} s")


def textures(work: Path) -> None:
    """the card atlases (brush dabs, puffs): the fp engine's, so the arena's spruces and clouds are the same hand"""
    from fp.paint3d import textures as fp_textures
    fp_textures(work / "tex")


def render_map(work: Path, samples: int = 1, scale: float = 1.0, only: str = None) -> None:
    """export the active map's place, then run the Blender driver (blender/arena.py) with the map's builders
    (arena/maps/<name>/blender.py) and its materials"""
    from .maps import active
    import json
    M = active()
    work = Path(work)
    P.export(work)
    spec = json.loads((work / "scene3d.json").read_text())
    spec.update(mats=M.biome.MAT, builder=str(M.BLENDER), light=getattr(M.biome, "LIGHT", {}))
    (work / "scene3d.json").write_text(json.dumps(spec))
    textures(work)
    if hasattr(M.biome, "textures"):
        M.biome.textures(work / "tex")
    only = only or ",".join(M.biome.RENDER_PASSES)
    blender(HERE / "blender" / "arena.py", work, samples, scale, only)
