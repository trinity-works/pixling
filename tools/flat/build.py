"""Build the Flat Minimal style: both biome scenes at noon and night (dither optional) and the animal sheets.

  python3 tools/flat/build.py                     # flat_forest, flat_dunes -> out/<scene>/; sheets -> out/flat_deer...
  python3 tools/flat/build.py --only flat_forest --frames 1

Per scene: scene.json (re-render with python3 -m pp.iso), noon_1x.png, noon_1x.gif (forest: the ambient loop),
night_1x.png, night_dither_1x.png (the optional dither filter) and x4 previews of each.
Sheets: flat_deer (8-direction held-key walk) and flat_heron (8-direction idle with a fishing dip), per biome.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pp import iso  # noqa: E402
from tools.flat import kit, scenes  # noqa: E402

SCENES = {"flat_forest": "forest", "flat_dunes": "dunes"}
ANIMATED = ("flat_forest",)
# iso has four true facings: built along x the head points to -x (screen NW); swapped to y it points NE;
# mirrored for SE / SW. The screen cardinals borrow the nearest diagonal.
FACING = {"S": "SW", "SE": "SE", "E": "SE", "NE": "NE", "N": "NE", "NW": "NW", "W": "NW", "SW": "SW"}


def facing(polys, f, cx, cy):
    """Turn polys built along x (centred on cx, cy) to an iso facing and centre them on the origin."""
    if f in ("NE", "SW"):
        polys = [iso.swap_xy(p) for p in polys]
        cx, cy = cy, cx
    if f == "SE":
        polys = [iso.mirror(p, 0, cx) for p in polys]
    if f == "SW":
        polys = [iso.mirror(p, 1, cy) for p in polys]
    return [iso.shift(p, -cx, -cy) for p in polys]


def sheets(biome, out_root):
    spec = scenes.scene(biome)
    base = {"light": spec["light"], "palette": spec["palette"], "materials": spec["materials"]}
    mats = ("deer", "antler")
    jobs = {
        "flat_deer": (lambda d, k: facing(kit.deer(0, 0, z=0, mats=mats, legs=(0, 0, 1, 1)[k]), FACING[d], 3, 1),
                      4, 24, 22, (12, 18), 140, "walk"),
        "flat_heron": (lambda d, k: facing(kit.heron(0, 0, 0, dip=(0, 0, 0, 1)[k]), FACING[d], 2, 1),
                       4, 20, 22, (10, 18), 200, "idle"),
    }
    out = []
    for name, (pose, keys, fw, fh, anchor, ms, clip) in jobs.items():
        name = name + ("_dunes" if biome == "dunes" else "")
        sheet, meta = iso.animal_sheet(base, pose, keys, fw, fh, anchor, None, ms, name=name, style=spec["name"],
                                       clip=clip)
        d = out_root / name
        d.mkdir(parents=True, exist_ok=True)
        sheet.save(d / ("%s_%s.png" % (name, clip)))
        (d / (name + ".json")).write_text(json.dumps(meta, indent=1))
        out.append(d / ("%s_%s.png" % (name, clip)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated scene names (default: all)")
    ap.add_argument("--frames", type=int, default=24, help="ambient loop length for the animated scene")
    ap.add_argument("--out", default=str(ROOT / "out"))
    a = ap.parse_args()
    out_root = Path(a.out)
    names = a.only.split(",") if a.only else list(SCENES)
    for name in names:
        t = time.time()
        spec = scenes.scene(SCENES[name])
        scene = iso.Scene(spec)
        out = out_root / name
        out.mkdir(parents=True, exist_ok=True)
        (out / "scene.json").write_text(json.dumps(spec))
        n = a.frames if name in ANIMATED else 1
        iso.save_frames(out, [iso.render_frame(scene, f, n) for f in range(n)], "noon", 120, preview=4)
        iso.save_frames(out, [iso.render_frame(scene, 0, 1, "night")], "night", preview=4)
        iso.save_frames(out, [iso.render_frame(scene, 0, 1, "night", "night")], "night_dither", preview=4)
        print(out, "(%.1fs)" % (time.time() - t))
    if not a.only:
        for biome in SCENES.values():
            for p in sheets(biome, out_root):
                print(p)


if __name__ == "__main__":
    main()
