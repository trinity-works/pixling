"""CLI: python3 -m arena <command> [--map NAME]   battle maps for your own units, one shared engine, one art style

  maps: hushfall (Hushfall Crossing, the default), emberleaf (Emberleaf Hollow). Every command reads --map NAME; the
  map's art lives in arena/maps/NAME/art/, its work folder and outputs in out/arena/NAME/ (Hushfall: out/arena/).

  bundle [--out FILE]            the map viewer as ONE html that opens from disk (default out/arena/arena.html); needs
                                 no Blender: the painted art is committed in arena/art/
  shots [--out DIR]              bundle, then stills through the real viewer (Playwright, file://): the overview, the
                                 overlays (grid, zones, scale, colliders, nav, LOS, paths, agent), close crops, the
                                 clouds at two times; zone map, grey and squint; page errors
  perf                           bundle, then frame time in Chromium (rAF) at 1280x720 and 1920x1080 (arena/perf.mjs)
  export [--out FILE]            the level as JSON for your units (walk grid, heights, levels, spawns, objectives,
                                 chokepoints, routes, dimensions); the same file as arena/art/level.json
  paint [--work DIR] [--scale 0.5]
                                 re-render in Blender and repaint arena/art/ (ARENA_BPY=python-with-bpy or
                                 ARENA_BLENDER=blender; ~2.5 min at 1 sample)
  repaint [--work DIR]           repaint arena/art/ from the last render (tune RAMPS in paint.py, ZONES in zones.py;
                                 no Blender): the map, its moving layers and tree sway (layers.py), the level
  plan [--out FILE]              a top-down plan of the walk grid
  level                          rebuild art/level.json from the place data (collision, nav, LOS, zones; no Blender)
  check [--quick]                validate the level for a game: reachability, fairness, spawn safety, chokepoints,
                                 stuck tests, colliders against the painted art (exit 1 on a failure)
  lint                           measure art/map.png against the zone budgets (zones.py): per-zone values,
                                 saturation, contrast and texture energy, the sun's pinks, the units' hues
  zones [--out DIR]              looking aids for art/map.png: the zone map, greyscale, and a squint (blurred) grey
  palette [--out FILE]           the palette by role, and the value structure each zone shows
  scale [--out FILE]             the map under a 1 m grid with people 1.7 m tall and the key dimensions
  family [--out FILE]            every map side by side at the same scale with a 1.7 m person and its palette
  maps                           the maps and whether their art is painted
"""
from __future__ import annotations

import argparse
import json

from . import maps
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
from pp.paths import OUT_ROOT as ROOT   # a checkout writes out/ in the repo; an installed pixling, in the current folder


