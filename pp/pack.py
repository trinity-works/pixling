"""Assemble an itch.io-ready pack from build dirs."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List

import numpy as np

from .aseprite import export_build
from .color import rgb_to_hex
from .forge import load_style
from .paths import PACKS
from .io import save_png
from .scene import compose, silhouettes

README = """{title}
{line}

{n} animated sprites, {style} style. Pixel art at 1x (scale by whole numbers only: 2x, 3x, 4x).

Layout
- sheets/<asset>_<clip>.png: rows = directions {dirs}; columns = frames.
- Every frame is {ms} ms ({fps:.1f} fps). Holds are baked in as repeated frames, so play at a constant rate.
- <asset>.json: frame size, feet anchor pixel, per-frame events (hit, footstep, cast, hurt) and
  locomotion speed (px per cycle, so feet don't slide).
- aseprite/: editable sources, one tag per clip_direction.
- gifs/: previews.
- palette.png / palette.gpl: the full locked palette ({ncol} colours). Every sprite uses only these.

Assets
{assets}
"""


def build_pack(name: str, build_dirs: List[str], style_name: str, title: str = "") -> Path:
    out = PACKS / name
    if out.exists():
        shutil.rmtree(out)
    (out / "sheets").mkdir(parents=True)
    (out / "gifs").mkdir()
    (out / "aseprite").mkdir()
    style = load_style(style_name)
    pal = style.palette()
    lines = []
    dirs = None
    fx_dirs = [Path(d) for d in build_dirs if "clips" not in json.loads((Path(d) / (Path(d).name + ".json")).read_text())]
    build_dirs = [d for d in build_dirs if Path(d) not in fx_dirs]
    if fx_dirs:
        (out / "vfx").mkdir()
    for d in fx_dirs:
        shutil.copytree(d, out / "vfx" / d.name)
        m = json.loads((d / (d.name + ".json")).read_text())
        lines.append("- vfx %s: %d frames of %dx%d (%s)" % (d.name, m["frames"], m["frame_w"], m["frame_h"], m["kind"]))
    for d in build_dirs:
        d = Path(d)
        meta = json.loads((d / (d.name + ".json")).read_text())
        dirs = dirs or meta["directions"]
        for c in meta["clips"].values():
            shutil.copy(d / c["sheet"], out / "sheets" / c["sheet"])
        shutil.copy(d / (d.name + ".json"), out / "sheets" / (d.name + ".json"))
        g = out / "gifs" / d.name
        if (d / "gif").exists():
            shutil.copytree(d / "gif", g)
        export_build(d, out / "aseprite" / (d.name + ".aseprite"), palette=pal)
        clips = ", ".join("%s (%d)" % (k, len(v["frames"])) for k, v in meta["clips"].items())
        lines.append("- %s: %dx%d frames, %d directions — %s" % (d.name, meta["frame_w"], meta["frame_h"],
                                                              len(meta["directions"]), clips))
    sw = np.zeros((8, 8 * len(pal), 4), np.uint8)
    for i, c in enumerate(pal):
        sw[:, i * 8:(i + 1) * 8] = (*c, 255)
    save_png(sw, out / "palette.png")
    gpl = "GIMP Palette\nName: %s\nColumns: 8\n#\n" % style.name
    gpl += "".join("%3d %3d %3d %s\n" % (c[0], c[1], c[2], rgb_to_hex(c)) for c in pal)
    (out / "palette.gpl").write_text(gpl)
    chars = [d for d in build_dirs if len(json.loads((Path(d) / (Path(d).name + ".json")).read_text())["directions"]) > 1]
    compose(build_dirs, style_name, out=out / "preview.png", scale=4)
    if chars:
        silhouettes(chars, out=out / "lineup.png")
    t = title or name.replace("_", " ").title()
    (out / "README.txt").write_text(README.format(title=t, line="=" * len(t), n=len(build_dirs), style=style.name,
                                                  dirs=", ".join(dirs or []), ms=75, fps=1000 / 75, ncol=len(pal),
                                                  assets="\n".join(lines)))
    return out
