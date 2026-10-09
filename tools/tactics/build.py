"""Build the Crisp Tactics style: every scene (valley, harbour; valley and autumn biomes) and the stag walk sheets.

  python3 tools/tactics/build.py                  # all scenes + sheets -> out/<scene>/, out/tactics_stag[_autumn]/
  python3 tools/tactics/build.py --only tactics_valley --frames 1

Per scene: scene.json (re-render with python3 -m pp.iso), noon_1x.png, noon_1x.gif (the ambient loop, 1x) and
noon.png (an integer-scaled preview). Per sheet: <name>_walk.png + <name>.json (8 directions, held-key walk).
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pp import iso  # noqa: E402
from tools.tactics import kit, scenes  # noqa: E402

SCENES = {"tactics_valley": (scenes.valley, "valley"), "tactics_autumn": (scenes.valley, "autumn"),
          "tactics_harbour_valley": (scenes.harbour, "valley"), "tactics_harbour_autumn": (scenes.harbour, "autumn")}
ANIMATED = ("tactics_valley", "tactics_harbour_valley")     # the autumn scenes ship as stills
LINE = {"ink_ramp": "ink", "ink_tone": 1, "drop_contrast": 2.0}  # sprites: the lit-side selout everywhere


def stag_pose(facing, legs):
    """The stag with its body centred on the origin. Iso has four true facings (head at -x = NW, -y = NE, mirrored
    for SE / SW); the screen cardinals borrow the nearest diagonal."""
    f = {"S": "SW", "SE": "SE", "E": "SE", "NE": "NE", "N": "NE", "NW": "NW", "W": "NW", "SW": "SW"}[facing]
    if f in ("NW", "SE"):
        ps = kit.stag(0, 0, z=0, facing="x", g=1, legs=legs)
        ps = [iso.mirror(p, 0, 5.5) for p in ps] if f == "SE" else ps
        dx, dy = -11, -3
    else:
        ps = kit.stag(0, 0, z=0, facing="y", g=1, legs=legs)
        ps = [iso.mirror(p, 1, 5.5) for p in ps] if f == "SW" else ps
        dx, dy = -3, -11
    return [iso.shift(iso.scale(p, scenes.K), dx, dy) for p in ps]


def stag_sheet(biome, out_root):
    st = scenes.style(biome)
    base = {"light": st["light"], "palette": st["ramps"], "materials": scenes.materials(biome)}
    name = "tactics_stag" + ("_autumn" if biome == "autumn" else "")
    sheet, meta = iso.animal_sheet(base, lambda d, k: stag_pose(d, (0, 0, 1, 1)[k]), 4, 52, 56, (26, 46), LINE,
                                   name=name, style=st["name"])
    out = out_root / name
    out.mkdir(parents=True, exist_ok=True)
    sheet.save(out / (name + "_walk.png"))
    (out / (name + ".json")).write_text(json.dumps(meta, indent=1))
    return out / (name + "_walk.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated scene names (default: all)")
    ap.add_argument("--frames", type=int, default=24, help="ambient loop length for the animated scenes")
    ap.add_argument("--out", default=str(ROOT / "out"))
    a = ap.parse_args()
    out_root = Path(a.out)
    names = a.only.split(",") if a.only else list(SCENES)
    for name in names:
        fn, biome = SCENES[name]
        t = time.time()
        spec = fn(biome)
        scene = iso.Scene(spec)
        n = a.frames if name in ANIMATED else 1
        frames = [iso.render_frame(scene, f, n) for f in range(n)]
        out = out_root / name
        out.mkdir(parents=True, exist_ok=True)
        (out / "scene.json").write_text(json.dumps(spec))
        print(iso.save_frames(out, frames, "noon", 120, preview=3), "(%.1fs)" % (time.time() - t))
    if not a.only:
        for biome in ("valley", "autumn"):
            print(stag_sheet(biome, out_root))


if __name__ == "__main__":
    main()
