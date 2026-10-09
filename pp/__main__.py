"""CLI: python3 -m pp <command> ... (the same CLI as `pixling`; run it without arguments for the list)

  build <spec.json> [--out DIR] [--dirs S,E,...] [--clips idle,walk]

This file holds the sprite-forge commands; pp/cli.py routes everything else (guide, code, styles, map, reel, scenario).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .forge import Forge, load_json, load_spec, OUT


def main(argv=None) -> int:
    from .cli import main as cli_main
    return cli_main(argv)


def engine_main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pixling")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="render a character/creature spec into sheets + gifs")
    b.add_argument("spec")
    b.add_argument("--out")
    b.add_argument("--dirs")
    b.add_argument("--clips")
    b.add_argument("--maps", help="2D-HD maps to export beside the sheets: normal,height")
    r = sub.add_parser("review", help="zoomed grid of clips x directions from a build dir")
    r.add_argument("build_dir")
    r.add_argument("--clips")
    r.add_argument("--dirs")
    r.add_argument("--scale", type=int, default=5)
    r.add_argument("--bg", help="background hex (default: the build's style bg)")
    r.add_argument("--onion", action="store_true", help="overlay each clip's frames in one cell (motion check)")
    sc = sub.add_parser("scene", help="line up built sprites on the style's ground at game scale")
    sc.add_argument("build_dirs", nargs="+")
    sc.add_argument("--style")
    sc.add_argument("--clip", default="idle")
    sc.add_argument("--dir", default="S")
    sc.add_argument("--scale", type=int, default=4)
    sc.add_argument("--out")
    li = sub.add_parser("lint", help="short quality lints for build dirs (+ family silhouette check)")
    li.add_argument("build_dirs", nargs="+")
    si = sub.add_parser("silhouettes", help="white-fill silhouette row + colour row (family design check)")
    si.add_argument("build_dirs", nargs="+")
    si.add_argument("--dir", default="S")
    si.add_argument("--out")
    sz = sub.add_parser("sizes", help="size lineup: builds sorted by height with the size-class rulers")
    sz.add_argument("build_dirs", nargs="+")
    sz.add_argument("--scale", type=int, default=4)
    sz.add_argument("--out")
    ma = sub.add_parser("materials", help="list a style's materials and ramps")
    ma.add_argument("style")
    fx = sub.add_parser("fx", help="render a standalone VFX sheet + gif")
    fx.add_argument("kind")
    fx.add_argument("--style", required=True)
    fx.add_argument("--ramp", help="style ramp name (or comma list of hex)")
    fx.add_argument("--name")
    fx.add_argument("--param", action="append", default=[], help="k=v (json value)")
    pk = sub.add_parser("pack", help="assemble an itch.io pack from build dirs")
    pk.add_argument("name")
    pk.add_argument("build_dirs", nargs="+")
    pk.add_argument("--style", required=True)
    pk.add_argument("--title", default="")
    ins = sub.add_parser("inspect", help="one frame's hidden data: bone/material maps + a text table")
    ins.add_argument("spec")
    ins.add_argument("--clip", default="idle")
    ins.add_argument("--dir", default="S")
    ins.add_argument("--frame", type=int, default=0)
    ins.add_argument("--scale", type=int, default=8)
    ins.add_argument("--no-grid", action="store_true", help="skip the glyph grid in the text")
    ins.add_argument("--out")
    va = sub.add_parser("variants", help="build labelled variants of a spec side by side; --apply N keeps one")
    va.add_argument("spec")
    va.add_argument("--vary", action="append", default=[], help="key=a,b,c or key=lo..hi (dotted spec path)")
    va.add_argument("--clips")
    va.add_argument("--dirs")
    va.add_argument("--sample", type=int, default=0, help="rows to draw when a --vary is a range (default 6)")
    va.add_argument("--seed", type=int, default=0)
    va.add_argument("--scale", type=int, default=3)
    va.add_argument("--apply", type=int, help="write this row's overrides (from the last run) into the spec")
    stt = sub.add_parser("states", help="build a building's ruin, construction stages and finished state")
    stt.add_argument("spec")
    stt.add_argument("--states", default="ruin,build:0.25,build:0.5,build:0.75,build:0.9,built")
    stt.add_argument("--out", default="out")
    stt.add_argument("--scale", type=int, default=3)
    lt = sub.add_parser("light", help="a map at every hour: day, golden, sunset, dusk, night (+ light.json for engines)")
    lt.add_argument("spec")
    lt.add_argument("--hours", default="0,1.2,2.2,3.1,4", help="levels 0 day .. 5 deep night")
    lt.add_argument("--out")
    lt.add_argument("--builds")
    lt.add_argument("--gif", action="store_true", help="also a day -> night -> day loop")
    lt.add_argument("--scale", type=int, default=2)
    ex = sub.add_parser("aseprite", help="export a build dir to .aseprite")
    ex.add_argument("build_dir")
    pc = sub.add_parser("pixcheck", help="pixel cleanliness of a 1x render: orphans, whiskers, broken stairs")
    pc.add_argument("png")
    pc.add_argument("--mark", help="write a 4x marked image here")
    a = ap.parse_args(argv)
    if a.cmd == "pixcheck":
        from .pixcheck import check
        print(check(a.png, a.mark))
        return 0
    if a.cmd == "light":
        from .light import run as light_run
        print(light_run(a.spec, [float(h) for h in a.hours.split(",")], a.out, a.builds, a.gif, a.scale))
        return
    if a.cmd == "states":
        from .states import run
        for p_ in run(a.spec, a.states.split(","), a.out, a.scale):
            print(p_)
        return
    if a.cmd == "variants":
        from . import variants as V
        if a.apply is not None:
            print("applied v%02d: %s" % (a.apply, V.label(V.apply(a.spec, a.apply))))
            return 0
        if not a.vary:
            ap.error("variants needs at least one --vary (or --apply N)")
        still, anim, lines = V.run(a.spec, a.vary, a.clips.split(",") if a.clips else None,
                                   a.dirs.split(",") if a.dirs else None, a.sample, a.seed, a.scale)
        print("\n".join(lines))
        print(still)
        print(anim)
        return 0
    if a.cmd == "inspect":
        from .inspect import inspect
        path, txt = inspect(a.spec, a.clip, a.dir, a.frame, a.scale, a.out, not a.no_grid)
        print(txt)
        print(path)
        return 0
    if a.cmd == "pack":
        from .pack import build_pack
        print(build_pack(a.name, a.build_dirs, a.style, a.title))
        return 0
    if a.cmd == "aseprite":
        from .aseprite import export_build
        from .forge import load_style
        meta = load_json(Path(a.build_dir) / (Path(a.build_dir).name + ".json"))
        print(export_build(a.build_dir, palette=load_style(meta["style"]).palette()))
        return 0
    if a.cmd == "sizes":
        from .scene import sizes
        print(sizes(a.build_dirs, a.scale, out=a.out))
        return 0
    if a.cmd == "silhouettes":
        from .scene import silhouettes
        print(silhouettes(a.build_dirs, a.dir, out=a.out))
        return 0
    if a.cmd == "materials":
        from .forge import load_style
        from .color import rgb_to_hex
        st = load_style(a.style)
        print(st.spec.get("about", ""))
        for m, d in st.materials.items():
            cols = " ".join(rgb_to_hex(c) for c in st.mat_colors(m))
            flags = " ".join(k for k in ("emissive", "no_outline") if d.get(k))
            print("  %-12s ramp=%-12s %s %s" % (m, d["ramp"], cols, flags))
        return 0
    if a.cmd == "fx":
        import json as _json
        from .forge import load_style
        from .vfx import render_effect
        from .io import save_gif, save_png, pack_sheet
        from .color import rgb_to_hex
        st = load_style(a.style)
        if a.ramp and "," in a.ramp:
            ramp = a.ramp.split(",")
        else:
            rn = a.ramp or next(iter(st.spec.get("vfx_ramps", {}).values()))
            ramp = [rgb_to_hex(c) for c in st.ramps[rn]]
        params = {}
        for kv in a.param:
            k, v = kv.split("=", 1)
            params[k] = _json.loads(v)
        frames = render_effect(a.kind, params, ramp)
        name = a.name or "fx_%s_%s" % (a.kind, a.ramp or "default")
        out = OUT / "fx" / name
        out.mkdir(parents=True, exist_ok=True)
        save_png(pack_sheet([frames]), out / (name + ".png"))
        save_png(pack_sheet([frames]), out / (name + "_x4.png"), scale=4)
        from .color import hex_to_rgb
        save_gif(frames, [75] * len(frames), out / (name + ".gif"), scale=4, bg=hex_to_rgb(st.spec.get("bg", "#222")))
        (out / (name + ".json")).write_text(_json.dumps({"kind": a.kind, "frames": len(frames), "ms": 75,
                                                         "frame_w": frames[0].shape[1], "frame_h": frames[0].shape[0],
                                                         "ramp": ramp, "params": params}, indent=1))
        print("fx %s: %d frames -> %s" % (a.kind, len(frames), out))
        return 0
    if a.cmd == "lint":
        from .lint import lint_build, silhouette_family
        for d in a.build_dirs:
            print("[%s]" % Path(d).name)
            for m in lint_build(d):
                print("  " + m)
        if len(a.build_dirs) > 1:
            print("[family]")
            from .lint import size_family
            for m in silhouette_family(a.build_dirs) + size_family(a.build_dirs):
                print("  " + m)
        return 0
    if a.cmd == "scene":
        from .scene import compose
        print(compose(a.build_dirs, a.style, a.clip, a.dir, scale=a.scale, out=a.out))
        return 0
    if a.cmd == "review":
        from .review import onion_sheet, review_sheet
        if a.onion:
            print(onion_sheet(a.build_dir, a.clips.split(",") if a.clips else None,
                              a.dirs.split(",") if a.dirs else None, a.scale))
            return 0
        print(review_sheet(a.build_dir, a.clips.split(",") if a.clips else None,
                           a.dirs.split(",") if a.dirs else None, a.scale, a.bg))
        return 0
    if a.cmd == "build":
        spec = load_spec(a.spec)
        if a.clips:
            spec["clips"] = a.clips.split(",")
        out = Path(a.out) if a.out else OUT / spec["name"]
        t = time.time()
        meta = Forge(spec).build(out, a.dirs.split(",") if a.dirs else None,
                                 maps=a.maps.split(",") if a.maps else None)
        print("built %s: %d clips -> %s (%.1fs)" % (meta["name"], len(meta["clips"]), out, time.time() - t))
    return 0


if __name__ == "__main__":
    sys.exit(main())