def main(argv=None):
    ap = argparse.ArgumentParser(prog="arena", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["bundle", "shots", "export", "paint", "repaint", "plan", "lint", "zones", "palette",
                                    "scale", "level", "check", "perf", "family", "maps"])
    ap.add_argument("--map", default=None, help="the map (default hushfall); maps: " + ", ".join(maps.names()))
    ap.add_argument("--out", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--art", default=None, help="paint / repaint into this folder instead of the map's art/ (tests)")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=1)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    M = maps.activate(a.map or maps.DEFAULT)
    # Hushfall keeps its old out/arena/ folders; other maps get out/arena/NAME/
    OUT = ROOT / "out" / "arena" if M.KEY == "hushfall" else ROOT / "out" / "arena" / M.KEY
    a.work = a.work or str(OUT / "work")
    from . import build, paint, place, render, sheets, zones

    if a.cmd == "maps":
        for n in maps.names():
            m = maps.get(n)
            print(f"{n:10s} {m.TITLE:20s} {'art ok' if (m.ART / 'map.png').exists() else 'no art yet'}  {m.HERE}")
        return 0
    if a.cmd == "family":
        print("arena: family ->", sheets.family(Path(a.out or ROOT / "out" / "arena" / "family.png")))
        return 0
    if a.cmd == "level":
        w = paint.level_json(build.ART)
        print(f"arena: level -> {build.ART / 'level.json'} (v{w['version']}, {len(w['colliders']['shapes'])} shapes)")
        return 0
    if a.cmd == "check":
        from . import check
        return check.run(build.ART, quick=a.quick)
    if a.cmd == "lint":
        return zones.lint(build.ART)
    if a.cmd == "zones":
        odir = Path(a.out or OUT / "zones")
        sheets.looks(build.ART / "map.png", build.ART / "zones.png", odir, "map")
        print("arena: zone map, grey and squint ->", odir)
        return 0
    if a.cmd == "palette":
        print("arena: palette ->", sheets.palette_strip(Path(a.out or OUT / "palette.png"), build.ART))
        return 0
    if a.cmd == "scale":
        print("arena: scale ->", sheets.scale_sheet(build.ART, Path(a.out or OUT / "scale.png")))
        return 0
    if a.cmd == "export":
        out = Path(a.out or OUT / f"{M.NAME}.level.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        w = json.loads((build.ART / "level.json").read_text())
        out.write_text(json.dumps(w, indent=1))
        print(f"arena: level -> {out} (grid {w['grid']['nu']} x {w['grid']['nv']} cells of {w['grid']['cell']} m)")
        return 0
    if a.cmd in ("paint", "repaint"):
        work = Path(a.work)
        if a.cmd == "paint":
            render.render_map(work, a.samples, a.scale)
        from . import layers
        art = Path(a.art) if a.art else build.ART
        c0 = paint.composite(work)
        print(paint.paint_map(work, art, c=c0))
        print("arena: layers", layers.build(work, art, c0))
        paint.level_json(art)
        print("arena: art ->", art)
        return 0
    if a.cmd == "plan":
        out = Path(a.out or OUT / "plan.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        import numpy as np
        g = place.walk_grid(place.layout())
        cols = np.array([[40, 40, 60], [150, 175, 180], [190, 160, 140]], np.uint8)
        Image.fromarray(cols[g["kind"]][::-1]).resize((g["kind"].shape[1] * 6, g["kind"].shape[0] * 6), Image.NEAREST).save(out)
        print("arena: plan ->", out)
        return 0
    if a.cmd == "bundle":
        p = build.bundle(Path(a.out or OUT / "arena.html"))
        print(f"arena: {p} ({p.stat().st_size / 1e6:.1f} MB) - open it in a browser")
        return 0
    if a.cmd == "perf":
        page = build.bundle(OUT / "arena.html")
        return subprocess.run(["node", str(HERE / "perf.mjs"), str(page.resolve()), "5"]).returncode
    if a.cmd == "shots":
        odir = Path(a.out or OUT / "shots")
        odir.mkdir(parents=True, exist_ok=True)
        page = build.bundle(odir / "arena.html")
        return shots(page, odir, M)
    return 0


SHOTS = [
    # (name, query, size): the viewer, paused, at map pixel `at`
    ("overview", "pause=1&t=6&zoom=1&at=960,540&hud=0", (1920, 1080)),
    ("overview_ui", "pause=1&t=6&zoom=1&at=960,540", (1920, 1080)),
    ("overlay_grid", "pause=1&t=6&zoom=1&at=960,540&overlay=grid&snow=0", (1920, 1080)),
    ("overlay_zones", "pause=1&t=6&zoom=1&at=960,540&overlay=zones&snow=0", (1920, 1080)),
    ("overlay_scale", "pause=1&t=6&zoom=1&at=960,540&overlay=scale&snow=0", (1920, 1080)),
    ("crop_high_ground", "pause=1&t=6&zoom=2&at=960,560&hud=0", (1200, 760)),
    ("crop_bridge", "pause=1&t=6&zoom=3&at=960,470&hud=0", (1200, 760)),
    ("crop_camp", "pause=1&t=6&zoom=2&at=330,620&hud=0", (1200, 760)),
    ("crop_background", "pause=1&t=6&zoom=2&at=960,170&hud=0", (1600, 600)),
    ("crop_scale_deck", "pause=1&t=6&zoom=3&at=960,560&overlay=scale&snow=0&hud=0", (1200, 760)),
    # the game overlays: colliders per level, the nav, sight from the ground and from the overlook, paths, the agent
    ("colliders", "pause=1&t=6&zoom=1&at=960,540&overlay=colliders&snow=0", (1920, 1080)),
    ("colliders_ground", "pause=1&t=6&zoom=1&at=960,540&overlay=colliders&level=0&snow=0", (1920, 1080)),
    ("colliders_terrace", "pause=1&t=6&zoom=1&at=960,540&overlay=colliders&level=1&snow=0", (1920, 1080)),
    ("colliders_deck", "pause=1&t=6&zoom=3&at=960,470&overlay=colliders&level=2&snow=0", (1200, 760)),
    ("nav", "pause=1&t=6&zoom=1&at=960,540&overlay=nav&snow=0", (1920, 1080)),
    ("los_ground", "pause=1&t=6&zoom=1&at=960,540&overlay=los&los=-14,-1,0&losstep=1&snow=0", (1920, 1080)),
    ("los_overlook", "pause=1&t=6&zoom=1&at=960,540&overlay=los&los=-4,15,0&losstep=1&snow=0", (1920, 1080)),
    ("paths", "pause=1&t=6&zoom=1&at=960,540&overlay=paths&cursor=0,13.5,0&snow=0", (1920, 1080)),
    ("agent", "pause=1&t=6&zoom=2&at=960,470&overlay=agent&target=0,13.5,0&walk=150&snow=0", (1200, 760)),
    ("clouds_t0", "pause=1&t=0&zoom=1&at=960,540&hud=0&snow=0", (1920, 1080)),
    ("clouds_t120", "pause=1&t=120&zoom=1&at=960,540&hud=0&snow=0", (1920, 1080)),
    # the overlay buttons toggle (clicked in the page, checked in its state); the shot shows all three on
    ("toggles", "pause=1&t=6&zoom=1&at=960,540", (1920, 1080),
     ["#b-grid", "#b-zones", "#b-scale", "#b-zones", "#b-colliders", "#b-nav", "#b-los", "#b-paths", "#b-agent",
      "#b-nav", "#b-r", "#b-lv"],
     "window.__arena.show.grid && !window.__arena.show.zones && window.__arena.show.scale && "
     "window.__arena.show.colliders && !window.__arena.show.nav && window.__arena.show.los && "
     "window.__arena.show.paths && window.__arena.show.agent"),
]


def shots(page: Path, odir: Path, M=None) -> int:
    M = M or maps.active()
    node = shutil.which("node")
    if not node:
        print("arena shots: needs node + playwright")
        return 1
    job = dict(page=str(page.resolve()), size=[1600, 900], shots=[])
    groups = {}
    for name, q, size, *more in getattr(M.biome, "SHOTS", SHOTS):
        sh = dict(query=q, out=str(odir / f"{name}.png"))
        if more:
            sh.update(clicks=more[0], expect=more[1])
        groups.setdefault(size, []).append(sh)
    rc = 0
    for size, shots_ in groups.items():
        job.update(size=list(size), shots=shots_)
        r = subprocess.run([node, str(HERE / "shots.mjs"), json.dumps(job)], capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode or "ERRORS" in r.stdout:
            print(r.stderr[-2000:])
            rc = 1
    from . import build, sheets
    if (odir / "overview.png").exists():
        sheets.looks(odir / "overview.png", build.ART / "zones.png", odir, "overview")
    return rc


if __name__ == "__main__":
    sys.exit(main())
