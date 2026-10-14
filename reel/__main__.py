"""CLI: python3 -m reel <command> ...

  split <sheet.png> [--names s,se,e,ne,n]   one-row facing sheet -> ref/start_<facing>.png on one baseline
  gambit <char.json>                  takes -> keyed, cut, finished 8-direction sheets + actor json + qc.json
  fx <spec.json>                      spell effect on black -> additive overlay sheet (out/reel/_fx/<name>)
  demo <name> [<name> ...] [--fx a,b] [--out D]   playable 8-direction demo: walk, attack, cast spells
  page <name> [<name> ...] [--out D]  review page: board at game size, every state x facing, onions, raw takes
  contact <video> [--every 2]         numbered sheet of a take's frames, for picking keys by eye
  key <video> [--color auto]          key one take, write a matte check (source | magenta | white | black)
  probe <video>                       size / fps / frame count
  light new <name>                    reel/lit/<name>/: light.json template + clip dirs (lit side view, LIGHTING.md)
  light start <design.png> <out.png> [--left 0.4]   the takes' start frame: keyed figure on a 16:9 key-colour frame
  light frames <video> <dir> [--every 2 --start 3 --end 121]   numbered stills f<NNN>.png (NNN = filmed frame)
  light loop <dir> [--min 16]         walk loop candidates by pose + motion match (filmed frame numbers)
  light patina <light.json> [--yes]   PATINA normal maps for the frames that need them (dry run without --yes)
  light build <light.json> [--out D]  colour + normal atlas + <name>.json ("pixling.lit-sprite" v1)
  light check <sheet.json>            per-pair colour / motion / foot / torso alarms (exit 1 on an alarm)
  light demo <sheet.json> [--out D]   playable page: walk, clips, movable lights
  light export <sheet.json> <dir> [--engine web|godot]   sheet + player (litsprite.js / lit_sprite.gd) into a game
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    gm = sub.add_parser("gambit")
    gm.add_argument("spec")
    pg = sub.add_parser("page")
    pg.add_argument("names", nargs="+")
    pg.add_argument("--out")
    dm = sub.add_parser("demo")
    dm.add_argument("names", nargs="+")
    dm.add_argument("--out")
    dm.add_argument("--fx", default="")
    fx = sub.add_parser("fx")
    fx.add_argument("spec")
    k = sub.add_parser("key")
    k.add_argument("video")
    k.add_argument("--color", default="auto")
    k.add_argument("--out")
    ct = sub.add_parser("contact")
    ct.add_argument("video")
    ct.add_argument("--color", default="auto")
    ct.add_argument("--every", type=int, default=2)
    ct.add_argument("--out")
    p = sub.add_parser("probe")
    p.add_argument("video")
    sp = sub.add_parser("split")
    sp.add_argument("sheet")
    sp.add_argument("--names", default="s,se,e,ne,n")
    sp.add_argument("--size", type=int, default=2048)
    sp.add_argument("--out")
    lt = sub.add_parser("light")
    lt.add_argument("op", choices=["new", "start", "frames", "loop", "patina", "build", "check", "demo", "export"])
    lt.add_argument("path")
    lt.add_argument("dest", nargs="?")
    lt.add_argument("--every", type=int, default=1)
    lt.add_argument("--start", type=int, default=0)
    lt.add_argument("--end", type=int)
    lt.add_argument("--min", type=int, default=16)
    lt.add_argument("--key", default="255,0,255")
    lt.add_argument("--out")
    lt.add_argument("--yes", action="store_true")
    lt.add_argument("--left", type=float, default=0.05, help="start: figure's left edge, fraction of the frame width")
    lt.add_argument("--engine", choices=["web", "godot"], default="web")
    a = ap.parse_args(argv)

    if a.cmd == "gambit":
        from .game import export
        print(f"-> {export(a.spec)}")
    elif a.cmd == "page":
        from .page import make
        print(make(a.names, a.out))
    elif a.cmd == "demo":
        from .demo import make as demo
        print(demo(a.names, a.out, [x for x in a.fx.split(",") if x]))
    elif a.cmd == "fx":
        from .fx import export as fx_export
        print(f"-> {fx_export(a.spec)}")
    elif a.cmd == "split":
        from .split import split
        for n, f in split(a.sheet, a.names.split(","), a.size, out=a.out).items():
            print(f"{n}: {f}")
    elif a.cmd == "light":
        from . import light
        if a.op == "new":
            print(f"-> {light.new(a.path)}")
        elif a.op == "start":
            print(f"-> {light.start_frame(a.path, a.dest or a.out, [int(x) for x in a.key.split(',')], left=a.left)}")
        elif a.op == "frames":
            done = light.dump_frames(a.path, a.dest or a.out, a.every, a.start, a.end)
            print(f"{len(done)} frames f{done[0]:03d}..f{done[-1]:03d} -> {a.dest or a.out}")
        elif a.op == "loop":
            nums = light.frame_numbers(a.path); key = [int(x) for x in a.key.split(",")]
            A = [light.keyed(light.frame_path(a.path, k), key)[1] for k in nums]
            for v, s_, e in light.find_loop(A, nums, a.min)[:5]:
                print(f"IoU {v:.3f}: {s_} matches {e} -> \"loop\": [{s_ + 1}, {e}], \"match\": {s_}")
        elif a.op == "patina":
            light.patina(a.path, a.yes)
        elif a.op == "build":
            light.build(a.path, a.out)
        elif a.op == "check":
            return 1 if light.check(a.path) else 0
        elif a.op == "demo":
            print(f"-> {light.demo(a.path, a.out or a.dest)}")
        else:
            if not (a.dest or a.out):
                raise SystemExit("light export <sheet.json> <dir>")
            print(f"-> {light.export(a.path, a.dest or a.out, a.engine)}")
    elif a.cmd == "probe":
        from .io import probe
        print(probe(a.video))
    elif a.cmd in ("key", "contact"):
        from . import cut, pack
        from .take import OUT, key_cfg, key_take
        cfg = key_cfg({"key": {"color": a.color}})
        out = Path(a.out or OUT / "_check" / Path(a.video).stem)
        cels, src = key_take(Path(a.video), cfg, out / "cache", "take", keep_src=a.cmd == "key")
        if a.cmd == "key":
            if not src:                       # cached: re-decode for the source views
                cels, src = key_take(Path(a.video), cfg, out / "cache_src", "take", keep_src=True)
            pack.matte_check(src, cels, out / "matte.png")
            print(f"-> {out / 'matte.png'}")
        else:
            ref = cels[0]
            cut.contact(cels[:: a.every], ref.feet, 160 / max(1, cut.height(ref)), out / "contact.png")
            print(f"-> {out / 'contact.png'}  (cell i = source frame i*{a.every})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
